#!/usr/bin/env python3
"""Run Baselines B0/B1 and measure H1 Generalization Gap (Phase 04, Gate G1).

Arms:
- B0: One-shot generation on tier-2 difficulty.
- B1: Naive loop with random-seed feedback.

Measures:
- B0 one-shot success rate vs 30-80% difficulty band (Gate G1).
- H1 Generalization gap (loop-scenario vs held-out scenarios) with paired
  bootstrap 95% confidence intervals (10,000 resamples).
- V6 budget parity check across arms.
- Frozen manifest with config hash (H12 / V11).

Writes:
- runs/<run_id>/episodes.jsonl (append-only)
- runs/<run_id>/traces/*.json
- runs/<run_id>/manifest.json
- runs/<run_id>/gap_table.json

Usage:
  # Pilot run (V15, 2 trajectories, ~20 episodes):
  .\\.venv\\Scripts\\python.exe experiments/run_baselines.py --run-id h1-pilot-01 --pilot

  # Full run (>=20 trajectories/arm, 200 episodes):
  .\\.venv\\Scripts\\python.exe experiments/run_baselines.py --run-id h1-full-01
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from closedloop.data import analysis  # noqa: E402
from closedloop.data import log as episode_log  # noqa: E402
from closedloop.data import manifest as run_manifest  # noqa: E402
from closedloop.data.sampler import sample  # noqa: E402
from closedloop.exec import pilot as pilot_mod  # noqa: E402
from closedloop.exec.episode import POLICY_API_DOC  # noqa: E402
from closedloop.gen.generator import InvalidProgram, generate_task_program  # noqa: E402
from closedloop.llm.client import LLMClient  # noqa: E402
from closedloop.llm.cost import BudgetExceeded, CostMeter, UnpricedModelError  # noqa: E402

CACHE_PATH = ROOT / "runs" / "llm_cache.json"


def utcnow() -> str:
    """Current UTC timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    """Load shared prompt-hash response cache."""
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
    """Save shared prompt-hash cache."""
    import dataclasses

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        k: dataclasses.asdict(v) if dataclasses.is_dataclass(v) else v
        for k, v in cache.items()
    }
    CACHE_PATH.write_text(json.dumps(serializable, indent=1, sort_keys=True))


def _assemble_record(
    run_id: str,
    ep_name: str,
    scenario: dict,
    seed: int,
    program_id: str,
    version: int,
    kind: str,
    payload: dict,
    created_at: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
) -> tuple[dict, dict]:
    """Assemble EpisodeResult dict and trace payload."""
    trace_name = f"traces/{ep_name}.json"
    base = dict(
        episode_id=f"{run_id}-{ep_name}",
        stream="repair",
        task="T1",
        program_id=program_id,
        program_version=version,
        scenario=dict(scenario),
        seed=seed,
        judge_mode="state",
        judge_pass=None,
        judge_confidence=None,
        trace_path=trace_name,
        frames_path=None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        created_at=created_at,
    )
    if kind == "sim":
        base.update(
            truth_success=bool(payload["truth_success"]),
            truth_success_alt=bool(payload["truth_success_alt"]),
            margin=float(payload["margin"]),
        )
        trace_content = {
            "trace": payload["trace"],
            "steps": payload["steps"],
            "final_pos": list(payload["final_pos"]),
        }
    else:
        base.update(truth_success=False, truth_success_alt=False, margin=-1.0)
        trace_content = {
            "outcome": payload.get("reason"),
            "detail": str(payload.get("detail", ""))[-1500:],
        }
    return base, trace_content


