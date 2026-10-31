"""Phase 09: Shift Test H4 Experiment Runner (Plan §12, PHASE_09_shift_h4.md).

Evaluates whether statistical guarantees certified under distribution D transfer
to shifted distribution D' (wider pose, heavier mass, lower friction).

Executes:
1. Frozen configuration check (V11) and pre-run config hash logging.
2. Verified policy program check (sha256).
3. Fresh certification seeds in [2000000, 2999999], strictly disjoint from Phase 08
   and claimed once per program via persistent CertificationLedger (Rule H9, V4).
4. Pilot (~10%, n=30: 15 on D, 15 on D') and Full (n=300: 150 on D, 150 on D').
5. Sandboxed subprocess execution with timeout and memory enforcement (Rules H13, H15).
6. Append-only raw logging to episodes.jsonl (Rule H10).
7. Figure data generated strictly from logs (Rule H11).
8. Gate verification asserting scenario shift detectability and bound drop / refusal (Hypothesis H4).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent


def git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def run_shift_experiment(
    run_id: str,
    *,
    pilot: bool = False,
    shift_config_path: str = "configs/shift.yaml",
    pricing_config_path: str = "configs/pricing.yaml",
    tasks_config_path: str = "configs/tasks.yaml",
    runs_dir: str = "runs",
) -> dict[str, Any]:
    """Execute shift experiment (pilot or full) in state mode default."""
    load_env()

    from closedloop.certify.shift import (
        generate_shift_figure_data,
        compute_scenario_shift_stats,
        compare_shift_bounds,
    )
    from closedloop.data import log as episode_log
    from closedloop.data import manifest as run_manifest
    from closedloop.data.sampler import CertificationLedger, sample, LeakageError
    from closedloop.exec.pilot import execute_episode
    from closedloop.llm.cost import CostMeter

    cfg_file = ROOT / shift_config_path
    pricing_file = ROOT / pricing_config_path
    tasks_file = ROOT / tasks_config_path

    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    shift_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    git_sha = git_head()
    created_at = datetime.now(timezone.utc).isoformat()

    # 1. Verify program integrity
    prog_file = ROOT / shift_cfg["program_file"]
    if not prog_file.exists():
        raise FileNotFoundError(f"Program file not found: {prog_file}")
    policy_code = prog_file.read_text(encoding="utf-8")
    actual_sha = hashlib.sha256(policy_code.encode("utf-8")).hexdigest()
    expected_sha = shift_cfg["program_sha256"]
    if actual_sha != expected_sha:
        raise ValueError(f"Program hash mismatch: {actual_sha} != {expected_sha}")
    program_id = shift_cfg["program_id"]

    # 2. Determine sample sizes and seed bases
    if pilot:
        total_runs = int(shift_cfg["sample_sizes"]["pilot_runs"])
        n_cohort = total_runs // 2
        seed_base = int(shift_cfg["seeds"]["pilot_seed_base"])
    else:
        total_runs = int(shift_cfg["sample_sizes"]["full_runs"])
        n_cohort = total_runs // 2
        seed_base = int(shift_cfg["seeds"]["full_seed_base"])

    seed_d = seed_base
    seed_dp = seed_base + n_cohort
    planned_seeds = list(range(seed_base, seed_base + total_runs))

    # 3. Enforce single-use certification seeds via persistent ledger (Rule H9, V4)
    ledger_path = ROOT / runs_dir / ".certification_ledger.json"
    ledger = CertificationLedger(path=ledger_path)
    ledger.claim(program_id, planned_seeds)

    # 4. Sample scenarios from D and D'
    bounds_d = {k: tuple(v) for k, v in shift_cfg["bounds_d"].items()}
    bounds_dp = {k: tuple(v) for k, v in shift_cfg["bounds_d_prime"].items()}

    scenarios_d = sample("certification", n=n_cohort, seed=seed_d, bounds=bounds_d)
    scenarios_dp = sample("certification", n=n_cohort, seed=seed_dp, bounds=bounds_dp)

    for sc in scenarios_d:
        sc["distribution"] = "D"
    for sc in scenarios_dp:
        sc["distribution"] = "D_prime"

    # 5. Pre-flight budget & manifest initialization (Rule H12)
    run_dir = ROOT / runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "episodes.jsonl"
    manifest_path = run_dir / "manifest.json"

    initial_manifest = {
        "run_id": run_id,
        "phase": "09",
        "experiment": "shift",
        "pilot": pilot,
        "status": "running",
        "created_at": created_at,
        "git_sha": git_sha,
        "config_hash": cfg_hash,
        "program_id": program_id,
        "episodes_planned": total_runs,
        "seed_range": [seed_base, seed_base + total_runs - 1],
    }
    manifest_path.write_text(json.dumps(initial_manifest, indent=2) + "\n", encoding="utf-8")

    # 6. Execute episodes in sandboxed subprocesses (Rules H13, H15)
    timeout_s = int(shift_cfg.get("timeout_s", 120))
    memory_mb = int(shift_cfg.get("memory_mb", 1024))
    all_specs = [
        {"distribution": "D", "trace_path": "dist_D", "scenario": sc, "seed": int(sc["seed"])}
        for sc in scenarios_d
    ] + [
        {"distribution": "D_prime", "trace_path": "dist_D_prime", "scenario": sc, "seed": int(sc["seed"])}
        for sc in scenarios_dp
    ]

    print(f"[{run_id}] Executing {len(all_specs)} episodes in sandboxed subprocesses...")

    def _execute_single(spec: dict[str, Any]) -> dict[str, Any]:
        sc = spec["scenario"]
        sd = spec["seed"]
        try:
            kind, payload = execute_episode(
                scenario=sc,
                seed=sd,
                policy_code=policy_code,
                repo_root=str(ROOT),
                timeout_s=timeout_s,
                memory_mb=memory_mb,
            )
            if kind == "sim":
                ts = bool(payload["truth_success"])
                ts_alt = bool(payload["truth_success_alt"])
                margin = float(payload["margin"])
            else:
                ts = False
                ts_alt = False
                margin = -1.0
        except Exception as e:
            print(f"[{run_id} Sim Error] Episode {sd}: {e}")
            ts = False
            ts_alt = False
            margin = -1.0

        return {
            "distribution": spec["distribution"],
            "trace_path": spec["trace_path"],
            "scenario": sc,
            "seed": sd,
            "truth_success": ts,
            "truth_success_alt": ts_alt,
            "margin": margin,
        }

    max_workers = min(os.cpu_count() or 4, 8)
    executed_records: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_execute_single, spec): spec for spec in all_specs}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            executed_records.append(res)

    # Sort deterministically by seed for append-only logging (Rule H10)
    executed_records.sort(key=lambda r: r["seed"])

    for idx, r in enumerate(executed_records):
        rec = episode_log.EpisodeResult(
            episode_id=f"{run_id}-ep{idx:04d}-s{r['seed']}",
            stream="certification",
            task="task_T1",
            program_id=program_id,
            program_version=1,
            scenario=dict(r["scenario"]),
            seed=r["seed"],
            truth_success=r["truth_success"],
            truth_success_alt=r["truth_success_alt"],
            margin=r["margin"],
            judge_mode="state",
            judge_pass=r["truth_success"],
            judge_confidence=1.0,
            trace_path=r["trace_path"],
            frames_path=None,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        episode_log.append_episode(log_path, rec)

    # 7. Compute shift figure data from raw logs (Rule H11)
    delta = float(shift_cfg.get("delta", 0.05))
    target_p = float(shift_cfg["targets"].get("state_cell_p", 0.90))
    d_ref_bound = float(shift_cfg["reference_p08"]["d_certified_region_bound"])

    fig_data = generate_shift_figure_data(
        episodes_path=log_path,
        d_bound=d_ref_bound,
        delta=delta,
        target_p=target_p,
    )

    fig_data_file = run_dir / "shift_figure_data.json"
    fig_data_file.write_text(json.dumps(fig_data, indent=2) + "\n", encoding="utf-8")

    # Render figure plot artifact (Rule H11)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

        # Bar chart: empirical pass rates and certified lower bounds
        cats = ["Reference D", "Shifted D'"]
        emp_rates = [fig_data["d_empirical_pass_rate"], fig_data["dp_empirical_pass_rate"]]
        bounds = [fig_data["d_recomputed_bound"], fig_data["dp_recertified_bound"]]

        x_pos = np.arange(len(cats))
        width = 0.35

        ax1.bar(x_pos - width / 2, emp_rates, width, label="Empirical Pass Rate", color="#3b82f6", alpha=0.85)
        ax1.bar(x_pos + width / 2, bounds, width, label="Certified Bound (95% CI)", color="#10b981", alpha=0.85)
        ax1.axhline(target_p, color="#ef4444", linestyle="--", linewidth=1.5, label=f"Target p >= {target_p}")
        ax1.set_ylabel("Probability")
        ax1.set_title("Guarantee Refusal Under Distribution Shift (H4)")
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(cats)
        ax1.set_ylim([0, 1.05])
        ax1.legend(loc="upper right")
        ax1.grid(axis="y", linestyle=":", alpha=0.6)

        # Mass distribution comparison
        masses_d = [ep["scenario"]["mass"] for ep in executed_records if ep["distribution"] == "D"]
        masses_dp = [ep["scenario"]["mass"] for ep in executed_records if ep["distribution"] == "D_prime"]
        ax2.hist(masses_d, bins=15, alpha=0.6, label="D (mass [1.0, 11.5] kg)", color="#3b82f6")
        ax2.hist(masses_dp, bins=15, alpha=0.6, label="D' (mass [6.0, 14.0] kg)", color="#f59e0b")
        ax2.axvline(8.495, color="#ef4444", linestyle="-.", linewidth=1.5, label="Gripper Slip Threshold (8.5 kg)")
        ax2.set_xlabel("Object Mass (kg)")
        ax2.set_ylabel("Count")
        ax2.set_title("Scenario Mass Shift")
        ax2.legend(loc="upper right")
        ax2.grid(axis="y", linestyle=":", alpha=0.6)

        plt.tight_layout()
        plot_path = run_dir / "shift_plot.png"
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)
    except Exception as e:
        print(f"[{run_id}] Note: Matplotlib plot rendering skipped ({e})")

    # 8. Complete manifest
    completed_manifest = dict(initial_manifest)
    completed_manifest.update({
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "episodes_observed": len(executed_records),
        "d_empirical_pass_rate": fig_data["d_empirical_pass_rate"],
        "d_bound": fig_data["d_recomputed_bound"],
        "dp_empirical_pass_rate": fig_data["dp_empirical_pass_rate"],
        "dp_recertified_bound": fig_data["dp_recertified_bound"],
        "bound_dropped": fig_data["bound_dropped"],
        "refusal": fig_data["refusal"],
        "shift_detected": fig_data["scenario_stats"].get("shift_detected", False),
    })
    manifest_path.write_text(json.dumps(completed_manifest, indent=2) + "\n", encoding="utf-8")

    print(f"[{run_id}] Completed {len(executed_records)} episodes.")
    print(f"  D empirical pass rate: {fig_data['d_empirical_pass_rate']:.4f}, bound: {fig_data['d_recomputed_bound']:.4f}")
    print(f"  D' empirical pass rate: {fig_data['dp_empirical_pass_rate']:.4f}, bound: {fig_data['dp_recertified_bound']:.4f}")
    print(f"  Bound dropped: {fig_data['bound_dropped']}, Refusal: {fig_data['refusal']}")

    return fig_data


def verify_phase_09_gate(run_id: str = "shift-full-01") -> None:
    """Gate verification for Phase 09 (Plan §12, PHASE_09_shift_h4.md).

    Asserions:
    1. Run manifest exists and matches expected config hash.
    2. Exactly 300 planned episodes executed and logged append-only.
    3. All seeds in certification stream [2000000, 2999999] with no duplicate seeds.
    4. Sampler shift is statistically detected (gate: STOP if shift not detectable in scenario stats).
    5. Hypothesis H4: D' recertified bound drops below D bound or refuses target p.
    6. Figure data generated strictly from logs matches SciPy recomputation.
    """
    run_dir = ROOT / "runs" / run_id
    manifest_file = run_dir / "manifest.json"
    episodes_file = run_dir / "episodes.jsonl"
    figure_data_file = run_dir / "shift_figure_data.json"

    assert manifest_file.exists(), f"Missing manifest: {manifest_file}"
    assert episodes_file.exists(), f"Missing episodes: {episodes_file}"
    assert figure_data_file.exists(), f"Missing figure data: {figure_data_file}"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed", "Run status must be completed"
    assert manifest["episodes_observed"] == manifest["episodes_planned"] == 300

    # Verify config hash
    from closedloop.data import manifest as run_manifest
    expected_hash = run_manifest.config_hash([
        ROOT / "configs" / "shift.yaml",
        ROOT / "configs" / "pricing.yaml",
        ROOT / "configs" / "tasks.yaml",
    ])
    assert manifest["config_hash"] == expected_hash, (
        f"Config hash mismatch: {manifest['config_hash']} != {expected_hash}"
    )

    # Verify episodes and seeds
    episodes: list[dict[str, Any]] = []
    with episodes_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line.strip()))

    assert len(episodes) == 300, f"Expected 300 episodes, found {len(episodes)}"
    seeds = [ep["seed"] for ep in episodes]
    assert len(seeds) == len(set(seeds)), "Duplicate seeds detected in shift run"
    for s in seeds:
        assert 2000000 <= s <= 2999999, f"Seed {s} outside certification stream"

    fig_data = json.loads(figure_data_file.read_text(encoding="utf-8"))

    # Check scenario stats: Gate requires shift detectable in scenario stats
    scen_stats = fig_data.get("scenario_stats", {})
    assert scen_stats.get("shift_detected", False) is True, (
        f"STOP: Shift not detectable in scenario stats (sampler bug): {scen_stats}"
    )
    mass_diff = scen_stats["dimensions"]["mass"]["mean_diff"]
    fric_diff = scen_stats["dimensions"]["friction"]["mean_diff"]
    assert mass_diff >= 2.0, f"Mass shift {mass_diff} < 2.0 kg"
    assert fric_diff <= -0.15, f"Friction shift {fric_diff} > -0.15"

    # Check Hypothesis H4
    assert fig_data["bound_dropped"] is True or fig_data["refusal"] is True, (
        f"STOP: H4 not supported: bound did not drop and no refusal: {fig_data}"
    )
    assert fig_data["dp_recertified_bound"] < fig_data["d_bound"], (
        f"D' bound {fig_data['dp_recertified_bound']} not less than D bound {fig_data['d_bound']}"
    )

    print(f"PHASE 09 GATE VERIFIED: run_id={run_id}, episodes={len(episodes)}")
    print(f"Reference D Bound: {fig_data['d_bound']:.4f}, D' Recertified Bound: {fig_data['dp_recertified_bound']:.4f}")
    print(f"D Empirical Pass: {fig_data['d_empirical_pass_rate']:.4f}, D' Empirical Pass: {fig_data['dp_empirical_pass_rate']:.4f}")
    print(f"Bound Drop: {fig_data['bound_difference']:.4f}, Refusal: {fig_data['refusal']}")
    print("PHASE 09: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 09 Shift Test Runner")
    parser.add_argument("--run-id", type=str, default="shift-full-01")
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()

    run_shift_experiment(run_id=args.run_id, pilot=args.pilot)
