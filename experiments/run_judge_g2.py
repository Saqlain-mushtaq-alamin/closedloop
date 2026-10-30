"""Phase 07: Vision Judge + Calibration (Gate G2) Experiment Runner.

Executes:
1. Visual inspection of 10 overlay frames with SAM 3.1 masks saved to disk (Task 1).
2. Pilot calibration (~60 rollouts, 30 success / 30 failure) + V9 controls (Task 3).
3. Cost pre-flight check projecting full run cost against remaining budget cap.
4. Full calibration (>=300 true success, >=300 true failure) on calibration seeds
   (1,000,000–1,999,999 strictly, Rule H9) under fixed sample plan (Rule H12).
5. Margin bucketing (B=4), Clopper-Pearson bounds (a_L, worst-bucket b_U), and Day-1 ceiling.
6. Evaluates Gate G2: a_L >= 0.85, worst-bucket b_U <= 0.15, ceiling >= 0.85.
7. Logs all episodes to append-only episodes.jsonl (H10) and writes frozen manifest.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
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

from closedloop.certify.stats import cp_lower, cp_upper, ceiling
from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.data.sampler import sample
from closedloop.judge.calibrate import (
    CalibrationReport,
    MarginBucket,
    compute_judge_freeze_hash,
    partition_into_bucket,
    preflight_cost_check,
    run_calibration,
)
from closedloop.judge.judge import (
    VisionJudge,
    check_centroid_in_pad,
    combine_verdict,
    draw_overlay_image,
    render_judge_frame,
)
from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.sim.env import T1Env, good_policy, noop_policy


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



def load_run_cache(cache_path: Path) -> dict[str, Any]:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_run_cache(cache: dict[str, Any], cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp = cache_path.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(cache_path)


def run_inspection_frames(
    judge: VisionJudge,
    out_dir: Path,
    n_frames: int = 10,
) -> list[dict[str, Any]]:
    """Capture and inspect overlay frames with saved visual PNGs for Task 1."""
    out_dir.mkdir(parents=True, exist_ok=True)
    inspections: list[dict[str, Any]] = []
    scenarios = sample("calibration", n_frames, 1000100)
    env = T1Env()

    for i, sc in enumerate(scenarios):
        seed = int(sc["seed"])
        env.reset(sc)
        if i % 2 == 0:
            good_policy(env, np.random.default_rng(seed))
            pol_desc = "good_policy (on pad)"
        else:
            noop_policy(env, np.random.default_rng(seed))
            pol_desc = "noop_policy (table surface)"

        sim_res = env.finish()
        verdict = judge.judge_episode(env)
        rgba, _ = render_judge_frame(env, judge.camera_cfg)

        overlay_img = draw_overlay_image(
            rgba=rgba,
            cube_box=verdict.cube_box,
            pad_box=verdict.pad_box,
            cube_centroid=verdict.cube_centroid,
            pass_verdict=verdict.pass_verdict,
            annotation=f"[{pol_desc}]",
        )
        png_path = out_dir / f"inspect_frame_{i:02d}.png"
        overlay_img.save(png_path)

        rec = {
            "index": i,
            "policy": pol_desc,
            "seed": seed,
            "scenario": sc,
            "sim_truth_success": sim_res.truth_success,
            "margin": sim_res.margin,
            "verdict_pass": verdict.pass_verdict,
            "geometric_pass": verdict.geometric_pass,
            "spark_pass": verdict.spark_pass,
            "cube_box": verdict.cube_box,
            "pad_box": verdict.pad_box,
            "cube_centroid": verdict.cube_centroid,
            "confidence": verdict.confidence,
            "png_file": png_path.name,
        }
        (out_dir / f"inspect_frame_{i:02d}.json").write_text(json.dumps(rec, indent=2))
        inspections.append(rec)

    env.close()
    return inspections


def run_judge_g2(
    run_id: str = "judge-g2-03",
    pilot: bool = False,
    n_succ_override: int | None = None,
    n_fail_override: int | None = None,
) -> dict[str, Any]:
    """Execute Phase 07 calibration and Gate G2 evaluation."""
    created_at = datetime.now(timezone.utc).isoformat()
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "episodes.jsonl"

    judge_cfg_path = ROOT / "configs" / "judge.yaml"
    with open(judge_cfg_path, encoding="utf-8") as f:
        judge_cfg = yaml.safe_load(f)

    judge_freeze_hash = compute_judge_freeze_hash(judge_cfg_path)

    # Load verified pricing and initialize CostMeter
    pricing_path = ROOT / "configs" / "pricing.yaml"
    meter = CostMeter()
    pricing_dict = meter.load_prices(pricing_path)

    # Isolated cache per run (Rule H10, H12)
    cache_path = run_dir / "llm_cache.json"
    cache = load_run_cache(cache_path)

    client = LLMClient(meter)

    judge = VisionJudge(
        client=client,
        model=judge_cfg.get("model", "muse-spark-1.3"),
        segmentation_model=judge_cfg.get("segmentation_model", "sam-3.1"),
        combination_rule=judge_cfg.get("combination_rule", "geometric_and_spark"),
        confidence_threshold=float(judge_cfg.get("confidence_threshold", 0.70)),
        prompt=judge_cfg.get("prompt"),
        camera_cfg=judge_cfg.get("camera"),
        cache=cache,
    )

    # Task 1: Generate 10 inspection overlay frames with visual images
    print("--- Task 1: Generating 10 visual inspection frames with SAM 3.1 overlays ---", flush=True)
    inspections = run_inspection_frames(judge, run_dir / "inspection", n_frames=10)
    print(
        f"Inspected 10 frames: {sum(1 for r in inspections if r['verdict_pass'])} pass, "
        f"{sum(1 for r in inspections if not r['verdict_pass'])} fail. Overlays saved.\n",
        flush=True,
    )

    # Seeds from 1,001,000 (pre-registered plan)
    seed_base = 1001000

    if pilot:
        n_succ = n_succ_override or 20
        n_fail_per_bucket = (n_fail_override // 4) if n_fail_override else 10
    else:
        n_succ = n_succ_override or 300
        n_fail_per_bucket = (n_fail_override // 4) if n_fail_override else 100

    n_fail = n_fail_per_bucket * 4

    # Task 3: Pre-flight cost check projecting full run cost from pilot metering
    if not pilot:
        print("--- Pre-Flight: Executing 60-rollout calibration pilot ---", flush=True)
        pilot_id = f"{run_id}-pilot"
        pilot_res = run_judge_g2(run_id=pilot_id, pilot=True, n_succ_override=20, n_fail_override=40)
        pilot_spent = float(pilot_res["total_cost_usd"])
        pilot_calls = int(pilot_res["episodes_evaluated"])
        remaining_headroom = meter.cap_usd - meter.spent_usd

        preflight_ok, preflight_msg = preflight_cost_check(
            pilot_calls=pilot_calls,
            pilot_spent_usd=pilot_spent,
            full_calls=n_succ + n_fail,
            headroom_usd=remaining_headroom,
        )
        print(f"Cost Pre-Flight: {preflight_msg}", flush=True)
        if not preflight_ok:
            raise RuntimeError(f"Cost Pre-Flight BLOCKED launch: {preflight_msg}")

    print_interval = 5 if pilot else 25
    print(f"\n=== Starting Phase 07 Vision Judge Calibration: {run_id} ===", flush=True)
    print(
        f"Target Successes: {n_succ}, Target Failures: {n_fail} "
        f"(100 per bucket x 4, Total Planned: {n_succ + n_fail})",
        flush=True,
    )
    print(f"Judge Freeze Hash: {judge_freeze_hash[:16]}..., Model: {judge.model}\n", flush=True)

    # Execute Calibration via authoritative engine
    report = run_calibration(
        judge=judge,
        seed_base=seed_base,
        n_succ=n_succ,
        n_fail_per_bucket=n_fail_per_bucket,
        delta=float(judge_cfg["calibration"].get("delta", 0.05)),
        B=int(judge_cfg["calibration"].get("margin_buckets", 4)),
        K=int(judge_cfg["calibration"].get("heatmap_cells", 16)),
        log_path=log_path,
        print_interval=print_interval,
    )


    save_run_cache(judge.cache, cache_path)

    # Save Calibration Report
    report_file = run_dir / "calibration_report.json"
    rep_dict = {
        "run_id": run_id,
        "n_success": report.n_success,
        "n_failure": report.n_failure,
        "tpr": report.tpr,
        "tpr_lower": report.tpr_lower,
        "fpr": report.fpr,
        "worst_bucket_fpr_upper": report.worst_bucket_fpr_upper,
        "margin_buckets": report.margin_buckets,
        "ceiling_target": report.ceiling_target,
        "g2_verdict": report.g2_verdict,
        "judge_freeze_hash": judge_freeze_hash,
        "total_cost_usd": round(meter.spent_usd, 6),
        "created_at": created_at,
    }
    report_file.write_text(json.dumps(rep_dict, indent=2), encoding="utf-8")

    # Read logged episodes count
    logged_episodes = len([line for line in log_path.read_text().splitlines() if line.strip()])

    # Write Manifest (H11, H12)
    manifest = {
        "run_id": run_id,
        "experiment": str(judge_cfg.get("experiment", "exp_judge_g2")),
        "task": str(judge_cfg.get("task", "task_T1")),
        "phase": "phase_07",
        "git_sha": git_head(),
        "config_hash": judge_freeze_hash,
        "budget_cap_usd": meter.cap_usd,
        "total_cost_usd": round(meter.spent_usd, 6),
        "pricing_per_mtok": pricing_dict,
        "episodes_planned": n_succ + n_fail,
        "episodes_completed": logged_episodes,
        "summary": {
            "tpr": report.tpr,
            "tpr_lower": report.tpr_lower,
            "fpr": report.fpr,
            "worst_bucket_fpr_upper": report.worst_bucket_fpr_upper,
            "ceiling_target": report.ceiling_target,
            "g2_verdict": report.g2_verdict,
        },
        "created_at": created_at,
        "status": "valid",
    }
    manifest_file = run_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


    print("\n=== Calibration Complete ===", flush=True)
    print(f"TPR: {report.tpr:.4f} (Lower bound a_L: {report.tpr_lower:.4f})", flush=True)
    print(f"FPR: {report.fpr:.4f} (Worst-bucket upper bound b_U: {report.worst_bucket_fpr_upper:.4f})", flush=True)
    print(f"Day-1 Ceiling Target: {report.ceiling_target:.4f}", flush=True)
    print(f"Gate G2 Verdict: {report.g2_verdict}", flush=True)
    print(f"Total Cost USD: ${meter.spent_usd:.4f}", flush=True)
    print(f"Report written to: {report_file}\n", flush=True)

    return {
        "run_id": run_id,
        "episodes_evaluated": logged_episodes,
        "total_cost_usd": meter.spent_usd,
        "report": rep_dict,
    }


def verify_phase_07_gate(run_id: str = "judge-g2-03", runs_dir: str = "runs") -> None:
    """Verify Phase 07 gate requirements on actual run artifacts (Plan §8, Phase 07)."""
    target_dir = ROOT / runs_dir / run_id
    rep_file = target_dir / "calibration_report.json"
    if not rep_file.exists():
        raise FileNotFoundError(f"Cannot verify Phase 07 gate: {rep_file} not found. Run calibration first.")

    rep_data = json.loads(rep_file.read_text(encoding="utf-8"))
    man_file = target_dir / "manifest.json"
    if not man_file.exists():
        raise FileNotFoundError(f"Manifest missing: {man_file}")
    man_data = json.loads(man_file.read_text(encoding="utf-8"))

    # 1. Config freeze hash check
    expected_freeze = compute_judge_freeze_hash()
    actual_freeze = rep_data.get("judge_freeze_hash", "")
    if actual_freeze != expected_freeze:
        raise AssertionError(
            f"Freeze hash mismatch: report {actual_freeze} != current {expected_freeze} "
            f"(configs/judge.yaml was modified post-run)"
        )

    # 2. Episode log audit & recomputation
    log_file = target_dir / "episodes.jsonl"
    if not log_file.exists():
        raise FileNotFoundError(f"Episode log missing: {log_file}")

    lines = [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    episodes = [json.loads(line) for line in lines]

    planned = man_data.get("episodes_planned", 0)
    if len(episodes) != planned:
        raise AssertionError(
            f"Episodes planned ({planned}) != episodes logged ({len(episodes)}). "
            f"Unlogged or uncompleted rollouts detected!"
        )

    if planned < 600:
        raise AssertionError(f"Full calibration requires >= 600 episodes planned, found {planned}")

    # Verify seeds strictly in calibration stream [1,000,000, 1,999,999]
    seen_seeds: set[int] = set()
    for ep in episodes:
        sd = int(ep.get("seed", 0))
        if not (1000000 <= sd < 2000000):
            raise AssertionError(f"H9 Violation: Episode seed {sd} not in calibration range [1M, 2M)")
        if sd in seen_seeds:
            raise AssertionError(f"Duplicate seed {sd} found in calibration run")
        seen_seeds.add(sd)

    # Recompute TPR and FPR
    succ_eps = [ep for ep in episodes if ep["truth_success"]]
    fail_eps = [ep for ep in episodes if not ep["truth_success"]]

    if len(succ_eps) < 300 or len(fail_eps) < 300:
        raise AssertionError(f"Calibration counts underpowered: {len(succ_eps)} succ, {len(fail_eps)} fail")

    succ_pass = sum(1 for ep in succ_eps if ep["judge_pass"])
    recomp_tpr = succ_pass / len(succ_eps)
    recomp_tpr_lower = cp_lower(succ_pass, len(succ_eps), 0.005)

    buckets = [
        MarginBucket("near_boundary", -0.05, 0.0),
        MarginBucket("shallow", -0.15, -0.05),
        MarginBucket("medium", -0.35, -0.15),
        MarginBucket("deep", -1.00, -0.35),
    ]

    fail_pass = 0
    for ep in fail_eps:
        b = partition_into_bucket(ep["margin"], buckets)
        if b:
            b.n_total += 1
            if ep["judge_pass"]:
                b.k_pass += 1
                fail_pass += 1

    bucket_u_bounds = [cp_upper(b.k_pass, b.n_total, 0.00125) if b.n_total > 0 else 0.0 for b in buckets]
    recomp_worst_bu = max(bucket_u_bounds)
    recomp_fpr = fail_pass / len(fail_eps)

    recomp_ceiling = ceiling(
        a=recomp_tpr,
        b=recomp_fpr,
        n_succ_cal=len(succ_eps),
        n_fail_cal=len(fail_eps),
        n_cell=113,
        K=16,
        delta=0.05,
        B=4,
        seed=1001000,
    )

    # Compare with report
    assert abs(rep_data["tpr_lower"] - recomp_tpr_lower) < 1e-3, "Reported tpr_lower mismatch"
    assert abs(rep_data["worst_bucket_fpr_upper"] - recomp_worst_bu) < 1e-3, "Reported worst_bucket_fpr_upper mismatch"

    # Evaluate G2 criteria
    g2_criteria = (
        recomp_tpr_lower >= 0.85
        and recomp_worst_bu <= 0.15
        and recomp_ceiling >= 0.85
    )
    expected_g2 = "PASS" if g2_criteria else "FAIL -> Pitch B"
    actual_g2 = rep_data.get("g2_verdict", "")

    if actual_g2 != expected_g2:
        raise AssertionError(f"Gate G2 verdict inconsistency: expected {expected_g2}, got {actual_g2}")

    print(f"PHASE 07: PASS (G2 {actual_g2})", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 07 Vision Judge Calibration")
    parser.add_argument("--run-id", default="judge-g2-03", help="Run ID")

    parser.add_argument("--pilot", action="store_true", help="Run pilot calibration (~60 rollouts)")
    parser.add_argument("--n-succ", type=int, default=None, help="Target successes override")
    parser.add_argument("--n-fail", type=int, default=None, help="Target failures override")
    parser.add_argument("--verify-gate", action="store_true", help="Run gate checks on run-id")
    args = parser.parse_args()

    if args.verify_gate:
        verify_phase_07_gate(run_id=args.run_id)
    else:
        run_judge_g2(
            run_id=args.run_id,
            pilot=args.pilot,
            n_succ_override=args.n_succ,
            n_fail_override=args.n_fail,
        )
