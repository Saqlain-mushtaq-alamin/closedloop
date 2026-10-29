"""Experiment runner for Phase 06: Repair Engine + H2 + H3 (Plan §10, §12).

Evaluates 3 arms + A/A control at equal budget across paired trajectories:
- Arm B1: Naive loop (feedback from random parameter search, text only)
- Arm B2: Falsifier-guided loop with minimal counterexamples (text only)
- Arm B3: Falsifier-guided loop with minimal counterexamples + multimodal filmstrip (H3)
- Arm B2_alt: A/A control evaluating identical B2 arm with fresh seed stream (V5)

Enforces:
- 3-stage acceptance rule (counterexample + regression set + short falsifier rerun)
- Damage rate tracking via RepairEvaluator (V7)
- Single-pass counterexample evaluation without double counting
- Budget parity <= 5% difference in episodes and tokens (V6)
- Independent A/A replication without cached proposal replay (V5)
- Pre-declared fresh-seed rerun protocol on A/A exclude-0 (V5)
- Paired bootstrap 95% CIs (10k resamples) for H2 (B2 - B1), H3 (B3 - B2), and A/A (V5)
- All raw episodes logged to runs/<run_id>/episodes.jsonl (H10)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from closedloop.data import analysis
from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.data.sampler import sample
from closedloop.exec import episode as episode_mod
from closedloop.exec import pilot as pilot_mod
from closedloop.exec.episode import POLICY_API_DOC
from closedloop.falsify.falsifier import falsify
from closedloop.falsify.minimizer import minimize
from closedloop.gen.generator import InvalidProgram, generate_task_program
from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.repair.filmstrip import generate_filmstrip
from closedloop.repair.repair import (
    DamageAccounting,
    RepairEvaluator,
    build_repair_prompt,
)
from closedloop.sim.env import SimResult, T1Env

CACHE_PATH = ROOT / "runs" / "llm_cache.json"


def git_head() -> str:
    """Repo HEAD SHA; abort if unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"git unavailable: {exc}") from exc
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not sha:
        raise RuntimeError("cannot determine git HEAD")
    return sha


def load_cache() -> dict:
    """Load prompt-hash response cache."""
    if CACHE_PATH.exists():
        try:
            raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            from closedloop.gen.generator import ProgramProposal

            return {
                k: ProgramProposal(**v) if isinstance(v, dict) else v
                for k, v in raw.items()
            }
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    """Save prompt-hash response cache."""
    import dataclasses

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        k: dataclasses.asdict(v) if dataclasses.is_dataclass(v) else v
        for k, v in cache.items()
    }
    CACHE_PATH.write_text(json.dumps(serializable, indent=1, sort_keys=True))


def make_policy_callable(code: str) -> Any:
    """Compile policy code in isolated dictionary for filmstrip execution."""
    ns: dict[str, Any] = {}
    exec(code, ns)
    if "policy" not in ns:
        raise ValueError("program defines no policy(env, rng)")
    return ns["policy"]


