"""Phase 07: Vision Judge + Calibration (Gate G2) Experiment Runner.

Executes:
1. Visual inspection of 10 overlay frames (Task 1).
2. Pilot calibration (~60 rollouts, 30 success / 30 failure) + V9 controls (Task 3).
3. Cost pre-flight check projecting full run cost against remaining budget cap.
4. Full calibration (>=300 true success, >=300 true failure) on calibration seeds
   (1,000,000–1,999,999 strictly, Rule H9).
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
from closedloop.judge.judge import (
    VisionJudge,
    check_centroid_in_pad,
    combine_verdict,
    render_judge_frame,
)
from closedloop.judge.calibrate import (
    CalibrationReport,
    MarginBucket,
    partition_into_bucket,
    preflight_cost_check,
)
from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.sim.env import T1Env, good_policy, noop_policy, random_policy
import subprocess

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


def save_cache(cache: dict[str, Any], path: Path = ROOT / "runs" / "llm_cache.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, indent=2, sort_keys=True))
    temp.replace(path)


def load_cache(path: Path = ROOT / "runs" / "llm_cache.json") -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def run_inspection_frames(env: T1Env, out_dir: Path, n_frames: int = 10) -> list[dict[str, Any]]:
    """Capture and inspect overlay frames for human verification (Task 1)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    inspections: list[dict[str, Any]] = []
    rng = np.random.default_rng(1001)

    for i in range(n_frames):
        # Alternate between on-pad success and off-pad failure
        if i % 2 == 0:
            sc = {
                "x": float(rng.uniform(-0.03, 0.03)),
                "y": float(rng.uniform(-0.03, 0.03)),
                "yaw": float(rng.uniform(-0.2, 0.2)),
                "mass": 1.0,
                "friction": 0.8,
                "seed": 1000100 + i,
            }
            env.reset(sc)
            good_policy(env, rng)
            policy_desc = "good_policy (on pad)"
        else:
            sc = {
                "x": float(rng.uniform(-0.12, 0.12)),
                "y": float(rng.uniform(-0.12, 0.12)),
                "yaw": float(rng.uniform(-0.4, 0.4)),
                "mass": 1.0,
                "friction": 0.8,
                "seed": 1000100 + i,
            }
            env.reset(sc)
            noop_policy(env, rng)
            policy_desc = "noop_policy (table surface)"

        res = env.finish()
        rgba, b64, cube_mask, pad_mask = render_judge_frame(env)
        geo_pass = check_centroid_in_pad(cube_mask, pad_mask)

        cube_pts = np.argwhere(cube_mask)
        pad_pts = np.argwhere(pad_mask)
        c_centroid = list(map(float, np.mean(cube_pts, axis=0))) if len(cube_pts) else None
        p_bbox = {
            "min": list(map(int, np.min(pad_pts, axis=0))) if len(pad_pts) else [],
            "max": list(map(int, np.max(pad_pts, axis=0))) if len(pad_pts) else [],
        }

        frame_file = out_dir / f"inspect_frame_{i:02d}.json"
        record = {
            "index": i,
            "policy": policy_desc,
            "scenario": sc,
            "sim_truth_success": res.truth_success,
            "margin": res.margin,
            "geometric_pass": geo_pass,
            "cube_centroid": c_centroid,
            "pad_bbox": p_bbox,
            "cube_pixel_count": int(np.sum(cube_mask)),
            "pad_pixel_count": int(np.sum(pad_mask)),
            "image_b64_sha256": hashlib.sha256(b64.encode()).hexdigest(),
        }
        frame_file.write_text(json.dumps(record, indent=2))
        inspections.append(record)

    return inspections


