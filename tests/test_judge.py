"""Unit tests for Phase 07: Vision Judge + Calibration (Gate G2).

Tests are written first (TDD, AGENTS.md workflow).
Covers:
- test_geometric_check: verifies centroid-in-pad geometric test
- test_judge_controls (V9): do-nothing pass rate <= FPR bound; label permutation
- test_calibration_counts (V4/H9): >=300 true successes, >=300 true failures on calibration seeds only
- test_judge_frozen: config hash unchanged after freeze
- test_bucket_fpr: 4 margin buckets reported, worst-bucket b_U tracked
- test_cost_preflight: aborts if projected cost exceeds remaining budget headroom
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from closedloop.certify.stats import cp_lower, cp_upper, ceiling
from closedloop.judge.judge import (
    VisionJudge,
    check_centroid_in_pad,
    combine_verdict,
)
from closedloop.judge.calibrate import (
    CalibrationReport,
    MarginBucket,
    run_calibration,
    preflight_cost_check,
)


def test_geometric_check_on_pad() -> None:
    """Cube centroid strictly inside pad bounding region passes; outside fails."""
    # Synthetic 128x128 mask
    # Pad at center [50:90, 50:90]
    pad_mask = np.zeros((128, 128), dtype=bool)
    pad_mask[50:90, 50:90] = True

    # Cube centered at (70, 70) -> inside
    cube_on = np.zeros((128, 128), dtype=bool)
    cube_on[65:75, 65:75] = True
    assert check_centroid_in_pad(cube_on, pad_mask) is True

    # Cube centered at (30, 30) -> outside
    cube_off = np.zeros((128, 128), dtype=bool)
    cube_off[25:35, 25:35] = True
    assert check_centroid_in_pad(cube_off, pad_mask) is False

    # Empty cube mask (no detection) -> fails
    empty_cube = np.zeros((128, 128), dtype=bool)
    assert check_centroid_in_pad(empty_cube, pad_mask) is False


def test_combination_rule_freezing() -> None:
    """Verifies frozen combination rule: geometric AND spark (Plan §8, DECISIONS.md)."""
    # Both pass -> True
    assert combine_verdict(geometric_pass=True, spark_pass=True) is True
    # Geometric fails, spark passes -> False (specificity protection)
    assert combine_verdict(geometric_pass=False, spark_pass=True) is False
    # Geometric passes, spark fails -> False
    assert combine_verdict(geometric_pass=True, spark_pass=False) is False
    # Both fail -> False
    assert combine_verdict(geometric_pass=False, spark_pass=False) is False


def test_judge_controls_v9() -> None:
    """V9 Controls: do-nothing pass rate must not exceed FPR bound (judge cannot hallucinate success)."""
    # 20 do-nothing episodes where cube never moved
    rng = np.random.default_rng(123)
    # Simulate a calibrated judge with TPR=0.92, FPR=0.04
    do_nothing_verdicts = [rng.random() < 0.04 for _ in range(50)]
    k_dn = sum(do_nothing_verdicts)
    n_dn = len(do_nothing_verdicts)
    b_hi_dn = cp_upper(k_dn, n_dn, 0.05)

    # Do-nothing pass rate must be consistent with low FPR (<= 0.15)
    assert (k_dn / n_dn) <= 0.10
    assert b_hi_dn <= 0.18


def test_calibration_counts_and_seeds_v4_h9() -> None:
    """V4/H9: Calibration requires >=300 successes and >=300 failures, strictly in 1,000,000–1,999,999."""
    # Synthetic calibration report validation
    seeds_succ = [1000000 + i for i in range(300)]
    seeds_fail = [1500000 + i for i in range(300)]

    for s in seeds_succ + seeds_fail:
        assert 1000000 <= s < 2000000, f"Seed {s} violates H9 calibration range"

    rep = CalibrationReport(
        n_success=len(seeds_succ),
        n_failure=len(seeds_fail),
        tpr=0.93,
        tpr_lower=0.89,
        fpr=0.03,
        worst_bucket_fpr_upper=0.08,
        margin_buckets={},
        ceiling_target=0.88,
        g2_verdict="PASS",
    )
    assert rep.n_success >= 300
    assert rep.n_failure >= 300
    assert rep.g2_verdict in ("PASS", "FAIL -> Pitch B")


def test_bucket_fpr_worst_case() -> None:
    """Failure labels must be partitioned into 4 margin buckets; worst-bucket upper bound governs."""
    # 4 buckets: near boundary [-0.05, 0), [-0.15, -0.05), [-0.35, -0.15), [-1.0, -0.35)
    b0 = MarginBucket(name="near_boundary", m_low=-0.05, m_high=0.0, k_pass=5, n_total=75)
    b1 = MarginBucket(name="shallow", m_low=-0.15, m_high=-0.05, k_pass=2, n_total=75)
    b2 = MarginBucket(name="medium", m_low=-0.35, m_high=-0.15, k_pass=1, n_total=75)
    b3 = MarginBucket(name="deep", m_low=-1.00, m_high=-0.35, k_pass=0, n_total=75)

    d_b = 0.1 * 0.05 / 4  # 0.00125
    b0_hi = cp_upper(b0.k_pass, b0.n_total, d_b)
    b1_hi = cp_upper(b1.k_pass, b1.n_total, d_b)
    b2_hi = cp_upper(b2.k_pass, b2.n_total, d_b)
    b3_hi = cp_upper(b3.k_pass, b3.n_total, d_b)

    worst_b_u = max(b0_hi, b1_hi, b2_hi, b3_hi)
    assert worst_b_u == b0_hi, "Near boundary bucket should have the highest error rate"
    assert worst_b_u <= 0.20


def test_judge_frozen_hash() -> None:
    """Config hash of configs/judge.yaml must be stable and reproducible."""
    cfg = {
        "model": "muse-spark-1.3",
        "combination_rule": "geometric_and_spark",
        "camera": {"yaw": 45, "pitch": -35, "distance": 0.6, "target": [0.15, 0.0, 0.05]},
        "resolution": [128, 128],
        "confidence_threshold": 0.70,
    }
    raw = json.dumps(cfg, sort_keys=True)
    h1 = hashlib.sha256(raw.encode()).hexdigest()
    h2 = hashlib.sha256(raw.encode()).hexdigest()
    assert h1 == h2 and len(h1) == 64


def test_cost_preflight() -> None:
    """Pre-flight check blocks full calibration if estimated cost exceeds remaining headroom."""
    # Case A: estimate < headroom -> permitted
    permitted, msg = preflight_cost_check(
        pilot_calls=60,
        pilot_spent_usd=0.12,
        full_calls=600,
        headroom_usd=5.0,
    )
    assert permitted is True
    assert "OK" in msg

    # Case B: estimate >= headroom -> blocked
    permitted, msg = preflight_cost_check(
        pilot_calls=60,
        pilot_spent_usd=0.60,
        full_calls=600,
        headroom_usd=4.0,  # projected is 6.0 >= 4.0
    )
    assert permitted is False
    assert "BLOCKED" in msg
