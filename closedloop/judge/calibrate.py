"""Calibration engine for Vision Judge (Plan §8, Phase 07, Gate G2).

Executes >=300 true-success and >=300 true-failure rollouts on calibration seeds
(1,000,000–1,999,999 strictly, Rule H9).
Partitions failures into B=4 margin buckets.
Computes one-sided Clopper-Pearson bounds (a_L, worst-bucket b_U) and Day-1 ceiling.
Evaluates Gate G2: a_L >= 0.85, worst-bucket b_U <= 0.15, ceiling >= 0.85.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from closedloop.certify.stats import cp_lower, cp_upper, ceiling
from closedloop.judge.judge import VisionJudge
from closedloop.sim.env import T1Env, good_policy, noop_policy, random_policy


@dataclass
class MarginBucket:
    """Bucket of true failure rollouts stratified by distance to success threshold."""

    name: str
    m_low: float
    m_high: float
    k_pass: int = 0
    n_total: int = 0

    @property
    def fpr(self) -> float:
        return self.k_pass / self.n_total if self.n_total > 0 else 0.0


@dataclass
class CalibrationReport:
    """Complete summary of calibration results and Gate G2 verdict."""

    n_success: int
    n_failure: int
    tpr: float
    tpr_lower: float
    fpr: float
    worst_bucket_fpr_upper: float
    margin_buckets: dict[str, dict[str, Any]]
    ceiling_target: float
    g2_verdict: str


def preflight_cost_check(
    pilot_calls: int,
    pilot_spent_usd: float,
    full_calls: int,
    headroom_usd: float,
) -> tuple[bool, str]:
    """Verify remaining budget headroom can accommodate full calibration before launch."""
    if pilot_calls <= 0:
        return False, "BLOCKED: pilot_calls must be > 0"
    unit_cost = pilot_spent_usd / pilot_calls
    projected = unit_cost * full_calls
    if projected >= headroom_usd:
        return (
            False,
            f"BLOCKED: projected cost ${projected:.2f} >= remaining headroom ${headroom_usd:.2f}",
        )
    return (
        True,
        f"OK: projected cost ${projected:.2f} < remaining headroom ${headroom_usd:.2f} (unit: ${unit_cost:.4f})",
    )


def partition_into_bucket(margin: float, buckets: list[MarginBucket]) -> MarginBucket:
    """Assign a failure rollout to its margin bucket."""
    for b in buckets:
        if b.m_low <= margin < b.m_high:
            return b
    # Catch-all edge assignment
    if margin >= 0.0:
        return buckets[0]
    return buckets[-1]


def run_calibration(
    judge: VisionJudge,
    seed_base: int = 1000000,
    n_succ_target: int = 300,
    n_fail_target: int = 300,
    delta: float = 0.05,
    B: int = 4,
    K: int = 16,
) -> CalibrationReport:
    """Run full calibration dataset on calibration seeds only (Rule H9)."""
    assert 1000000 <= seed_base < 1900000, "Seed must be in calibration range (1M-1.99M)"

    buckets = [
        MarginBucket("near_boundary", -0.05, 0.0),
        MarginBucket("shallow", -0.15, -0.05),
        MarginBucket("medium", -0.35, -0.15),
        MarginBucket("deep", -1.00, -0.35),
    ]

    env = T1Env()
    rng = np.random.default_rng(seed_base)

    succ_passes = 0
    succ_total = 0

    fail_passes = 0
    fail_total = 0

    curr_seed = seed_base

    # 1. Collect true successes (using good_policy on valid scenario ranges)
    while succ_total < n_succ_target:
        sc = {
            "x": float(rng.uniform(-0.04, 0.04)),
            "y": float(rng.uniform(-0.04, 0.04)),
            "yaw": float(rng.uniform(-0.2, 0.2)),
            "mass": float(rng.uniform(1.0, 3.0)),
            "friction": float(rng.uniform(0.6, 1.0)),
            "seed": curr_seed,
        }
        curr_seed += 1
        env.reset(sc)
        good_policy(env, rng)
        res = env.finish()
        if res.truth_success:
            verdict = judge.judge_episode(env)
            if verdict.pass_verdict:
                succ_passes += 1
            succ_total += 1

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

    # 2. Collect true failures stratified across margin buckets
    target_per_bucket = n_fail_target // B

    while any(b.n_total < target_per_bucket for b in buckets) or fail_total < n_fail_target:
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

        curr_seed += 1
        env.reset(sc)
        policy_fn(env, rng)
        res = env.finish()

        if not res.truth_success:
            bucket = partition_into_bucket(res.margin, buckets)
            if bucket.n_total < target_per_bucket or fail_total < n_fail_target:
                verdict = judge.judge_episode(env)
                bucket.n_total += 1
                fail_total += 1
                if verdict.pass_verdict:
                    bucket.k_pass += 1
                    fail_passes += 1

    env.close()

    # 3. Compute Clopper-Pearson Statistics (stats.py)
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

    # 4. Ceiling calculation (median certified bound from Day-1 script)
    # Assumes n_cell = 113 for target p=0.95 at delta_cell = 0.8*delta/(K*M)
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

    # 5. Evaluate Gate G2
    g2_pass = (
        tpr_lower >= 0.85
        and worst_bucket_fpr_upper <= 0.15
        and ceil_val >= 0.85
    )
    g2_verdict = "PASS" if g2_pass else "FAIL -> Pitch B"

    return CalibrationReport(
        n_success=succ_total,
        n_failure=fail_total,
        tpr=round(tpr, 4),
        tpr_lower=round(tpr_lower, 4),
        fpr=round(fpr, 4),
        worst_bucket_fpr_upper=round(worst_bucket_fpr_upper, 4),
        margin_buckets=bucket_stats,
        ceiling_target=round(ceil_val, 4),
        g2_verdict=g2_verdict,
    )