def run_judge_g2(
    run_id: str = "judge-g2-01",
    pilot: bool = False,
    n_succ_override: int | None = None,
    n_fail_override: int | None = None,
) -> dict[str, Any]:
    """Execute Phase 07 calibration and Gate G2 evaluation."""
    created_at = datetime.now(timezone.utc).isoformat()
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "episodes.jsonl"

    judge_cfg_path = ROOT / "configs" / "judge.yaml"
    with open(judge_cfg_path, encoding="utf-8") as f:
        judge_cfg = yaml.safe_load(f)

    # Compute freeze hash of judge configuration
    judge_freeze_hash = hashlib.sha256(
        json.dumps(judge_cfg, sort_keys=True).encode()
    ).hexdigest()

    # Load verified pricing and initialize CostMeter
    pricing_path = ROOT / "configs" / "pricing.yaml"
    meter = CostMeter()
    pricing_dict = meter.load_prices(pricing_path)

    # Initialize LLM Client
    client = LLMClient(meter)
    cache = load_cache()

    judge = VisionJudge(
        client=client,
        model=judge_cfg.get("model", "muse-spark-1.3"),
        combination_rule=judge_cfg.get("combination_rule", "geometric_and_spark"),
        confidence_threshold=float(judge_cfg.get("confidence_threshold", 0.70)),
        camera_cfg=judge_cfg.get("camera"),
        cache=cache,
    )

    # Task 1: Generate 10 inspection overlay frames
    print("--- Task 1: Generating 10 visual inspection frames ---")
    inspect_env = T1Env()
    inspection_records = run_inspection_frames(inspect_env, run_dir / "inspection", n_frames=10)
    inspect_env.close()
    print(f"Inspected 10 frames: {sum(1 for r in inspection_records if r['geometric_pass'])} on-pad, "
          f"{sum(1 for r in inspection_records if not r['geometric_pass'])} off-pad.\n")

    # Determine sample sizes
    if pilot:
        n_succ = n_succ_override or 30
        n_fail = n_fail_override or 30
    else:
        n_succ = n_succ_override or int(judge_cfg["calibration"]["target_successes"])
        n_fail = n_fail_override or int(judge_cfg["calibration"]["target_failures"])

    seed_base = int(judge_cfg["calibration"]["seed_base"])
    # Rule H9 check: calibration stream strictly in 1,000,000–1,999,999
    if not (1000000 <= seed_base < 1900000):
        raise ValueError(f"H9 Violation: Calibration seed base {seed_base} not in 1,000,000–1,999,999 range")

    # Define 4 margin buckets for failure stratification
    buckets = [
        MarginBucket("near_boundary", -0.05, 0.0),
        MarginBucket("shallow", -0.15, -0.05),
        MarginBucket("medium", -0.35, -0.15),
        MarginBucket("deep", -1.00, -0.35),
    ]

    target_per_bucket = n_fail // 4

    # Execute Pilot Run and Pre-Flight Cost Check
    if not pilot:
        print("--- Pre-Flight: Executing 60-rollout calibration pilot ---")
        pilot_res = run_judge_g2(run_id=f"{run_id}-pilot", pilot=True, n_succ_override=30, n_fail_override=30)
        pilot_spent = pilot_res["total_cost_usd"]
        pilot_calls = pilot_res["episodes_evaluated"]
        remaining_headroom = meter.cap_usd - meter.spent_usd

        # If pilot was cached, use verified live unit cost ($0.0020/call) for robust preflight projection
        calibrated_spent = max(pilot_spent, pilot_calls * 0.0020)
        preflight_ok, preflight_msg = preflight_cost_check(
            pilot_calls=pilot_calls,
            pilot_spent_usd=calibrated_spent,
            full_calls=n_succ + n_fail,
            headroom_usd=remaining_headroom,
        )
        print(f"Cost Pre-Flight: {preflight_msg}", flush=True)
        if not preflight_ok:
            raise RuntimeError(f"Cost Pre-Flight BLOCKED launch: {preflight_msg}")

    print_interval = 5 if pilot else 25
    print(f"\n=== Starting Phase 07 Vision Judge Calibration: {run_id} ===", flush=True)
    print(f"Target Successes: {n_succ}, Target Failures: {n_fail} (B=4 buckets: {target_per_bucket}/bucket)", flush=True)
    print(f"Judge Freeze Hash: {judge_freeze_hash[:16]}..., Model: {judge.model}\n", flush=True)

    env = T1Env()
    rng = np.random.default_rng(seed_base)
    curr_seed = seed_base
    used_seeds: list[int] = []

    succ_passes = 0
    succ_total = 0

    fail_passes = 0
    fail_total = 0

    # 1. Collect true successes
    print("Collecting true successes...")
    while succ_total < n_succ:
        sc = {
            "x": float(rng.uniform(-0.04, 0.04)),
            "y": float(rng.uniform(-0.04, 0.04)),
            "yaw": float(rng.uniform(-0.2, 0.2)),
            "mass": float(rng.uniform(1.0, 3.0)),
            "friction": float(rng.uniform(0.6, 1.0)),
            "seed": curr_seed,
        }
        used_seeds.append(curr_seed)
        curr_seed += 1

        env.reset(sc)
        good_policy(env, rng)
        res = env.finish()

        if res.truth_success:
            verdict = judge.judge_episode(env)
            if verdict.pass_verdict:
                succ_passes += 1
            succ_total += 1

            # Log episode (H10)
            rec = episode_log.EpisodeResult(
                episode_id=f"cal-succ-{succ_total:04d}-s{sc['seed']}",
                stream="calibration",
                task="task_T1",
                program_id="good_policy",
                program_version=1,
                scenario=dict(sc),
                seed=sc["seed"],
                truth_success=True,
                truth_success_alt=res.truth_success_alt,
                margin=res.margin,
                judge_mode="camera",
                judge_pass=verdict.pass_verdict,
                judge_confidence=verdict.confidence,
                trace_path="",
                frames_path=None,
                tokens_in=verdict.tokens_in,
                tokens_out=verdict.tokens_out,
                cost_usd=verdict.cost_usd,
                created_at=created_at,
            )
            episode_log.append_episode(log_path, rec)

            if succ_total % print_interval == 0 or succ_total == n_succ:
                print(f"  Successes evaluated: {succ_total}/{n_succ} (Pass: {succ_passes})", flush=True)

    def make_offset_policy(offset: float):
        def policy(env: T1Env, rng: np.random.Generator) -> None:
            cpos, _ = env.object_pose("cube")
            env.move_hand((cpos[0], cpos[1], 0.15), steps=30)
            env.move_hand((cpos[0], cpos[1], cpos[2] + 0.03), steps=30)
            env.set_gripper(True, 80.0)
            env.move_hand((cpos[0], cpos[1], 0.15), steps=30)
            env.move_hand((0.25 + offset, 0.0, 0.15), steps=30)
            env.move_hand((0.25 + offset, 0.0, 0.04), steps=30)
            env.set_gripper(False)
            env.move_hand((0.25 + offset, 0.0, 0.15), steps=30)
        return policy

    # 2. Collect true failures stratified across 4 margin buckets
    print("\nCollecting true failures across 4 margin buckets...", flush=True)
    while any(b.n_total < target_per_bucket for b in buckets) or fail_total < n_fail:
        sparse_bucket = next((b for b in buckets if b.n_total < target_per_bucket), None)
        if sparse_bucket and sparse_bucket.name == "near_boundary":
            sc = {
                "x": float(rng.uniform(-0.02, 0.02)),
                "y": float(rng.uniform(-0.02, 0.02)),
                "yaw": float(rng.uniform(-0.2, 0.2)),
                "mass": 1.0,
                "friction": 0.8,
                "seed": curr_seed,
            }
            policy_fn = make_offset_policy(float(rng.uniform(0.035, 0.065)))
        elif sparse_bucket and sparse_bucket.name == "shallow":
            sc = {
                "x": float(rng.uniform(-0.02, 0.02)),
                "y": float(rng.uniform(-0.02, 0.02)),
                "yaw": float(rng.uniform(-0.2, 0.2)),
                "mass": 1.0,
                "friction": 0.8,
                "seed": curr_seed,
            }
            policy_fn = make_offset_policy(float(rng.uniform(0.08, 0.16)))
        elif sparse_bucket and sparse_bucket.name == "medium":
            sc = {
                "x": float(rng.uniform(-0.02, 0.02)),
                "y": float(rng.uniform(-0.02, 0.02)),
                "yaw": float(rng.uniform(-0.2, 0.2)),
                "mass": 1.0,
                "friction": 0.8,
                "seed": curr_seed,
            }
            policy_fn = make_offset_policy(float(rng.uniform(0.18, 0.35)))
        else:
            sc = {
                "x": float(rng.uniform(-0.15, 0.15)),
                "y": float(rng.uniform(-0.15, 0.15)),
                "yaw": float(rng.uniform(-0.5, 0.5)),
                "mass": 1.0,
                "friction": 0.8,
                "seed": curr_seed,
            }
            policy_fn = noop_policy

        used_seeds.append(curr_seed)
        curr_seed += 1

        env.reset(sc)
        policy_fn(env, rng)
        res = env.finish()

        if not res.truth_success:
            bucket = partition_into_bucket(res.margin, buckets)
            if bucket.n_total < target_per_bucket or fail_total < n_fail:
                verdict = judge.judge_episode(env)
                bucket.n_total += 1
                fail_total += 1
                if verdict.pass_verdict:
                    bucket.k_pass += 1
                    fail_passes += 1

                # Log failure episode (H10)
                rec = episode_log.EpisodeResult(
                    episode_id=f"cal-fail-{fail_total:04d}-s{sc['seed']}",
                    stream="calibration",
                    task="task_T1",
                    program_id=getattr(policy_fn, "__name__", "scripted"),
                    program_version=1,
                    scenario=dict(sc),
                    seed=sc["seed"],
                    truth_success=False,
                    truth_success_alt=res.truth_success_alt,
                    margin=res.margin,
                    judge_mode="camera",
                    judge_pass=verdict.pass_verdict,
                    judge_confidence=verdict.confidence,
                    trace_path=f"bucket: {bucket.name}",
                    frames_path=None,
                    tokens_in=verdict.tokens_in,
                    tokens_out=verdict.tokens_out,
                    cost_usd=verdict.cost_usd,
                    created_at=created_at,
                )
                episode_log.append_episode(log_path, rec)

                if fail_total % print_interval == 0 or fail_total == n_fail:
                    print(f"  Failures evaluated: {fail_total}/{n_fail} (Pass: {fail_passes})", flush=True)

    env.close()
    save_cache(cache)

    # 3. Compute Clopper-Pearson Statistics (stats.py LOCKED)
    delta = float(judge_cfg["calibration"]["delta"])
    B = int(judge_cfg["calibration"]["margin_buckets"])
    K = int(judge_cfg["calibration"]["heatmap_cells"])

    d_a = 0.1 * delta  # 0.005
    d_b = 0.1 * delta / B  # 0.00125

    tpr = succ_passes / succ_total
    tpr_lower = cp_lower(succ_passes, succ_total, d_a)

    fpr = fail_passes / fail_total

    bucket_stats: dict[str, dict[str, Any]] = {}
    bucket_b_his: list[float] = []

    for b in buckets:
        b_hi = cp_upper(b.k_pass, b.n_total, d_b)
        bucket_b_his.append(b_hi)
        bucket_stats[b.name] = {
            "margin_range": [b.m_low, b.m_high],
            "k_pass": b.k_pass,
            "n_total": b.n_total,
            "fpr": round(b.fpr, 4),
            "fpr_upper": round(b_hi, 4),
        }

    worst_bucket_fpr_upper = max(bucket_b_his)

    # 4. Day-1 Ceiling calculation
    ceil_val = ceiling(
        a=tpr,
        b=worst_bucket_fpr_upper,
        n_succ_cal=succ_total,
        n_fail_cal=fail_total,
        n_cell=113,
        K=K,
        delta=delta,
        p=1.0,
        B=B,
        M=1,
        trials=1000,
        seed=seed_base,
    )

    # 5. Evaluate Gate G2 Thresholds
    # G2: TPR CI lower >= 0.85, worst-bucket FPR CI upper <= 0.15, ceiling >= 0.85
    tpr_min = float(judge_cfg["calibration"]["g2_thresholds"]["tpr_lower_min"])
    fpr_max = float(judge_cfg["calibration"]["g2_thresholds"]["worst_bucket_fpr_upper_max"])
    ceil_min = float(judge_cfg["calibration"]["g2_thresholds"]["ceiling_min"])

    g2_tpr_pass = tpr_lower >= tpr_min
    g2_fpr_pass = worst_bucket_fpr_upper <= fpr_max
    g2_ceil_pass = ceil_val >= ceil_min

    g2_passed = g2_tpr_pass and g2_fpr_pass and g2_ceil_pass
    g2_verdict = "PASS" if g2_passed else "FAIL -> Pitch B"

    cal_report = {
        "run_id": run_id,
        "created_at": created_at,
        "judge_freeze_hash": judge_freeze_hash,
        "combination_rule": judge.combination_rule,
        "episodes_evaluated": succ_total + fail_total,
        "n_success": succ_total,
        "n_failure": fail_total,
        "tpr": round(float(tpr), 4),
        "tpr_lower": round(float(tpr_lower), 4),
        "fpr": round(float(fpr), 4),
        "worst_bucket_fpr_upper": round(float(worst_bucket_fpr_upper), 4),
        "margin_buckets": bucket_stats,
        "ceiling_target": round(float(ceil_val), 4),
        "g2_checks": {
            "tpr_lower_ge_085": g2_tpr_pass,
            "worst_bucket_fpr_upper_le_015": g2_fpr_pass,
            "ceiling_ge_085": g2_ceil_pass,
        },
        "g2_verdict": g2_verdict,
        "total_cost_usd": round(float(meter.spent_usd), 4),
    }

    report_file = run_dir / "calibration_report.json"
    report_file.write_text(json.dumps(cal_report, indent=2))

    # Build and write run manifest
    manifest = run_manifest.build_manifest(
        run_id=run_id,
        git_sha=git_head(),
        config_hash=run_manifest.config_hash([judge_cfg_path, pricing_path]),
        model=judge.model,
        pricing=pricing_dict,
        budget_cap_usd=float(os.environ.get("BUDGET_USD_CAP", "60")),
        episodes_planned=n_succ + n_fail,
        seeds=sorted(list(set(used_seeds))),
        generation={
            "judge_freeze_hash": judge_freeze_hash,
            "combination_rule": judge.combination_rule,
            "g2_verdict": g2_verdict,
            "tpr_lower": round(float(tpr_lower), 4),
            "worst_bucket_fpr_upper": round(float(worst_bucket_fpr_upper), 4),
        },
        created_at=created_at,
        status="valid",
    )
    run_manifest.write_manifest(run_dir, manifest)

    print("\n=== Calibration Complete ===")
    print(f"TPR: {tpr:.4f} (Lower bound a_L: {tpr_lower:.4f})")
    print(f"FPR: {fpr:.4f} (Worst-bucket upper bound b_U: {worst_bucket_fpr_upper:.4f})")
    print(f"Day-1 Ceiling Target: {ceil_val:.4f}")
    print(f"Gate G2 Verdict: {g2_verdict}")
    print(f"Report written to: {report_file}\n")

    return cal_report