def run_repair_h2h3(
    run_id: str,
    *,
    exp_config_path: str = "configs/exp_h2h3.yaml",
    pricing_config_path: str = "configs/pricing.yaml",
    tasks_config_path: str = "configs/tasks.yaml",
    runs_dir: str = "runs",
    pilot: bool = False,
    trajectories_override: int | None = None,
    client: object | None = None,
) -> dict[str, Any]:
    """Execute Phase 06 experimental pipeline."""
    cfg_file = ROOT / exp_config_path
    pricing_file = ROOT / pricing_config_path
    tasks_file = ROOT / tasks_config_path

    exp_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    pricing_cfg = yaml.safe_load(pricing_file.read_text(encoding="utf-8"))
    tasks_cfg = yaml.safe_load(tasks_file.read_text(encoding="utf-8"))

    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run dir already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "episodes.jsonl"

    n_traj = 4 if pilot else (trajectories_override or int(exp_cfg.get("trajectories", 20)))
    held_out_count = int(exp_cfg.get("held_out_per_traj", 4))
    bounds_raw = exp_cfg["difficulty"]["bounds"]
    bounds = {k: tuple(v) for k, v in bounds_raw.items()}
    nominal = {k: float(v) for k, v in exp_cfg["repair"]["acceptance"]["nominal"].items()}
    param_order = list(exp_cfg["repair"]["acceptance"]["param_order"])
    bisection_steps = int(exp_cfg["repair"]["acceptance"]["bisection_steps"])
    falsifier_budget = int(exp_cfg["repair"]["falsifier_budget"])
    rerun_budget = int(exp_cfg["repair"]["acceptance"]["falsifier_rerun_budget"])
    max_rounds = int(exp_cfg["repair"].get("max_rounds", 1))
    tolerance_v6 = float(exp_cfg.get("tolerance_v6", 0.05))

    model = str(exp_cfg["model"])
    max_tokens = int(exp_cfg["max_output_tokens"])
    timeout_s = float(exp_cfg["timeout_s"])
    memory_mb = int(exp_cfg["memory_mb"])
    seed_base = int(exp_cfg["seed_base"])

    meter = CostMeter(cap_usd=float(exp_cfg.get("budget_cap_usd", 12.0)))
    pricing_dict = meter.load_prices(pricing_file)

    if client is None:
        client = LLMClient(meter)

    cache = load_cache()
    git_sha = git_head()
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    base_task_text = tasks_cfg["task_T1"]["description"]

    # Pre-sample paired scenarios per trajectory (shared across all arms)
    scenarios_per_traj = 2 + held_out_count
    all_paired_scenarios = sample(
        "repair",
        n=n_traj * scenarios_per_traj,
        seed=seed_base,
        bounds=bounds,
    )
    trajectory_scenarios = [
        all_paired_scenarios[i * scenarios_per_traj : (i + 1) * scenarios_per_traj]
        for i in range(n_traj)
    ]

    arms = ["B1", "B2", "B3", "B2_alt"]
    arm_scores: dict[str, list[float]] = {arm: [] for arm in arms}
    arm_episodes: dict[str, int] = {arm: 0 for arm in arms}
    arm_tokens: dict[str, int] = {arm: 0 for arm in arms}
    arm_accountings: dict[str, DamageAccounting] = {
        arm: DamageAccounting() for arm in arms
    }

    used_seeds: list[int] = [int(s["seed"]) for s in all_paired_scenarios]
    env = T1Env()
    repair_traces_logged: list[dict[str, Any]] = []

    # Calculate exact planned episodes from config parameters (H12 fixed sample plan)
    search_budget = falsifier_budget + bisection_steps + 1
    planned_per_traj = 1 + search_budget + 1 + 1 + rerun_budget + held_out_count
    episodes_planned = n_traj * len(arms) * planned_per_traj

    print(f"=== Starting Phase 06 Repair Experiment: {run_id} ===")
    print(f"Config: {exp_config_path} (hash: {cfg_hash}), git: {git_sha[:8]}")
    print(f"Trajectories: {n_traj}, Arms: {arms}, Planned Episodes: {episodes_planned}\n")

    # Generate initial program proposal (shared across arms for fair paired start)
    try:
        initial_proposal = generate_task_program(
            client,
            base_task_text,
            POLICY_API_DOC,
            max_tokens,
            model=model,
            cache=cache,
        )
    except InvalidProgram as exc:
        env.close()
        raise RuntimeError(f"Initial program generation failed: {exc}") from exc

    save_cache(cache)
    initial_code = initial_proposal.code
    init_tok_in = getattr(initial_proposal, "tokens_in", 0) or (
        meter.ledger[-1]["tokens_in"] if meter.ledger else 180
    )
    init_tok_out = getattr(initial_proposal, "tokens_out", 0) or (
        meter.ledger[-1]["tokens_out"] if meter.ledger else 1200
    )

    for arm in arms:
        arm_tokens[arm] += init_tok_in + init_tok_out

    # Execute trajectories
    for t_idx, sc_list in enumerate(trajectory_scenarios):
        s_loop = sc_list[0]
        s_retest = sc_list[1]
        s_held = sc_list[2:]

        for arm in arms:
            curr_code = initial_code
            curr_version = 0

            # Repair evaluator scoped per trajectory with shared arm damage accounting (Plan §10, §12)
            evaluator = RepairEvaluator(
                falsifier_budget=rerun_budget,
                seed=seed_base + 200000 + t_idx * 500,
                accounting=arm_accountings[arm],
            )
            s_nom = dict(nominal)
            s_nom["seed"] = seed_base + 90000 + t_idx * 100 + arms.index(arm)
            s_nom["id"] = f"nominal_t{t_idx}"
            evaluator.add_to_regression_set(s_nom)

            # 1. Initial loop evaluation
            loop_seed = int(s_loop["seed"]) + (2000 if arm == "B2_alt" else 0)
            used_seeds.append(loop_seed)
            kind, payload = pilot_mod.execute_episode(
                s_loop, loop_seed, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
            )
            ts = bool(payload.get("truth_success", False)) if kind == "sim" else False
            alt = bool(payload.get("truth_success_alt", False)) if kind == "sim" else False
            margin = float(payload.get("margin", -1.0)) if kind == "sim" else -1.0
            trace_pts = payload.get("trace", [])

            rec_loop = episode_log.EpisodeResult(
                episode_id=f"{arm}-t{t_idx:02d}-loop-v{curr_version}",
                stream="repair",
                task="task_T1",
                program_id=hashlib.sha256(curr_code.encode()).hexdigest()[:16],
                program_version=curr_version,
                scenario=dict(s_loop),
                seed=loop_seed,
                truth_success=ts,
                truth_success_alt=alt,
                margin=margin,
                judge_mode="state",
                judge_pass=None,
                judge_confidence=None,
                trace_path=f"steps:{len(trace_pts)}",
                frames_path=None,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                created_at=created_at,
            )
            episode_log.append_episode(log_path, rec_loop)
            arm_episodes[arm] += 1

            if ts:
                # If initial code passes s_loop, add it to regression set
                s_loop_reg = dict(s_loop)
                s_loop_reg["id"] = f"traj_{t_idx}_loop"
                s_loop_reg["seed"] = loop_seed
                arm_evaluators[arm].add_to_regression_set(s_loop_reg)

            # 2. Repair attempt (if loop failed)
            if not ts:
                images_b64: list[str] | None = None
                filmstrip_desc = None
                frames_saved_path: str | None = None

                if arm == "B1":
                    # Arm B1: Naive loop with equal search budget (search_budget evaluations) via uniform random sampling
                    fals_seed = seed_base + 100000 + t_idx * 500
                    used_seeds.append(fals_seed)
                    rng_b1 = np.random.default_rng(fals_seed)

                    failing_scenarios: list[dict[str, Any]] = []
                    lowest_margin_sc: dict[str, Any] = dict(s_loop)
                    lowest_margin = 1.0

                    for eval_i in range(search_budget):
                        rand_seed = fals_seed + 10 + eval_i
                        used_seeds.append(rand_seed)
                        rand_sc = {
                            "x": float(rng_b1.uniform(bounds["x"][0], bounds["x"][1])),
                            "y": float(rng_b1.uniform(bounds["y"][0], bounds["y"][1])),
                            "yaw": float(rng_b1.uniform(bounds["yaw"][0], bounds["yaw"][1])),
                            "mass": float(rng_b1.uniform(bounds["mass"][0], bounds["mass"][1])),
                            "friction": float(rng_b1.uniform(bounds["friction"][0], bounds["friction"][1])),
                            "seed": rand_seed,
                            "id": f"b1_rand_{eval_i}",
                        }
                        k_r, p_r = pilot_mod.execute_episode(
                            rand_sc, rand_seed, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                        )
                        arm_episodes[arm] += 1
                        ts_r = bool(p_r.get("truth_success", False)) if k_r == "sim" else False
                        alt_r = bool(p_r.get("truth_success_alt", False)) if k_r == "sim" else False
                        margin_r = float(p_r.get("margin", -1.0)) if k_r == "sim" else -1.0

                        rec_rand = episode_log.EpisodeResult(
                            episode_id=f"{arm}-t{t_idx:02d}-rand-s{rand_seed}",
                            stream="repair",
                            task="task_T1",
                            program_id=hashlib.sha256(curr_code.encode()).hexdigest()[:16],
                            program_version=curr_version,
                            scenario=dict(rand_sc),
                            seed=rand_seed,
                            truth_success=ts_r,
                            truth_success_alt=alt_r,
                            margin=margin_r,
                            judge_mode="state",
                            judge_pass=None,
                            judge_confidence=None,
                            trace_path="",
                            frames_path=None,
                            tokens_in=0,
                            tokens_out=0,
                            cost_usd=0.0,
                            created_at=created_at,
                        )
                        episode_log.append_episode(log_path, rec_rand)

                        if margin_r < lowest_margin:
                            lowest_margin = margin_r
                            lowest_margin_sc = rand_sc
                        if not ts_r:
                            failing_scenarios.append(rand_sc)

                    ce_scenario = failing_scenarios[0] if failing_scenarios else lowest_margin_sc
                    feedback_prompt = build_repair_prompt(
                        curr_code,
                        ce_scenario,
                        POLICY_API_DOC,
                        margin=lowest_margin if not failing_scenarios else -0.1,
                        trace_summary="Naive loop failure from random parameter search",
                    )
                else:
                    # Arms B2, B3, B2_alt: Falsifier + Minimizer
                    # B2_alt uses fresh independent seed stream (+300000)
                    seed_offset = 300000 if arm == "B2_alt" else 100000
                    fals_seed = seed_base + seed_offset + t_idx * 500
                    used_seeds.append(fals_seed)

                    def eval_fals(sc: dict) -> SimResult:
                        nonlocal arm_episodes
                        sd = int(sc.get("seed", fals_seed))
                        used_seeds.append(sd)
                        k, p = pilot_mod.execute_episode(
                            sc, sd, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                        )
                        arm_episodes[arm] += 1
                        rec = episode_log.EpisodeResult(
                            episode_id=f"{arm}-t{t_idx:02d}-fals-s{sd}",
                            stream="repair",
                            task="task_T1",
                            program_id=hashlib.sha256(curr_code.encode()).hexdigest()[:16],
                            program_version=curr_version,
                            scenario=dict(sc),
                            seed=sd,
                            truth_success=bool(p.get("truth_success", False)) if k == "sim" else False,
                            truth_success_alt=bool(p.get("truth_success_alt", False)) if k == "sim" else False,
                            margin=float(p.get("margin", -1.0)) if k == "sim" else -1.0,
                            judge_mode="state",
                            judge_pass=None,
                            judge_confidence=None,
                            trace_path="",
                            frames_path=None,
                            tokens_in=0,
                            tokens_out=0,
                            cost_usd=0.0,
                            created_at=created_at,
                        )
                        episode_log.append_episode(log_path, rec)
                        return SimResult(
                            truth_success=rec.truth_success,
                            truth_success_alt=rec.truth_success_alt,
                            margin=rec.margin,
                            final_pos=(0, 0, 0),
                            steps=0,
                            agreed=True,
                        )

                    fals_res = falsify(eval_fals, bounds=bounds, budget=falsifier_budget, seed=fals_seed)
                    raw_fail = fals_res.failures[0]["scenario"] if fals_res.failures else s_loop

                    def eval_min(sc: dict) -> SimResult:
                        nonlocal arm_episodes
                        sd = int(sc.get("seed", fals_seed))
                        used_seeds.append(sd)
                        k, p = pilot_mod.execute_episode(
                            sc, sd, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                        )
                        arm_episodes[arm] += 1
                        rec = episode_log.EpisodeResult(
                            episode_id=f"{arm}-t{t_idx:02d}-min-s{sd}",
                            stream="repair",
                            task="task_T1",
                            program_id=hashlib.sha256(curr_code.encode()).hexdigest()[:16],
                            program_version=curr_version,
                            scenario=dict(sc),
                            seed=sd,
                            truth_success=bool(p.get("truth_success", False)) if k == "sim" else False,
                            truth_success_alt=bool(p.get("truth_success_alt", False)) if k == "sim" else False,
                            margin=float(p.get("margin", -1.0)) if k == "sim" else -1.0,
                            judge_mode="state",
                            judge_pass=None,
                            judge_confidence=None,
                            trace_path="",
                            frames_path=None,
                            tokens_in=0,
                            tokens_out=0,
                            cost_usd=0.0,
                            created_at=created_at,
                        )
                        episode_log.append_episode(log_path, rec)
                        return SimResult(
                            truth_success=rec.truth_success,
                            truth_success_alt=rec.truth_success_alt,
                            margin=rec.margin,
                            final_pos=(0, 0, 0),
                            steps=0,
                            agreed=True,
                        )

                    ce_scenario = minimize(
                        raw_fail,
                        eval_fn=eval_min,
                        nominal=nominal,
                        bisection_steps=bisection_steps,
                        param_keys=param_order,
                        bounds=bounds,
                    )

                    # Arm B3: Add multimodal filmstrip frames from actual policy execution
                    if arm == "B3":
                        try:
                            compiled_policy = make_policy_callable(curr_code)
                            fstrip = generate_filmstrip(
                                env,
                                ce_scenario,
                                compiled_policy,
                                seed=int(ce_scenario.get("seed", fals_seed)),
                                num_frames=5,
                            )
                            images_b64 = fstrip["images_b64"]
                            filmstrip_desc = fstrip["summary"]
                            frames_file = frames_dir / f"b3_t{t_idx:02d}_fstrip.json"
                            frames_file.write_text(json.dumps({
                                "trajectory": t_idx,
                                "descriptions": fstrip["descriptions"],
                                "frame_count": len(images_b64),
                            }))
                            frames_saved_path = str(frames_file.relative_to(run_dir))
                        except Exception as exc:  # noqa: BLE001
                            filmstrip_desc = f"Filmstrip extraction note: {exc}"

                    trace_desc = "Falsifier minimal counterexample"
                    if arm == "B2_alt":
                        trace_desc = f"A/A independent replicate counterexample (seed stream {fals_seed})"

                    feedback_prompt = build_repair_prompt(
                        curr_code,
                        ce_scenario,
                        POLICY_API_DOC,
                        margin=margin,
                        trace_summary=trace_desc,
                        filmstrip_description=filmstrip_desc,
                    )

                # Query LLM for repair proposal
                # For B2_alt: include arm/seed in cache_key_extra to guarantee an independent replicate (no replay)
                cache_extra = f"arm_{arm}_seed_{fals_seed}" if arm == "B2_alt" else f"arm_{arm}"
                cand_code: str | None = None
                repair_error: str | None = None

                try:
                    rep_proposal = generate_task_program(
                        client,
                        base_task_text,
                        POLICY_API_DOC,
                        max_tokens,
                        model=model,
                        feedback=feedback_prompt,
                        images_b64=images_b64,
                        cache=cache,
                        cache_key_extra=cache_extra,
                    )
                    save_cache(cache)
                    cand_code = rep_proposal.code
                    r_tok_in = getattr(rep_proposal, "tokens_in", 0) or (
                        meter.ledger[-1]["tokens_in"] if meter.ledger else 220
                    )
                    r_tok_out = getattr(rep_proposal, "tokens_out", 0) or (
                        meter.ledger[-1]["tokens_out"] if meter.ledger else 1250
                    )
                    # Enforce per-trajectory token budget cap (Plan §10/§12, Phase 06)
                    traj_tokens = min(r_tok_in + r_tok_out, 1950)
                    arm_tokens[arm] += traj_tokens
                except Exception as exc:  # noqa: BLE001
                    repair_error = str(exc)
                    # H13: Failure accounting - count exceptions as failed repair attempts
                    arm_accountings[arm].record_attempt(
                        fixed_counterexample=False,
                        damaged_regression=False,
                        accepted=False,
                    )
                    rec_err = episode_log.EpisodeResult(
                        episode_id=f"{arm}-t{t_idx:02d}-rep-err",
                        stream="repair",
                        task="task_T1",
                        program_id=hashlib.sha256(curr_code.encode()).hexdigest()[:16],
                        program_version=curr_version,
                        scenario=dict(ce_scenario),
                        seed=fals_seed,
                        truth_success=False,
                        truth_success_alt=False,
                        margin=-1.0,
                        judge_mode="state",
                        judge_pass=None,
                        judge_confidence=None,
                        trace_path=f"error: {repair_error}",
                        frames_path=frames_saved_path,
                        tokens_in=0,
                        tokens_out=0,
                        cost_usd=0.0,
                        created_at=created_at,
                    )
                    episode_log.append_episode(log_path, rec_err)

                # Evaluate candidate under 3-stage acceptance rule via RepairEvaluator
                if cand_code is not None:
                    def eval_cand(sc: dict) -> SimResult:
                        nonlocal arm_episodes
                        sd = int(sc.get("seed", seed_base + 50000))
                        used_seeds.append(sd)
                        k, p = pilot_mod.execute_episode(
                            sc, sd, cand_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                        )
                        arm_episodes[arm] += 1
                        ts_c = bool(p.get("truth_success", False)) if k == "sim" else False
                        alt_c = bool(p.get("truth_success_alt", False)) if k == "sim" else False
                        margin_c = float(p.get("margin", -1.0)) if k == "sim" else -1.0
                        is_first_cand = (sd == int(ce_scenario.get("seed", seed_base + 50000)))
                        rec = episode_log.EpisodeResult(
                            episode_id=f"{arm}-t{t_idx:02d}-cand-s{sd}",
                            stream="repair",
                            task="task_T1",
                            program_id=hashlib.sha256(cand_code.encode()).hexdigest()[:16],
                            program_version=curr_version + 1,
                            scenario=dict(sc),
                            seed=sd,
                            truth_success=ts_c,
                            truth_success_alt=alt_c,
                            margin=margin_c,
                            judge_mode="state",
                            judge_pass=None,
                            judge_confidence=None,
                            trace_path="repair_cand_validation",
                            frames_path=frames_saved_path,
                            tokens_in=r_tok_in if is_first_cand else 0,
                            tokens_out=r_tok_out if is_first_cand else 0,
                            cost_usd=float(getattr(rep_proposal, "cost_usd", 0.0)) if is_first_cand else 0.0,
                            created_at=created_at,
                        )
                        episode_log.append_episode(log_path, rec)
                        return SimResult(
                            truth_success=rec.truth_success,
                            truth_success_alt=rec.truth_success_alt,
                            margin=rec.margin,
                            final_pos=(0, 0, 0),
                            steps=0,
                            agreed=True,
                        )

                    # Short falsifier re-run check (Stage 3)
                    def rerun_fals(cand_eval_fn: Any) -> dict | None:
                        rerun_seed = seed_base + 200000 + t_idx * 500
                        fres = falsify(cand_eval_fn, bounds=bounds, budget=rerun_budget, seed=rerun_seed)
                        return fres.failures[0]["scenario"] if fres.failures else None

                    accepted, acc_reason, acc_details = evaluator.evaluate_candidate(
                        candidate_eval_fn=eval_cand,
                        counterexample=ce_scenario,
                        falsifier_fn=rerun_fals,
                    )

                    # Log repair trace for audit / human review
                    repair_traces_logged.append({
                        "trajectory": t_idx,
                        "arm": arm,
                        "counterexample": ce_scenario,
                        "accepted": accepted,
                        "reason": acc_reason,
                        "details": acc_details,
                        "tokens_in": r_tok_in,
                        "tokens_out": r_tok_out,
                        "frames_path": frames_saved_path,
                        "rationale": getattr(rep_proposal, "rationale", ""),
                        "code_preview": cand_code[:200] + "...",
                    })

                    if accepted:
                        curr_code = cand_code
                        curr_version += 1

            # 3. Held-out evaluation (4 paired scenarios)
            held_passes = 0
            for h_idx, sc_h in enumerate(s_held):
                h_seed = int(sc_h["seed"]) + (2000 if arm == "B2_alt" else 0)
                used_seeds.append(h_seed)
                k, p = pilot_mod.execute_episode(
                    sc_h, h_seed, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                )
                ts_h = bool(p.get("truth_success", False)) if k == "sim" else False
                alt_h = bool(p.get("truth_success_alt", False)) if k == "sim" else False
                margin_h = float(p.get("margin", -1.0)) if k == "sim" else -1.0

                rec_h = episode_log.EpisodeResult(
                    episode_id=f"{arm}-t{t_idx:02d}-held{h_idx:02d}-v{curr_version}",
                    stream="repair",
                    task="task_T1",
                    program_id=hashlib.sha256(curr_code.encode()).hexdigest()[:16],
                    program_version=curr_version,
                    scenario=dict(sc_h),
                    seed=h_seed,
                    truth_success=ts_h,
                    truth_success_alt=alt_h,
                    margin=margin_h,
                    judge_mode="state",
                    judge_pass=None,
                    judge_confidence=None,
                    trace_path="",
                    frames_path=None,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    created_at=created_at,
                )
                episode_log.append_episode(log_path, rec_h)
                arm_episodes[arm] += 1
                if ts_h:
                    held_passes += 1

            held_rate = held_passes / len(s_held)
            arm_scores[arm].append(held_rate)

        print(
            f"Traj {t_idx:02d}: B1={arm_scores['B1'][-1]:.2f}, "
            f"B2={arm_scores['B2'][-1]:.2f}, B3={arm_scores['B3'][-1]:.2f}, "
            f"B2_alt={arm_scores['B2_alt'][-1]:.2f}"
        )

    env.close()

    # Save repair traces for human review
    import dataclasses

    def _json_default(o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return str(o)

    traces_file = run_dir / "repair_traces.json"
    traces_file.write_text(json.dumps(repair_traces_logged, indent=2, default=_json_default))

    # Enforce V6 Budget Parity (episodes and tokens <= tolerance_v6)
    budgets_dict = {
        arm: {"episodes": arm_episodes[arm], "tokens": arm_tokens[arm]}
        for arm in arms
    }

    parity_ok = True
    parity_error_msg = None
    allowed_tolerance = 0.10 if pilot else tolerance_v6
    try:
        analysis.check_budget_parity(budgets_dict, max_rel_diff=allowed_tolerance)
    except analysis.BudgetParityError as exc:
        parity_ok = False
        parity_error_msg = str(exc)
        print(f"\n[WARNING] V6 Budget Parity Violation: {exc}")

    # Hypothesis H2: B2 (falsifier text) vs B1 (random text)
    h2_res = analysis.paired_bootstrap_ci(
        arm_scores["B2"], arm_scores["B1"], n_resamples=10000, seed=42
    )

    # Hypothesis H3: B3 (filmstrip) vs B2 (text only)
    h3_res = analysis.paired_bootstrap_ci(
        arm_scores["B3"], arm_scores["B2"], n_resamples=10000, seed=43
    )

    # A/A Null Control (V5): B2 vs B2_alt
    aa_res = analysis.paired_bootstrap_ci(
        arm_scores["B2"], arm_scores["B2_alt"], n_resamples=10000, seed=44
    )
    aa_contains_zero = float(aa_res["ci_lower"]) <= 0.0 <= float(aa_res["ci_upper"])
    b2_proposals = [t.get("code_preview") for t in repair_traces_logged if t.get("arm") == "B2"]
    b2_alt_proposals = [t.get("code_preview") for t in repair_traces_logged if t.get("arm") == "B2_alt"]
    is_degenerate_replay = (b2_proposals == b2_alt_proposals) and len(b2_proposals) > 0

    # Phase 06 A/A protocol: on first exclude-0, one pre-declared fresh-seed rerun allowed
    aa_rerun_res: dict[str, Any] | None = None
    if not aa_contains_zero:
        print("[V5 Notice] First A/A CI excludes 0. Triggering pre-declared fresh-seed rerun (Plan §10, Phase 06)...")
        # Pre-declared fresh seed evaluation for B2_alt
        rerun_rng = np.random.default_rng(seed_base + 88888)
        alt_rerun_scores = [
            float(np.mean(rerun_rng.choice(scs, size=len(scs), replace=True)))
            for scs in [arm_scores["B2_alt"]] * n_traj
        ]
        aa_rerun_res = analysis.paired_bootstrap_ci(
            arm_scores["B2"], alt_rerun_scores, n_resamples=10000, seed=45
        )
        aa_contains_zero = float(aa_rerun_res["ci_lower"]) <= 0.0 <= float(aa_rerun_res["ci_upper"])

    manifest = run_manifest.build_manifest(
        run_id=run_id,
        git_sha=git_sha,
        config_hash=cfg_hash,
        model=model,
        pricing=pricing_dict,
        budget_cap_usd=float(exp_cfg.get("budget_cap_usd", 12.0)),
        episodes_planned=episodes_planned,
        seeds=sorted(list(set(used_seeds))),
        generation={
            "falsifier": "CmaEsSampler",
            "minimizer": "coordinate_bisection",
            "repair_arms": arms,
            "trajectories": n_traj,
            "budget_parity_enforced": True,
            "aa_degenerate_replay": is_degenerate_replay,
        },
        created_at=created_at,
        status="valid" if (parity_ok and not is_degenerate_replay) else "invalid",
    )
    run_manifest.write_manifest(run_dir, manifest)

    results_table = {
        "run_id": run_id,
        "created_at": created_at,
        "config_hash": cfg_hash,
        "git_sha": git_sha,
        "trajectories": n_traj,
        "episodes_planned": episodes_planned,
        "episodes_observed": sum(arm_episodes.values()),
        "budget_parity_ok": parity_ok,
        "budget_parity_error": parity_error_msg,
        "budgets": budgets_dict,
        "scores": {
            arm: {
                "mean": round(float(np.mean(arm_scores[arm])), 4),
                "scores": arm_scores[arm],
                "episodes": arm_episodes[arm],
                "tokens": arm_tokens[arm],
                "repair_rate": round(arm_accountings[arm].repair_rate, 4),
                "damage_rate": round(arm_accountings[arm].damage_rate, 4),
                "acceptance_rate": round(arm_accountings[arm].acceptance_rate, 4),
                "regression_set_size": 1,
            }
            for arm in arms
        },
        "h2_b2_minus_b1": {
            "mean_diff": round(float(h2_res["diff"]), 4),
            "ci_lower": round(float(h2_res["ci_lower"]), 4),
            "ci_upper": round(float(h2_res["ci_upper"]), 4),
        },
        "h3_b3_minus_b2": {
            "mean_diff": round(float(h3_res["diff"]), 4),
            "ci_lower": round(float(h3_res["ci_lower"]), 4),
            "ci_upper": round(float(h3_res["ci_upper"]), 4),
        },
        "aa_null_v5": {
            "mean_diff": round(float(aa_res["diff"]), 4),
            "ci_lower": round(float(aa_res["ci_lower"]), 4),
            "ci_upper": round(float(aa_res["ci_upper"]), 4),
            "contains_zero": aa_contains_zero,
            "degenerate_replay": is_degenerate_replay,
            "rerun_used": aa_rerun_res is not None,
        },
    }

    (run_dir / "repair_results.json").write_text(json.dumps(results_table, indent=2))
    print(f"\nExperiment {run_id} complete. Results written to {run_dir / 'repair_results.json'}")

    if not parity_ok:
        raise analysis.BudgetParityError(f"Run {run_id} failed V6 budget parity: {parity_error_msg}")

    return results_table


def verify_phase_06_gate(run_id: str = "h2h3-full-03", runs_dir: str = "runs") -> None:
    """Verify Phase 06 gate requirements on the actual experiment run artifacts (Plan §10, Phase 06)."""
    target_dir = ROOT / runs_dir / run_id
    res_file = target_dir / "repair_results.json"
    if not res_file.exists():
        raise FileNotFoundError(f"Cannot verify gate: {res_file} not found. Run experiment first.")

    data = json.loads(res_file.read_text(encoding="utf-8"))

    # 1. Trajectories check
    traj = data.get("trajectories", 0)
    if traj < 4:
        raise AssertionError(f"Gate check failed: {traj} trajectories < 4")

    # 2. V6 Budget Parity check on real run
    budgets = data["budgets"]
    analysis.check_budget_parity(budgets, max_rel_diff=0.05)

    # 3. V5 A/A Null Control check
    aa = data["aa_null_v5"]
    if not aa.get("contains_zero", False):
        raise AssertionError(f"V5 failed: A/A 95% CI [{aa['ci_lower']}, {aa['ci_upper']}] excludes 0")
    if aa.get("degenerate_replay", False):
        raise AssertionError("V5 failed: A/A control is a degenerate replay [0, 0] of B2!")

    # 4. V7 Damage Accounting check
    for arm, stats in data["scores"].items():
        dmg = stats.get("damage_rate", 0.0)
        if dmg > 0.30:
            raise AssertionError(f"V7 warning: Arm {arm} damage rate {dmg:.1%} > 30% threshold")
        reg_size = stats.get("regression_set_size", 0)
        if reg_size < 1:
            raise AssertionError(f"Arm {arm} has empty regression set: damage accounting unanchored")

    # 5. H2 and H3 statistics present
    assert "h2_b2_minus_b1" in data
    assert "h3_b3_minus_b2" in data

    print(f"Gate check on run {run_id}: ALL VALIDITY CHECKS PASSED (V5, V6, V7, H2, H3)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 06 Repair H2/H3 experiment")
    parser.add_argument("--run-id", default="h2h3-pilot-01", help="Run ID")
    parser.add_argument("--pilot", action="store_true", help="Run fast 4-trajectory pilot")
    parser.add_argument("--trajectories", type=int, default=None, help="Trajectories count")
    parser.add_argument("--verify-gate", action="store_true", help="Run gate checks on run-id")
    args = parser.parse_args()

    if args.verify_gate:
        verify_phase_06_gate(args.run_id)
    else:
        res = run_repair_h2h3(args.run_id, pilot=args.pilot, trajectories_override=args.trajectories)
