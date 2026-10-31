"""Mint one replacement repair program for Phase 08 certification (run cert-mint-01).

Single B1-equivalent, text-only trajectory (Plan Sec 10; numbers replicate the
P06 B1 arm exactly): initial Spark generation, uniform random search with the
equal search budget for the counterexample, at most ONE repair round, and the
3-stage acceptance gate (counterexample + regression set + short falsifier
re-run with fixed budget 5). Rejection is a valid outcome: the run is logged
and a MintRejected error is raised; no second trajectory starts here.

On acceptance the COMPLETE program source is frozen to
runs/<run_id>/program_final.py with a SHA-256 pin in freeze.json and a
manifest referencing the exact source file (V11: before any cert episode).
"""

from __future__ import annotations

import argparse
import ast
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

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.data.sampler import sample
from closedloop.exec import pilot as pilot_mod
from closedloop.exec.episode import POLICY_API_DOC
from closedloop.falsify.falsifier import falsify
from closedloop.falsify.minimizer import minimize
from closedloop.gen.generator import InvalidProgram, generate_task_program
from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.repair.repair import DamageAccounting, RepairEvaluator, build_repair_prompt
from closedloop.sim.env import SimResult


class FreezeError(ValueError):
    """A freeze directory that must not become a certification input."""


class MintRejected(RuntimeError):
    """The single repair attempt failed acceptance (valid outcome: stop)."""


def git_head() -> str:
    """Repo HEAD SHA; abort if unavailable."""
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not sha:
        raise RuntimeError("cannot determine git HEAD")
    return sha