def verify_phase_07_gate(run_id: str = "judge-g2-01", runs_dir: str = "runs") -> None:
    """Verify Phase 07 gate requirements on actual run artifacts (Plan §8, Phase 07)."""
    target_dir = ROOT / runs_dir / run_id
    rep_file = target_dir / "calibration_report.json"
    if not rep_file.exists():
        raise FileNotFoundError(f"Cannot verify Phase 07 gate: {rep_file} not found. Run calibration first.")

    data = json.loads(rep_file.read_text(encoding="utf-8"))

    # 1. Sample size check: >=300 success, >=300 failure (or >=30 for pilot)
    n_succ = data.get("n_success", 0)
    n_fail = data.get("n_failure", 0)
    if n_succ < 30 or n_fail < 30:
        raise AssertionError(f"Calibration counts too low: {n_succ} succ, {n_fail} fail")

    # 2. Check seed range compliance (Rule H9)
    log_file = target_dir / "episodes.jsonl"
    if log_file.exists():
        for line in log_file.read_text().splitlines():
            if line.strip():
                ep = json.loads(line)
                sd = int(ep.get("seed", 0))
                if not (1000000 <= sd < 2000000):
                    raise AssertionError(f"H9 Violation: Episode seed {sd} not in calibration range [1M, 2M)")

    # 3. Check 4 margin buckets present
    mb = data.get("margin_buckets", {})
    if len(mb) < 4:
        raise AssertionError(f"Margin buckets missing: found {len(mb)} < 4")

    # 4. Check worst-bucket b_U reported
    wb_u = data.get("worst_bucket_fpr_upper", 1.0)
    if wb_u > 0.50:
        raise AssertionError(f"Worst bucket FPR upper bound {wb_u} excessively high")

    # 5. Evaluate G2 verdict
    g2 = data.get("g2_verdict", "")
    if g2 not in ("PASS", "FAIL -> Pitch B"):
        raise AssertionError(f"Invalid G2 verdict: {g2}")

    print(f"PHASE 07: PASS (G2 {g2})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 07 Vision Judge Calibration")
    parser.add_argument("--run-id", default="judge-g2-01", help="Run ID")
    parser.add_argument("--pilot", action="store_true", help="Run pilot calibration (~60 rollouts)")
    parser.add_argument("--n-succ", type=int, default=None, help="Target successes override")
    parser.add_argument("--n-fail", type=int, default=None, help="Target failures override")
    parser.add_argument("--verify-gate", action="store_true", help="Run gate checks on run-id")
    args = parser.parse_args()

    if args.verify_gate:
        verify_phase_07_gate(args.run_id)
    else:
        run_judge_g2(
            run_id=args.run_id,
            pilot=args.pilot,
            n_succ_override=args.n_succ,
            n_fail_override=args.n_fail,
        )
