"""Calibration engine for Vision Judge (Plan §8, Phase 07, Gate G2).

Executes >=300 true-success and >=300 true-failure rollouts on calibration seeds
(1,000,000–1,999,999 strictly, Rule H9) under a fixed sample plan (Rule H12).
Partitions failures into B=4 margin buckets.
Computes one-sided Clopper-Pearson bounds (a_L, worst-bucket b_U) and Day-1 ceiling.
Evaluates Gate G2: a_L >= 0.85, worst-bucket b_U <= 0.15, ceiling >= 0.85.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

import hashlib
from closedloop.certify.stats import cp_lower, cp_upper, ceiling
from closedloop.data import log as episode_log
from closedloop.data.sampler import BOUNDS, LeakageError, sample
from closedloop.judge.judge import VisionJudge
from closedloop.sim import primitives as prim
from closedloop.sim.env import PAD_POS, T1Env, good_policy, noop_policy


def compute_judge_freeze_hash(cfg_path: Path | str = "configs/judge.yaml") -> str:
    """Compute sha256 hash covering the complete judge configuration including prompt."""
    p = Path(cfg_path)
    return hashlib.sha256(p.read_bytes()).hexdigest()


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
    """Verify remaining budget headroom can accommodate full calibration before launch (Task 3)."""
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


def partition_into_bucket(margin: float, buckets: list[MarginBucket]) -> MarginBucket | None:
    """Assign a failure rollout (margin < 0) to its margin bucket."""
    if margin >= 0.0:
        return None  # Successful rollout, not a failure
    for b in buckets:
        if b.m_low <= margin < b.m_high:
            return b
    return buckets[-1]


def make_offset_policy(offset_x: float) -> Callable[[T1Env, np.random.Generator], None]:
    """Scripted near-miss pick-and-place with calibrated offset from pad boundary."""
    def policy(env: T1Env, rng: np.random.Generator) -> None:
        cube_pos, _ = prim.get_object_pose(env, "cube")
        above = (cube_pos[0], cube_pos[1], 0.15)
        prim.move_to(env, above, steps=30)
        prim.move_to(env, (cube_pos[0], cube_pos[1], cube_pos[2] + 0.03), steps=30)
        prim.close_gripper(env, 80.0)
        prim.move_to(env, above, steps=30)
        target = (PAD_POS[0] + offset_x, PAD_POS[1], 0.15)
        prim.move_to(env, target, steps=40)
        prim.move_to(env, (target[0], target[1], 0.04), steps=30)
        prim.open_gripper(env)
        prim.move_to(env, target, steps=30)
    return policy


def run_calibration(
    judge: VisionJudge,
    seed_base: int = 1001000,
    n_succ: int = 300,
    n_fail_per_bucket: int = 100,
    delta: float = 0.05,
    B: int = 4,
    K: int = 16,
    log_path: Path | None = None,
    print_interval: int = 50,
) -> CalibrationReport:
    """Run full calibration dataset on calibration seeds only (Rule H9, H10, H12).

    Pre-registered sample plan (judge-g2-03):
    - 300 fresh successes on seeds seed_base..seed_base+n_succ-1
    - 100 failures in each of the 4 margin buckets (400 failures total)
      on seeds seed_base+n_succ..seed_base+n_succ+4*n_fail_per_bucket-1
    All scenarios draw (mass, friction, yaw) from the identical unified distribution D.
    Buckets are filled using simulator margin only; judge verdicts are never read during sampling.
    Every evaluated episode is logged to episodes.jsonl (H10, append-only).
    """
    n_fail = n_fail_per_bucket * B
    total_episodes = n_succ + n_fail
    scenarios = sample("calibration", total_episodes, seed_base)
    succ_scenarios = scenarios[:n_succ]
    fail_scenarios = scenarios[n_succ:]

    buckets = [
        MarginBucket("near_boundary", -0.05, 0.0),
        MarginBucket("shallow", -0.15, -0.05),
        MarginBucket("medium", -0.35, -0.15),
        MarginBucket("deep", -1.00, -0.35),
    ]

    env = T1Env()
    succ_passes = 0
    succ_total = 0

    fail_passes = 0
    fail_total = 0

    # 1. Run planned successes (fixed seeds starting at seed_base)
    for i, sc in enumerate(succ_scenarios):
        seed = int(sc["seed"])
        env.reset(sc)
        good_policy(env, np.random.default_rng(seed))
        sim_res = env.finish()

        verdict = judge.judge_episode(env)
        if sim_res.truth_success:
            succ_total += 1
            if verdict.pass_verdict:
                succ_passes += 1
        else:
            fail_total += 1
            b = partition_into_bucket(sim_res.margin, buckets)
            if b:
                b.n_total += 1
                if verdict.pass_verdict:
                    b.k_pass += 1
                    fail_passes += 1

        if log_path:
            rec = episode_log.EpisodeResult(
                episode_id=f"cal-succ-{i+1:04d}-s{seed}",
                stream="calibration",
                task="task_T1",
                program_id="good_policy",
                program_version=1,
                scenario=dict(sc),
                seed=seed,
                truth_success=sim_res.truth_success,
                truth_success_alt=sim_res.truth_success_alt,
                margin=sim_res.margin,
                judge_mode="camera",
                judge_pass=verdict.pass_verdict,
                judge_confidence=verdict.confidence,
                trace_path="",
                frames_path=None,
                tokens_in=verdict.tokens_in,
                tokens_out=verdict.tokens_out,
                cost_usd=verdict.cost_usd,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            episode_log.append_episode(log_path, rec)

        if (i + 1) % print_interval == 0 or (i + 1) == n_succ:
            print(f"  Success stream: {i+1}/{n_succ} evaluated (pass: {succ_passes})", flush=True)

    # 2. Run planned failures: exactly n_fail_per_bucket in each of the 4 buckets
    strata_configs = [
        ("near_boundary", "offset_near", make_offset_policy(0.045)),
        ("shallow", "offset_shallow", make_offset_policy(0.10)),
        ("medium", "offset_medium", make_offset_policy(0.22)),
        ("deep", "offset_deep", make_offset_policy(0.42)),
    ]

    for k, (bucket_name, pol_name, pol_fn) in enumerate(strata_configs):
        strata_scenarios = fail_scenarios[k * n_fail_per_bucket : (k + 1) * n_fail_per_bucket]
        target_bucket = buckets[k]

        for j, sc in enumerate(strata_scenarios):
            seed = int(sc["seed"])
            env.reset(sc)
            pol_fn(env, np.random.default_rng(seed))
            sim_res = env.finish()

            # Sampling constraint: partition using simulator margin ONLY
            actual_bucket = partition_into_bucket(sim_res.margin, buckets) or target_bucket

            # Now evaluate the judge verdict on the rollout
            verdict = judge.judge_episode(env)

            if not sim_res.truth_success:
                fail_total += 1
                actual_bucket.n_total += 1
                if verdict.pass_verdict:
                    actual_bucket.k_pass += 1
                    fail_passes += 1
            else:
                succ_total += 1
                if verdict.pass_verdict:
                    succ_passes += 1

            if log_path:
                rec = episode_log.EpisodeResult(
                    episode_id=f"cal-fail-{bucket_name}-{j+1:04d}-s{seed}",
                    stream="calibration",
                    task="task_T1",
                    program_id=pol_name,
                    program_version=1,
                    scenario=dict(sc),
                    seed=seed,
                    truth_success=sim_res.truth_success,
                    truth_success_alt=sim_res.truth_success_alt,
                    margin=sim_res.margin,
                    judge_mode="camera",
                    judge_pass=verdict.pass_verdict,
                    judge_confidence=verdict.confidence,
                    trace_path="",
                    frames_path=None,
                    tokens_in=verdict.tokens_in,
                    tokens_out=verdict.tokens_out,
                    cost_usd=verdict.cost_usd,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                episode_log.append_episode(log_path, rec)

        print(
            f"  Bucket '{bucket_name}': {target_bucket.n_total} evaluated "
            f"(k_pass={target_bucket.k_pass}, fpr={target_bucket.fpr:.4f})",
            flush=True,
        )

    env.close()


    # 3. Compute Clopper-Pearson Statistics (stats.py)
    d_a = 0.1 * delta  # 0.005
    d_b = 0.1 * delta / B  # 0.00125

    tpr = succ_passes / succ_total if succ_total > 0 else 0.0
    tpr_lower = cp_lower(succ_passes, succ_total, d_a) if succ_total > 0 else 0.0

    fpr = fail_passes / fail_total if fail_total > 0 else 0.0

    bucket_stats: dict[str, dict[str, Any]] = {}
    bucket_b_his: list[float] = []

    for b in buckets:
        b_hi = cp_upper(b.k_pass, b.n_total, d_b) if b.n_total > 0 else 0.0
        bucket_b_his.append(b_hi)
        bucket_stats[b.name] = {
            "margin_range": [b.m_low, b.m_high],
            "k_pass": b.k_pass,
            "n_total": b.n_total,
            "fpr": round(b.fpr, 4),
            "fpr_upper": round(b_hi, 4),
        }

    worst_bucket_fpr_upper = max(bucket_b_his) if bucket_b_his else 0.0

    # 4. Ceiling calculation using empirical rates (Plan §11, stats.py)
    ceil_val = ceiling(
        a=tpr,
        b=fpr,
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

    # 5. Evaluate Gate G2 criteria
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