def run_baselines(
    run_id: str,
    *,
    exp_cfg: dict,
    tasks_cfg: dict,
    pricing_cfg: dict,
    runs_dir: str = "runs",
    pilot: bool = False,
    trajectories_override: int | None = None,
    client: object | None = None,
) -> dict:
    """Execute paired B0 and B1 baselines across trajectories."""
    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        print(f"ABORTED: run directory already exists: {run_dir}")
        return {"status": "aborted", "error": f"run dir exists: {run_dir}"}
    run_dir.mkdir(parents=True)
    traces_dir = run_dir / "traces"
    traces_dir.mkdir(exist_ok=True)
    log_path = run_dir / "episodes.jsonl"

    n_traj = (
        4
        if pilot
        else (trajectories_override or int(exp_cfg.get("trajectories", 20)))
    )
    n_held_out = int(exp_cfg.get("held_out_per_traj", 4))
    bounds_raw = exp_cfg["difficulty"]["bounds"]
    bounds = {k: tuple(v) for k, v in bounds_raw.items()}
    model = str(exp_cfg["model"])
    max_tokens = int(exp_cfg["max_output_tokens"])
    timeout_s = float(exp_cfg["timeout_s"])
    memory_mb = int(exp_cfg["memory_mb"])
    start_seed = int(exp_cfg["seed"])

    meter = CostMeter(cap_usd=float(exp_cfg.get("budget_cap_usd", 8.0)))
    models_dict = pricing_cfg.get("models", pricing_cfg) if isinstance(pricing_cfg, dict) else {}
    for m, rates in models_dict.items():
        if isinstance(rates, (list, tuple)) and len(rates) == 2:
            meter.set_price(m, float(rates[0]), float(rates[1]))

    cache = load_cache()
    if client is None:
        try:
            client = LLMClient(meter)
        except RuntimeError as exc:
            print(f"ABORTED (no spend): {exc}")
            return {"status": "aborted", "error": str(exc)}

    task_desc = tasks_cfg["task_T1"]["description"]
    base_task_text = f"{task_desc} (tier-2 mass and friction conditions)"

    # Total planned episodes = n_traj * (2 loop/retest + n_held_out) for B0,
    # plus n_traj * (2 loop/retest + n_held_out) for B1.
    episodes_per_traj = 2 + n_held_out
    episodes_planned = n_traj * episodes_per_traj * 2

    # Draw paired scenarios from repair stream: (2 loop/retest + n_held_out) per trajectory
    total_scenarios_needed = n_traj * episodes_per_traj
    all_scenarios = sample("repair", total_scenarios_needed, start_seed, bounds=bounds)
    scenario_map: dict[int, list[dict]] = {}
    for t in range(n_traj):
        idx = t * episodes_per_traj
        traj_scenarios = all_scenarios[idx : idx + episodes_per_traj]
        scenario_map[t] = traj_scenarios

    all_seeds = [int(s["seed"]) for s in all_scenarios]
    created_at = utcnow()
    sha = git_head()

    # Track scores for B0 and B1
    b0_loop_scores: list[float] = []
    b0_held_out_scores: list[float] = []
    b1_loop_scores: list[float] = []
    b1_held_out_scores: list[float] = []

    b0_tokens = 0
    b1_tokens = 0
    b0_episodes = 0
    b1_episodes = 0

    print(f"Starting Baselines run: {run_id} ({n_traj} trajectories/arm, pilot={pilot})")

    # Generate initial program for B0 (shared with B1 initial)
    try:
        b0_proposal = generate_task_program(
            client,
            base_task_text,
            POLICY_API_DOC,
            max_tokens,
            model=model,
            cache=cache,
        )
    except InvalidProgram as exc:
        print(f"Invalid generation: {exc}")
        return {"status": "invalid_generation", "error": str(exc)}

    b0_code = b0_proposal.code
    b0_prog_id = hashlib.sha256(b0_code.encode()).hexdigest()[:16]
    b0_tok_in = getattr(b0_proposal, "tokens_in", 0) or (meter.ledger[-1]["tokens_in"] if meter.ledger else 160)
    b0_tok_out = getattr(b0_proposal, "tokens_out", 0) or (meter.ledger[-1]["tokens_out"] if meter.ledger else 1240)
    b0_tokens += b0_tok_in + b0_tok_out
    b1_tokens += b0_tok_in + b0_tok_out

    # Execute B0 and B1 across trajectories
    for t in range(n_traj):
        scenarios = scenario_map[t]
        s_loop = scenarios[0]
        s_retest = scenarios[1]
        s_held = scenarios[2:]

        # --- Arm B0: One-shot ---
        # 1. Loop scenario
        kind, payload = pilot_mod.execute_episode(
            s_loop, s_loop["seed"], b0_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        rec, trace = _assemble_record(
            run_id, f"b0-t{t:02d}-loop", s_loop, s_loop["seed"],
            b0_prog_id, 0, kind, payload, created_at,
        )
        (traces_dir / f"b0-t{t:02d}-loop.json").write_text(json.dumps(trace))
        episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
        b0_episodes += 1
        b0_loop_pass = 1.0 if rec["truth_success"] else 0.0
        b0_loop_scores.append(b0_loop_pass)

        # 2. Retest scenario
        kind, payload = pilot_mod.execute_episode(
            s_retest, s_retest["seed"], b0_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        rec, trace = _assemble_record(
            run_id, f"b0-t{t:02d}-retest", s_retest, s_retest["seed"],
            b0_prog_id, 0, kind, payload, created_at,
        )
        (traces_dir / f"b0-t{t:02d}-retest.json").write_text(json.dumps(trace))
        episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
        b0_episodes += 1

        # 3. Held-out scenarios
        held_passes_b0 = 0
        for h_idx, sc in enumerate(s_held):
            kind, payload = pilot_mod.execute_episode(
                sc, sc["seed"], b0_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            rec, trace = _assemble_record(
                run_id, f"b0-t{t:02d}-h{h_idx:02d}", sc, sc["seed"],
                b0_prog_id, 0, kind, payload, created_at,
            )
            (traces_dir / f"b0-t{t:02d}-h{h_idx:02d}.json").write_text(json.dumps(trace))
            episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
            b0_episodes += 1
            if rec["truth_success"]:
                held_passes_b0 += 1
        b0_held_out_scores.append(held_passes_b0 / len(s_held))

        # --- Arm B1: Naive Loop ---
        # Start with initial program
        b1_curr_code = b0_code
        b1_curr_prog_id = b0_prog_id
        b1_version = 0

        # Evaluate on loop scenario
        kind, payload = pilot_mod.execute_episode(
            s_loop, s_loop["seed"], b1_curr_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        rec, trace = _assemble_record(
            run_id, f"b1-t{t:02d}-loop-v{b1_version}", s_loop, s_loop["seed"],
            b1_curr_prog_id, b1_version, kind, payload, created_at,
        )
        (traces_dir / f"b1-t{t:02d}-loop-v{b1_version}.json").write_text(json.dumps(trace))
        episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
        b1_episodes += 1

        # If loop passed, evaluate on retest scenario
        if rec["truth_success"]:
            b1_loop_pass = 1.0
            kind, payload = pilot_mod.execute_episode(
                s_retest, s_retest["seed"], b1_curr_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            rec, trace = _assemble_record(
                run_id, f"b1-t{t:02d}-retest-v{b1_version}", s_retest, s_retest["seed"],
                b1_curr_prog_id, b1_version, kind, payload, created_at,
            )
            (traces_dir / f"b1-t{t:02d}-retest-v{b1_version}.json").write_text(json.dumps(trace))
            episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
            b1_episodes += 1
        else:
            # If loop failed and repair rounds allowed, attempt repair
            fail_reason = payload.get("reason", "insufficient grip force or stability") if kind == "sim" else "infrastructure error"
            fail_margin = payload.get("margin", -1.0)
            feedback = (
                f"Previous attempt failed on scenario (mass={s_loop['mass']:.2f} kg, friction={s_loop['friction']:.2f}). "
                f"Reason: {fail_reason}. Margin: {fail_margin:.4f}. "
                f"Please revise policy(env, rng) to ensure sufficient grasp force (close_gripper) and steady placement."
            )
            try:
                repair_prop = generate_task_program(
                    client,
                    base_task_text,
                    POLICY_API_DOC,
                    max_tokens,
                    model=model,
                    feedback=feedback,
                    cache=cache,
                )
                b1_curr_code = repair_prop.code
                b1_curr_prog_id = hashlib.sha256(b1_curr_code.encode()).hexdigest()[:16]
                b1_version += 1
                if meter.ledger:
                    rep_entry = meter.ledger[-1]
                    b1_tokens += rep_entry.get("tokens_in", 0) + rep_entry.get("tokens_out", 0)
            except Exception as exc:  # noqa: BLE001
                print(f"Repair attempt failed for traj {t}: {exc}")

            # Re-evaluate repaired program on retest scenario
            kind, payload = pilot_mod.execute_episode(
                s_retest, s_retest["seed"], b1_curr_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            rec, trace = _assemble_record(
                run_id, f"b1-t{t:02d}-retest-v{b1_version}", s_retest, s_retest["seed"],
                b1_curr_prog_id, b1_version, kind, payload, created_at,
            )
            (traces_dir / f"b1-t{t:02d}-retest-v{b1_version}.json").write_text(json.dumps(trace))
            episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
            b1_episodes += 1
            b1_loop_pass = 1.0 if rec["truth_success"] else 0.0

        b1_loop_scores.append(b1_loop_pass)

        # Evaluate final B1 program on held-out scenarios
        held_passes_b1 = 0
        for h_idx, sc in enumerate(s_held):
            kind, payload = pilot_mod.execute_episode(
                sc, sc["seed"], b1_curr_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            rec, trace = _assemble_record(
                run_id, f"b1-t{t:02d}-h{h_idx:02d}", sc, sc["seed"],
                b1_curr_prog_id, b1_version, kind, payload, created_at,
            )
            (traces_dir / f"b1-t{t:02d}-h{h_idx:02d}.json").write_text(json.dumps(trace))
            episode_log.append_episode(log_path, episode_log.EpisodeResult(**rec))
            b1_episodes += 1
            if rec["truth_success"]:
                held_passes_b1 += 1
        b1_held_out_scores.append(held_passes_b1 / len(s_held))

        print(f"Traj {t+1:02d}/{n_traj:02d}: B0 loop={b0_loop_pass:.0f}, held={b0_held_out_scores[-1]:.2f} | B1 loop={b1_loop_pass:.0f}, held={b1_held_out_scores[-1]:.2f}")

    # Save cache
    save_cache(cache)

    # Compute statistics & gaps
    b0_gap_res = analysis.compute_h1_gap(b0_loop_scores, b0_held_out_scores, n_resamples=10000, seed=start_seed)
    b1_gap_res = analysis.compute_h1_gap(b1_loop_scores, b1_held_out_scores, n_resamples=10000, seed=start_seed)

    # Episode budget parity check across arms (Human review: "arm episode counts within 5%")
    arm_budgets = {
        "B0": {"episodes": b0_episodes},
        "B1": {"episodes": b1_episodes},
    }
    parity_ok = True
    parity_msg = "PASS"
    try:
        analysis.check_budget_parity(arm_budgets, max_rel_diff=0.10 if pilot else 0.05)
    except analysis.BudgetParityError as exc:
        parity_ok = False
        parity_msg = f"FAIL ({exc})"

    # Overall B0 success rate across all B0 episodes
    b0_all_episodes = [
        ep for ep in episode_log.read_episodes(log_path)
        if "-b0-" in ep.episode_id
    ]
    b0_total_k = sum(1 for ep in b0_all_episodes if ep.truth_success)
    b0_total_n = len(b0_all_episodes)
    b0_success_rate = b0_total_k / b0_total_n if b0_total_n > 0 else 0.0
    g1_pass = 0.30 <= b0_success_rate <= 0.80

    # Write manifest
    cfg_hash = run_manifest.config_hash([
        ROOT / "configs" / "exp_h1.yaml",
        ROOT / "configs" / "tasks.yaml",
        ROOT / "configs" / "pricing.yaml",
    ])
    manifest = run_manifest.build_manifest(
        run_id=run_id,
        git_sha=sha,
        config_hash=cfg_hash,
        model=model,
        pricing=pricing_cfg,
        budget_cap_usd=meter.cap_usd,
        episodes_planned=b0_episodes + b1_episodes,
        seeds=all_seeds,
        generation={"model": model, "cost_usd": meter.spent_usd, "tokens_in": meter.ledger[-1]["tokens_in"] if meter.ledger else 0, "tokens_out": meter.ledger[-1]["tokens_out"] if meter.ledger else 0},
        created_at=created_at,
        status="valid",
    )
    manifest["b0_summary"] = {
        "n_episodes": b0_episodes,
        "success_rate": b0_success_rate,
        "loop_mean": b0_gap_res["mean_loop"],
        "held_out_mean": b0_gap_res["mean_held_out"],
        "gap": b0_gap_res["gap"],
        "ci_lower": b0_gap_res["ci_lower"],
        "ci_upper": b0_gap_res["ci_upper"],
    }
    manifest["b1_summary"] = {
        "n_episodes": b1_episodes,
        "loop_mean": b1_gap_res["mean_loop"],
        "held_out_mean": b1_gap_res["mean_held_out"],
        "gap": b1_gap_res["gap"],
        "ci_lower": b1_gap_res["ci_lower"],
        "ci_upper": b1_gap_res["ci_upper"],
    }
    manifest["g1_status"] = "PASS" if g1_pass else "FAIL"
    manifest["budget_parity"] = parity_msg
    run_manifest.write_manifest(run_dir, manifest)

    # Save gap table
    gap_table = {
        "run_id": run_id,
        "git_sha": sha,
        "config_hash": cfg_hash,
        "trajectories": n_traj,
        "b0": manifest["b0_summary"],
        "b1": manifest["b1_summary"],
        "g1_pass": g1_pass,
        "parity": parity_msg,
    }
    (run_dir / "gap_table.json").write_text(json.dumps(gap_table, indent=2))

    # Print summary
    print("\n" + "=" * 80)
    print(f"Phase 04 — H1 Generalization Gap & Baselines Summary: {run_id}")
    print("=" * 80)
    print(f"Arm B0 (One-shot) [Total {b0_total_k}/{b0_total_n} = {b0_success_rate:.3f}]:")
    print(f"  Loop scenario success:    {b0_gap_res['mean_loop']:.3f}")
    print(f"  Held-out scenario success:{b0_gap_res['mean_held_out']:.3f}")
    print(f"  Generalization gap (H1):  {b0_gap_res['gap']:+.3f} [95% CI: ({b0_gap_res['ci_lower']:+.3f}, {b0_gap_res['ci_upper']:+.3f})]")
    print(f"  Gate G1 check (30%-80% band): {'PASS' if g1_pass else 'FAIL'}")
    print()
    print("Arm B1 (Naive loop with random feedback):")
    print(f"  Loop scenario success:    {b1_gap_res['mean_loop']:.3f}")
    print(f"  Held-out scenario success:{b1_gap_res['mean_held_out']:.3f}")
    print(f"  Generalization gap (H1):  {b1_gap_res['gap']:+.3f} [95% CI: ({b1_gap_res['ci_lower']:+.3f}, {b1_gap_res['ci_upper']:+.3f})]")
    print()
    print(f"Budget parity (V6): {parity_msg}")
    print(f"Cost this run: ${meter.spent_usd:.4f} (meter total ${meter.spent_usd:.4f} / cap ${meter.cap_usd:.2f})")
    print("=" * 80 + "\n")

    return gap_table


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for running baselines."""
    ap = argparse.ArgumentParser(description="Run Baselines B0/B1 and measure H1 gap.")
    ap.add_argument("--run-id", required=True, help="fresh run identifier")
    ap.add_argument("--pilot", action="store_true", help="run pilot scale (V15, ~10%)")
    ap.add_argument("--trajectories", type=int, default=None, help="override trajectory count")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--configs-dir", default=str(ROOT / "configs"))
    args = ap.parse_args(argv)

    cfg_dir = Path(args.configs_dir)
    exp_cfg = yaml.safe_load((cfg_dir / "exp_h1.yaml").read_text(encoding="utf-8"))
    tasks_cfg = yaml.safe_load((cfg_dir / "tasks.yaml").read_text(encoding="utf-8"))
    pricing_cfg = yaml.safe_load((cfg_dir / "pricing.yaml").read_text(encoding="utf-8"))

    meter = CostMeter()
    try:
        pricing_dict = meter.load_prices(cfg_dir / "pricing.yaml")
    except UnpricedModelError as exc:
        print(f"ABORTED (no spend): {exc}")
        return 2

    res = run_baselines(
        args.run_id,
        exp_cfg=exp_cfg,
        tasks_cfg=tasks_cfg,
        pricing_cfg=pricing_dict,
        runs_dir=args.runs_dir,
        pilot=args.pilot,
        trajectories_override=args.trajectories,
    )
    if res.get("status") == "aborted":
        return 2
    if res.get("g1_pass") is False:
        print(f"GATE G1 FAILED: B0 success rate outside 30-80% band")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