def to_serializable(val: Any) -> Any:
    """Recursively convert dataclasses and objects to JSON-serializable primitives."""
    import dataclasses

    if dataclasses.is_dataclass(val):
        return {k: to_serializable(v) for k, v in dataclasses.asdict(val).items()}
    if isinstance(val, dict):
        return {k: to_serializable(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [to_serializable(v) for v in val]
    return val


def save_cache_safe(cache_data: dict[str, Any], path: Path) -> None:
    """Persist prompt-hash LLM cache using atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = to_serializable(cache_data)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(serializable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp_path.replace(path)


def freeze_program(
    run_dir: str | Path,
    code: str,
    *,
    rationale: str,
    seeds: list[int],
    acceptance: dict[str, Any],
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    model: str,
    config_hash: str,
) -> dict[str, Any]:
    """Persist the COMPLETE source plus its hash pin; never truncate."""
    run_dir = Path(run_dir)
    ast.parse(code)  # fail loudly on unparsable code before freezing
    source_path = run_dir / "program_final.py"
    source_path.write_text(code, encoding="utf-8")
    sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    freeze = {
        "source_file": source_path.name,
        "sha256": sha,
        "program_id": sha[:16],
        "model": model,
        "rationale": rationale,
        "seeds": list(seeds),
        "acceptance": dict(acceptance),
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "cost_usd": float(cost_usd),
        "config_hash": config_hash,
    }
    (run_dir / "freeze.json").write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return freeze


def validate_freeze(run_dir: str | Path) -> dict[str, Any]:
    """Re-verify a freeze directory; raise FreezeError on any mismatch."""
    run_dir = Path(run_dir)
    try:
        freeze = json.loads((run_dir / "freeze.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise FreezeError(f"unreadable freeze.json: {exc}") from exc
    try:
        code = (run_dir / freeze["source_file"]).read_text(encoding="utf-8")
    except (FileNotFoundError, KeyError, TypeError) as exc:
        raise FreezeError(f"missing source file: {exc}") from exc
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise FreezeError(f"source does not parse: {exc}") from exc
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "policy" for node in tree.body
    ):
        raise FreezeError("source defines no top-level policy(env, rng)")
    sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    if sha != freeze.get("sha256"):
        raise FreezeError("sha256 mismatch: source was modified after freezing")
    if freeze.get("program_id") != sha[:16]:
        raise FreezeError("program_id is not sha256[:16] of the frozen source")
    acc = freeze.get("acceptance") or {}
    if freeze.get("accepted", True) is False or acc.get("reason") != "accepted":
        raise FreezeError(f"freeze is not an acceptance: {acc.get('reason')!r}")
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise FreezeError(f"unreadable manifest.json: {exc}") from exc
    planned = manifest.get("episodes_planned")
    try:
        episodes = episode_log.read_episodes(run_dir / "episodes.jsonl")
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise FreezeError(f"unreadable episodes: {exc}") from exc
    if len(episodes) != planned:
        raise FreezeError(f"episodes {len(episodes)} != planned {planned}")
    if manifest.get("config_hash") != freeze.get("config_hash"):
        raise FreezeError("manifest config_hash differs from freeze config_hash")
    return freeze


def run_mint(
    run_id: str = "cert-mint-01",
    *,
    mint_config_path: str = "configs/mint.yaml",
    pricing_config_path: str = "configs/pricing.yaml",
    tasks_config_path: str = "configs/tasks.yaml",
    runs_dir: str = "runs",
    client: object | None = None,
) -> dict[str, Any]:
    """Execute the single pre-registered B1-equivalent trajectory."""
    cfg_file = ROOT / mint_config_path
    pricing_file = ROOT / pricing_config_path
    tasks_file = ROOT / tasks_config_path
    mint_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    tasks_cfg = yaml.safe_load(tasks_file.read_text(encoding="utf-8"))

    arm = str(mint_cfg.get("arm", "B1"))
    bounds = {k: tuple(v) for k, v in mint_cfg["difficulty"]["bounds"].items()}
    nominal = {k: float(v) for k, v in mint_cfg["repair"]["acceptance"]["nominal"].items()}
    falsifier_budget = int(mint_cfg["repair"]["falsifier_budget"])
    rerun_budget = int(mint_cfg["repair"]["acceptance"]["falsifier_rerun_budget"])
    param_order = list(mint_cfg["repair"]["acceptance"].get("param_order", ["x", "y", "yaw", "friction", "mass"]))
    bisection_steps = int(mint_cfg["repair"]["acceptance"].get("bisection_steps", 0))
    search_budget = falsifier_budget + (6 if arm == "B2" else int(mint_cfg["repair"]["acceptance"]["bisection_steps"])) + 1
    seed_base = int(mint_cfg["seed_base"])
    nominal_seed = int(mint_cfg["nominal_seed"])
    held_out_count = int(mint_cfg["held_out_per_traj"])
    model = str(mint_cfg["model"])
    max_tokens = int(mint_cfg["max_output_tokens"])
    timeout_s = float(mint_cfg["timeout_s"])
    memory_mb = int(mint_cfg["memory_mb"])

    meter = CostMeter(cap_usd=float(mint_cfg.get("budget_cap_usd", 5.0)))
    pricing_dict = meter.load_prices(pricing_file)
    if client is None:
        client = LLMClient(meter)  # fail fast: no key => no run dir, no spend
    elif hasattr(client, "meter") and getattr(client, "meter", None) is None:
        client.meter = meter
    cache: dict[str, Any] = {}  # fresh empty cache: both calls are live (H8)
    git_sha = git_head()
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base_task_text = tasks_cfg["task_T1"]["description"]

    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run dir already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    log_path = run_dir / "episodes.jsonl"
    cache_path = run_dir / "llm_cache.json"
    used_seeds: list[int] = []
    n_episodes = 0

    def log_ep(episode_id: str, code: str, version: int, scenario: dict,
               seed: int, kind: str, payload: dict, tokens: tuple[int, int] = (0, 0),
               cost: float = 0.0, trace: str = "") -> tuple[bool, float]:
        nonlocal n_episodes
        ts = bool(payload.get("truth_success", False)) if kind == "sim" else False
        alt = bool(payload.get("truth_success_alt", False)) if kind == "sim" else False
        margin = float(payload.get("margin", -1.0)) if kind == "sim" else -1.0
        episode_log.append_episode(
            log_path,
            episode_log.EpisodeResult(
                episode_id=episode_id, stream="repair", task="task_T1",
                program_id=hashlib.sha256(code.encode()).hexdigest()[:16],
                program_version=version, scenario=dict(scenario), seed=seed,
                truth_success=ts, truth_success_alt=alt, margin=margin,
                judge_mode="state", judge_pass=None, judge_confidence=None,
                trace_path=trace, frames_path=None,
                tokens_in=tokens[0], tokens_out=tokens[1], cost_usd=cost,
                created_at=created_at,
            ),
        )
        used_seeds.append(seed)
        n_episodes += 1
        return ts, margin

    outcome: dict[str, Any] = {"run_id": run_id, "accepted": False}
    try:
        # Paired scenarios (P06 rule: 2 + held_out, arm index 0).
        scenarios = sample("repair", n=2 + held_out_count, seed=seed_base, bounds=bounds)
        s_loop, s_held = scenarios[0], scenarios[2:]
        loop_seed = int(s_loop["seed"])

        # Initial generation (live call; InvalidProgram aborts the run, H13).
        try:
            initial_proposal = generate_task_program(
                client, base_task_text, POLICY_API_DOC, max_tokens,
                model=model, cache=cache,
            )
            save_cache_safe(cache, cache_path)
        except InvalidProgram as exc:
            raise RuntimeError(f"Initial program generation failed: {exc}") from exc
        curr_code = initial_proposal.code
        init_tokens = (
            int(getattr(initial_proposal, "tokens_in", 0) or 0),
            int(getattr(initial_proposal, "tokens_out", 0) or 0),
        )
        init_cost = float(getattr(initial_proposal, "cost_usd", 0.0))
        (run_dir / "program_initial.py").write_text(curr_code, encoding="utf-8")

        rerun_seed = seed_base + 40000 if arm == "B2" else seed_base + 200000
        evaluator = RepairEvaluator(
            falsifier_budget=rerun_budget, seed=rerun_seed,
            accounting=DamageAccounting(),
        )
        s_nom = dict(nominal)
        s_nom["seed"] = nominal_seed
        s_nom["id"] = "mint_nominal"
        evaluator.add_to_regression_set(s_nom)

        # 1. Initial loop evaluation.
        kind, payload = pilot_mod.execute_episode(
            s_loop, loop_seed, curr_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        ts_loop, margin_loop = log_ep(
            f"{arm}-t00-loop-v0", curr_code, 0, s_loop, loop_seed,
            kind, payload, tokens=init_tokens, cost=init_cost,
            trace=f"steps:{len(payload.get('trace', []))}",
        )
        if ts_loop:
            loop_reg = dict(s_loop)
            loop_reg["id"] = "mint_loop"
            evaluator.add_to_regression_set(loop_reg)
        r_size = len(evaluator.regression_set)

        failing: list[dict[str, Any]] = []
        lowest_margin = margin_loop
        lowest_sc = dict(s_loop)

        if arm == "B2":
            # 2. B2 Optuna CMA-ES falsification (10 evals) + coordinate minimization (6 evals + 1 recheck = 7 evals)
            fals_seed = seed_base + 10000

            def eval_fals(sc: dict) -> SimResult:
                sd = int(sc.get("seed", fals_seed))
                k_f, p_f = pilot_mod.execute_episode(
                    sc, sd, curr_code, repo_root=str(ROOT),
                    timeout_s=timeout_s, memory_mb=memory_mb,
                )
                ts_f, margin_f = log_ep(f"{arm}-t00-fals-s{sd}", curr_code, 0, sc, sd, k_f, p_f)
                return SimResult(
                    truth_success=ts_f,
                    truth_success_alt=bool(p_f.get("truth_success_alt", False)) if k_f == "sim" else False,
                    margin=margin_f,
                    final_pos=(0, 0, 0),
                    steps=0,
                    agreed=True,
                )

            fals_res = falsify(eval_fals, bounds=bounds, budget=falsifier_budget, seed=fals_seed)
            raw_fail = fals_res.failures[0]["scenario"] if fals_res.failures else s_loop
            raw_margin = fals_res.failures[0]["margin"] if fals_res.failures else margin_loop

            min_seed_base = seed_base + 20000
            min_eval_idx = 0
            last_min_margin = raw_margin

            def eval_min(sc: dict) -> SimResult:
                nonlocal min_eval_idx, last_min_margin
                sd = min_seed_base + min_eval_idx
                min_eval_idx += 1
                k_m, p_m = pilot_mod.execute_episode(
                    sc, sd, curr_code, repo_root=str(ROOT),
                    timeout_s=timeout_s, memory_mb=memory_mb,
                )
                ts_m, margin_m = log_ep(f"{arm}-t00-min-s{sd}", curr_code, 0, sc, sd, k_m, p_m)
                last_min_margin = margin_m
                return SimResult(
                    truth_success=ts_m,
                    truth_success_alt=bool(p_m.get("truth_success_alt", False)) if k_m == "sim" else False,
                    margin=margin_m,
                    final_pos=(0, 0, 0),
                    steps=0,
                    agreed=True,
                )

            min_sc = minimize(
                raw_fail,
                eval_fn=eval_min,
                nominal=nominal,
                bisection_steps=0,
                param_keys=param_order,
                bounds=bounds,
            )
            ce = dict(min_sc)
            ce["seed"] = seed_base + 30000
            ce_margin = last_min_margin
            trace_summary = "Falsifier minimal counterexample"
            if not ts_loop or fals_res.failures:
                failing.append({"scenario": ce, "margin": ce_margin})
        else:
            # 2. B1 uniform random search with the equal search budget (verbatim P06).
            fals_seed = seed_base + 100000
            rng_b1 = np.random.default_rng(fals_seed)
            for eval_i in range(search_budget):
                rand_seed = fals_seed + 10 + eval_i
                rand_sc = {
                    "x": float(rng_b1.uniform(bounds["x"][0], bounds["x"][1])),
                    "y": float(rng_b1.uniform(bounds["y"][0], bounds["y"][1])),
                    "yaw": float(rng_b1.uniform(bounds["yaw"][0], bounds["yaw"][1])),
                    "mass": float(rng_b1.uniform(bounds["mass"][0], bounds["mass"][1])),
                    "friction": float(rng_b1.uniform(bounds["friction"][0], bounds["friction"][1])),
                    "seed": rand_seed, "id": f"b1_rand_{eval_i}",
                }
                k_r, p_r = pilot_mod.execute_episode(
                    rand_sc, rand_seed, curr_code, repo_root=str(ROOT),
                    timeout_s=timeout_s, memory_mb=memory_mb,
                )
                ts_r, margin_r = log_ep(f"B1-t00-rand-s{rand_seed}", curr_code, 0,
                                        rand_sc, rand_seed, k_r, p_r)
                if margin_r < lowest_margin:
                    lowest_margin, lowest_sc = margin_r, rand_sc
                if not ts_r:
                    failing.append({"scenario": rand_sc, "margin": margin_r})

            if failing:
                ce = failing[0]["scenario"]
                ce_margin = failing[0]["margin"]
            else:
                ce = lowest_sc
                ce_margin = lowest_margin
            trace_summary = "Naive loop failure from random parameter search"

        if not ts_loop or failing:
            # 3. Single repair round (text-only prompt, verbatim P06).
            feedback = build_repair_prompt(
                curr_code, ce, POLICY_API_DOC, margin=ce_margin,
                trace_summary=trace_summary,
            )
            try:
                rep = generate_task_program(
                    client, base_task_text, POLICY_API_DOC, max_tokens,
                    model=model, feedback=feedback, cache=cache,
                    cache_key_extra=f"arm_{arm}_mint",
                )
                save_cache_safe(cache, cache_path)
            except InvalidProgram as exc:
                raise RuntimeError(f"Repair generation failed: {exc}") from exc
            cand_code = rep.code
            r_tokens = (int(getattr(rep, "tokens_in", 0) or 0), int(getattr(rep, "tokens_out", 0) or 0))
            r_cost = float(getattr(rep, "cost_usd", 0.0))
            (run_dir / "program_candidate_v1.py").write_text(cand_code, encoding="utf-8")

            def eval_cand(sc: dict) -> SimResult:
                sd = int(sc.get("seed", ce.get("seed", seed_base + 50000)))
                k, p = pilot_mod.execute_episode(
                    sc, sd, cand_code, repo_root=str(ROOT),
                    timeout_s=timeout_s, memory_mb=memory_mb,
                )
                first = sd == int(ce.get("seed", seed_base + 50000))
                ts_c, margin_c = log_ep(
                    f"{arm}-t00-cand-s{sd}", cand_code, 1, sc, sd, k, p,
                    tokens=r_tokens if first else (0, 0),
                    cost=r_cost if first else 0.0,
                    trace="repair_cand_validation",
                )
                rec = episode_log.read_episodes(log_path)[-1]
                return SimResult(truth_success=rec.truth_success,
                                 truth_success_alt=rec.truth_success_alt,
                                 margin=rec.margin, final_pos=(0, 0, 0),
                                 steps=0, agreed=True)

            def rerun_fals(cand_eval_fn: Any) -> dict | None:
                fres = falsify(cand_eval_fn, bounds=bounds, budget=rerun_budget,
                              seed=rerun_seed)
                return fres.failures[0]["scenario"] if fres.failures else None

            accepted, reason, details = evaluator.evaluate_candidate(
                candidate_eval_fn=eval_cand, counterexample=ce,
                falsifier_fn=rerun_fals,
            )
            outcome.update({
                "repair_attempted": True,
                "reason": reason,
                "details": details,
                "code": cand_code,
                "rationale": getattr(rep, "rationale", ""),
                "repair_tokens": r_tokens,
                "repair_cost": r_cost,
                "init_tokens": init_tokens,
                "init_cost": init_cost,
            })
            if accepted:
                outcome["accepted"] = True
        else:
            outcome.update({
                "repair_attempted": False,
                "accepted": True,
                "code": curr_code,
                "rationale": getattr(initial_proposal, "rationale", ""),
                "init_tokens": init_tokens,
                "init_cost": init_cost,
                "reason": "v0 undefeated: loop passed and search found no failure",
                "details": {"stage": 0},
            })

        # 4. Held-out evaluation (4 paired scenarios, reporting only).
        held_passes = 0
        final_code = outcome.get("code", curr_code)
        final_version = 1 if outcome.get("accepted") and outcome.get("repair_attempted") else 0
        for h_idx, sc_h in enumerate(s_held):
            h_seed = int(sc_h["seed"])
            k_h, p_h = pilot_mod.execute_episode(
                sc_h, h_seed, final_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            ts_h, _ = log_ep(f"{arm}-t00-held{h_idx:02d}-v{final_version}", final_code,
                             final_version, sc_h, h_seed, k_h, p_h)
            held_passes += int(ts_h)
        outcome["held_out_rate"] = held_passes / len(s_held)

        # Fixed-plan assertion: 1 + 17 + (1 + R) + 5 + 4 with repair, else 1 + 17 + 4.
        planned = (1 + search_budget + (1 + r_size) + rerun_budget + held_out_count
                   if outcome.get("repair_attempted") else 1 + search_budget + held_out_count)
        if n_episodes != planned:
            raise RuntimeError(f"episodes {n_episodes} != planned {planned}")
        outcome["episodes_planned"] = planned
        outcome["episodes_logged"] = n_episodes

        # Write mint_trace.json for both accepted and rejected attempts
        mint_trace = {
            "run_id": run_id,
            "arm": arm,
            "initial_program": {
                "source_file": "program_initial.py",
                "program_id": hashlib.sha256(curr_code.encode("utf-8")).hexdigest()[:16],
                "rationale": getattr(initial_proposal, "rationale", ""),
                "tokens_in": init_tokens[0],
                "tokens_out": init_tokens[1],
                "cost_usd": init_cost,
            },
            "repair_attempted": outcome.get("repair_attempted", False),
            "counterexample": ce if outcome.get("repair_attempted") else None,
            "repair_proposal": {
                "source_file": "program_candidate_v1.py",
                "program_id": hashlib.sha256(outcome["code"].encode("utf-8")).hexdigest()[:16],
                "rationale": outcome.get("rationale", ""),
                "tokens_in": r_tokens[0] if outcome.get("repair_attempted") else 0,
                "tokens_out": r_tokens[1] if outcome.get("repair_attempted") else 0,
                "cost_usd": r_cost if outcome.get("repair_attempted") else 0.0,
            } if outcome.get("repair_attempted") else None,
            "acceptance": {
                "accepted": outcome.get("accepted", False),
                "reason": outcome.get("reason", ""),
                "details": outcome.get("details", {}),
            },
            "held_out_rate": outcome.get("held_out_rate", 0.0),
            "spent_usd": round(init_cost + (r_cost if outcome.get("repair_attempted") else 0.0), 6),
        }
        (run_dir / "mint_trace.json").write_text(
            json.dumps(to_serializable(mint_trace), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        tot_cost = round(init_cost + (r_cost if outcome.get("repair_attempted") else 0.0), 6)
        tot_tok_in = init_tokens[0] + (r_tokens[0] if outcome.get("repair_attempted") else 0)
        tot_tok_out = init_tokens[1] + (r_tokens[1] if outcome.get("repair_attempted") else 0)

        # Write manifest.json
        man = {
            "run_id": run_id,
            "git_sha": git_sha,
            "config_hash": cfg_hash,
            "created_at": created_at,
            "model": model,
            "pricing_per_mtok": pricing_dict,
            "budget_cap_usd": float(mint_cfg.get("budget_cap_usd", 5.0)),
            "spent_usd": tot_cost,
            "tokens_spent": {
                "tokens_in": tot_tok_in,
                "tokens_out": tot_tok_out,
                "total": tot_tok_in + tot_tok_out,
            },
            "episodes_planned": planned,
            "seeds": used_seeds,
            "status": "valid",
            "generation": {
                "arm": arm,
                "seed_base": seed_base,
                "max_rounds": int(mint_cfg["repair"]["max_rounds"]),
                "accepted": outcome.get("accepted", False),
                "held_out_rate": outcome.get("held_out_rate", 0.0),
            },
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(to_serializable(man), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if not outcome.get("accepted"):
            raise MintRejected(f"mint candidate rejected: {outcome.get('reason')}")

        freeze = freeze_program(
            run_dir,
            outcome["code"],
            rationale=outcome.get("rationale", ""),
            seeds=used_seeds,
            acceptance={"reason": "accepted", "details": outcome.get("details", {})},
            tokens_in=tot_tok_in,
            tokens_out=tot_tok_out,
            cost_usd=tot_cost,
            model=model,
            config_hash=cfg_hash,
        )
        outcome["program_id"] = freeze["program_id"]
        outcome["sha256"] = freeze["sha256"]
        outcome["spent_usd"] = tot_cost
        outcome["episodes_logged"] = n_episodes
        validate_freeze(run_dir)
        return outcome
    finally:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint one B1-equivalent repair program.")
    parser.add_argument("--run-id", default="cert-mint-01")
    args = parser.parse_args()
    try:
        outcome = run_mint(run_id=args.run_id)
    except MintRejected as exc:
        print(f"VERDICT: REJECTED (valid outcome, run logged) — STOP. {exc}")
        raise SystemExit(0)
    print(f"VERDICT: ACCEPTED program_id={outcome['program_id']} "
          f"sha256={outcome['sha256'][:16]}... held_out={outcome['held_out_rate']:.2f} "
          f"spent_usd={outcome['spent_usd']:.4f} episodes={outcome['episodes_logged']}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
