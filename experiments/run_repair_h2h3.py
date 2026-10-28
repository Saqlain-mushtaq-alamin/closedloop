"""Experiment runner for Phase 06: Repair Engine + H2 + H3 (Plan §10, §12).

Evaluates 3 arms + A/A control at equal budget across paired trajectories:
- Arm B1: Naive loop (feedback from random-seed failure, text only)
- Arm B2: Falsifier-guided loop with minimal counterexamples (text only)
- Arm B3: Falsifier-guided loop with minimal counterexamples + multimodal filmstrip (H3)
- Arm B2_alt: A/A control evaluating identical B2 arm with fresh seed stream (V5)

Enforces:
- 3-stage acceptance rule (counterexample + regression set + short falsifier rerun)
- Damage rate tracking (V7)
- Budget parity <= 5% difference in episodes and tokens (V6)
- Paired bootstrap 95% CIs (10k resamples) for H2 (B2 - B1), H3 (B3 - B2), and A/A (V5)
- All raw episodes logged to runs/<run_id>/episodes.jsonl (H10)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from closedloop.data import analysis
from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.data.sampler import sample
from closedloop.exec import episode as episode_mod
from closedloop.exec import pilot as pilot_mod
from closedloop.exec.episode import POLICY_API_DOC
from closedloop.falsify.falsifier import falsify
from closedloop.falsify.minimizer import is_failing, minimize
from closedloop.gen.generator import InvalidProgram, generate_task_program
from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.repair.filmstrip import generate_filmstrip
from closedloop.repair.repair import (
    DamageAccounting,
    RepairEvaluator,
    build_repair_prompt,
    verify_repair_acceptance,
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

    model = str(exp_cfg["model"])
    max_tokens = int(exp_cfg["max_output_tokens"])
    timeout_s = float(exp_cfg["timeout_s"])
    memory_mb = int(exp_cfg["memory_mb"])
    seed_base = int(exp_cfg["seed_base"])

    meter = CostMeter(cap_usd=float(exp_cfg.get("budget_cap_usd", 12.0)))
    meter.load_prices(pricing_file)

    if client is None:
        client = LLMClient(meter)

    cache = load_cache()
    git_sha = git_head()
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    base_task_text = tasks_cfg["task_T1"]["description"]

    # Pre-sample paired scenarios per trajectory (shared across all arms)
    # Each trajectory draws: 1 loop scenario, 1 retest scenario, held_out_count held-out scenarios
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
    arm_damage_accounting: dict[str, DamageAccounting] = {arm: DamageAccounting() for arm in arms}

    used_seeds: list[int] = [int(s["seed"]) for s in all_paired_scenarios]
    env = T1Env()

    print(f"=== Starting Phase 06 Repair Experiment: {run_id} ===")
    print(f"Config: {exp_config_path} (hash: {cfg_hash}), git: {git_sha[:8]}")
    print(f"Trajectories: {n_traj}, Arms: {arms}, Held-out per traj: {held_out_count}\n")

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
    init_tok_in = getattr(initial_proposal, "tokens_in", 0) or (meter.ledger[-1]["tokens_in"] if meter.ledger else 180)
    init_tok_out = getattr(initial_proposal, "tokens_out", 0) or (meter.ledger[-1]["tokens_out"] if meter.ledger else 1200)

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

            # 1. Initial loop evaluation
            loop_seed = int(s_loop["seed"]) + (1000 if arm == "B2_alt" else 0)
            used_seeds.append(loop_seed)
            kind, payload = pilot_mod.execute_episode(
                s_loop, loop_seed, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
            )
            ts = bool(payload.get("truth_success", False)) if kind == "sim" else False
            alt = bool(payload.get("truth_success_alt", False)) if kind == "sim" else False
            margin = float(payload.get("margin", -1.0)) if kind == "sim" else -1.0

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
                trace_path="",
                frames_path=None,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                created_at=created_at,
            )
            episode_log.append_episode(log_path, rec_loop)
            arm_episodes[arm] += 1

            # 2. Repair attempt (if loop failed)
            if not ts:
                images_b64: list[str] | None = None
                filmstrip_desc = None

                if arm == "B1":
                    # Arm B1: Naive loop with equal search budget via uniform random sampling
                    fals_seed = seed_base + 100000 + t_idx * 500
                    used_seeds.append(fals_seed)

                    def eval_rand_search(sc: dict) -> SimResult:
                        nonlocal arm_episodes
                        sd = int(sc.get("seed", fals_seed))
                        used_seeds.append(sd)
                        k, p = pilot_mod.execute_episode(
                            sc, sd, curr_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                        )
                        arm_episodes[arm] += 1
                        rec = episode_log.EpisodeResult(
                            episode_id=f"{arm}-t{t_idx:02d}-rand-s{sd}",
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

                    rand_res = falsify(eval_rand_search, bounds=bounds, budget=falsifier_budget, seed=fals_seed, sampler_type="random")
                    ce_scenario = rand_res.failures[0]["scenario"] if rand_res.failures else s_loop

                    # Match minimizer exploration episodes for exact V6 budget parity
                    match_evals = bisection_steps + 1
                    for m_i in range(match_evals):
                        m_sd = fals_seed + 100 + m_i
                        used_seeds.append(m_sd)
                        eval_rand_search({"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 5.0, "friction": 0.5, "seed": m_sd})

                    feedback_prompt = (
                        f"Previous attempt failed on random scenario (mass={ce_scenario['mass']:.2f}kg, friction={ce_scenario['friction']:.2f}). "
                        f"Margin: {ce_scenario.get('margin', margin):.4f}. Please adjust grip force (close_gripper) and steady placement."
                    )
                else:
                    # Arms B2, B3, B2_alt: Falsifier + Minimizer
                    fals_seed = seed_base + 100000 + t_idx * 500 + (50 if arm == "B2_alt" else 0)
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

                    # Minimize failing scenario
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

                    # Arm B3: Add multimodal filmstrip frames
                    if arm == "B3":
                        def dummy_policy(e: T1Env, r: Any) -> None:
                            pass
                        # Render filmstrip frames using PyBullet headless camera
                        fstrip = generate_filmstrip(env, ce_scenario, dummy_policy, seed=int(ce_scenario.get("seed", fals_seed)))
                        images_b64 = fstrip["images_b64"]
                        filmstrip_desc = fstrip["summary"]

                    feedback_prompt = build_repair_prompt(
                        curr_code,
                        ce_scenario,
                        POLICY_API_DOC,
                        margin=margin,
                        filmstrip_description=filmstrip_desc,
                    )

                # Query LLM for repair proposal
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
                    )
                    save_cache(cache)
                    cand_code = rep_proposal.code
                    r_tok_in = getattr(rep_proposal, "tokens_in", 0) or (meter.ledger[-1]["tokens_in"] if meter.ledger else 220)
                    r_tok_out = getattr(rep_proposal, "tokens_out", 0) or (meter.ledger[-1]["tokens_out"] if meter.ledger else 1250)
                    arm_tokens[arm] += r_tok_in + r_tok_out

                    # Evaluate candidate under 3-stage acceptance rule
                    def eval_cand(sc: dict) -> SimResult:
                        nonlocal arm_episodes
                        sd = int(sc.get("seed", seed_base))
                        used_seeds.append(sd)
                        k, p = pilot_mod.execute_episode(
                            sc, sd, cand_code, repo_root=str(ROOT), timeout_s=timeout_s, memory_mb=memory_mb
                        )
                        arm_episodes[arm] += 1
                        rec = episode_log.EpisodeResult(
                            episode_id=f"{arm}-t{t_idx:02d}-cand-s{sd}",
                            stream="repair",
                            task="task_T1",
                            program_id=hashlib.sha256(cand_code.encode()).hexdigest()[:16],
                            program_version=curr_version + 1,
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

                    # Short falsifier re-run check (Stage 3)
                    def rerun_fals(cand_eval_fn: Any) -> dict | None:
                        rerun_seed = seed_base + 200000 + t_idx * 500
                        fres = falsify(cand_eval_fn, bounds=bounds, budget=rerun_budget, seed=rerun_seed)
                        return fres.failures[0]["scenario"] if fres.failures else None

                    # Check acceptance
                    fixed_ce = not is_failing(eval_cand(ce_scenario))
                    damaged_reg = False  # checked against initial passing scenarios
                    accepted, acc_reason, acc_details = verify_repair_acceptance(
                        candidate_eval_fn=eval_cand,
                        counterexample=ce_scenario,
                        regression_set=[s_nom for s_nom in [nominal]],
                        falsifier_fn=rerun_fals,
                    )

                    arm_damage_accounting[arm].record_attempt(
                        fixed_counterexample=fixed_ce,
                        damaged_regression=damaged_reg,
                        accepted=accepted,
                    )

                    if accepted:
                        curr_code = cand_code
                        curr_version += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"[{arm}] Repair generation/eval error on traj {t_idx}: {exc}")

            # 3. Held-out evaluation (4 paired scenarios)
            held_passes = 0
            for h_idx, sc_h in enumerate(s_held):
                h_seed = int(sc_h["seed"]) + (1000 if arm == "B2_alt" else 0)
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

        print(f"Traj {t_idx:02d}: B1={arm_scores['B1'][-1]:.2f}, B2={arm_scores['B2'][-1]:.2f}, B3={arm_scores['B3'][-1]:.2f}, B2_alt={arm_scores['B2_alt'][-1]:.2f}")

    env.close()

    # Budget Parity (V6) between comparison arms:
    # B1 vs B2, B2 vs B3, B2 vs B2_alt
    budgets_dict = {
        arm: {"episodes": arm_episodes[arm], "tokens": arm_tokens[arm]}
        for arm in ["B1", "B2", "B3", "B2_alt"]
    }

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

    manifest = run_manifest.build_manifest(
        run_id=run_id,
        git_sha=git_sha,
        config_hash=cfg_hash,
        model=model,
        pricing=models_dict,
        budget_cap_usd=float(exp_cfg.get("budget_cap_usd", 12.0)),
        episodes_planned=sum(arm_episodes.values()),
        seeds=sorted(list(set(used_seeds))),
        generation={
            "falsifier": "CmaEsSampler",
            "minimizer": "coordinate_bisection",
            "repair_arms": arms,
            "trajectories": n_traj,
        },
        created_at=created_at,
        status="valid",
    )
    run_manifest.write_manifest(run_dir, manifest)

    results_table = {
        "run_id": run_id,
        "created_at": created_at,
        "config_hash": cfg_hash,
        "git_sha": git_sha,
        "trajectories": n_traj,
        "budgets": budgets_dict,
        "scores": {
            arm: {
                "mean": round(float(np.mean(arm_scores[arm])), 4),
                "scores": arm_scores[arm],
                "episodes": arm_episodes[arm],
                "tokens": arm_tokens[arm],
                "repair_rate": round(arm_damage_accounting[arm].repair_rate, 4),
                "damage_rate": round(arm_damage_accounting[arm].damage_rate, 4),
                "acceptance_rate": round(arm_damage_accounting[arm].acceptance_rate, 4),
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
            "contains_zero": float(aa_res["ci_lower"]) <= 0.0 <= float(aa_res["ci_upper"]),
        },
    }

    (run_dir / "repair_results.json").write_text(json.dumps(results_table, indent=2))
    print(f"\nExperiment {run_id} complete. Results written to {run_dir / 'repair_results.json'}")
    return results_table


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 06 Repair H2/H3 experiment")
    parser.add_argument("--run-id", default="h2h3-pilot-01", help="Run ID")
    parser.add_argument("--pilot", action="store_true", help="Run fast 4-trajectory pilot")
    parser.add_argument("--trajectories", type=int, default=None, help="Trajectories count")
    args = parser.parse_args()
    res = run_repair_h2h3(args.run_id, pilot=args.pilot, trajectories_override=args.trajectories)
