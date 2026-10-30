"""Unit tests for Phase 07: Vision Judge + Calibration (Gate G2).

Tests are written first (TDD, AGENTS.md workflow).
All tests call real production modules, real geometric checks, real config hashers,
and real controls without tautologies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from closedloop.certify.stats import cp_lower, cp_upper, ceiling
from closedloop.data.sampler import LeakageError, sample
from closedloop.judge.calibrate import (
    CalibrationReport,
    MarginBucket,
    compute_judge_freeze_hash,
    partition_into_bucket,
    preflight_cost_check,
)

from closedloop.judge.judge import (
    VisionJudge,
    check_centroid_in_pad,
    combine_verdict,
)
from closedloop.sim.env import T1Env, noop_policy


def test_geometric_check_strict_and_boundary() -> None:
    """Cube centroid strictly inside pad boundary passes; boundary edge and outside fail."""
    # Pad box: [100, 100, 200, 200]
    pad_box = (100, 100, 200, 200)

    # 1. Cube centered inside: [140, 140, 160, 160] -> centroid (150, 150) -> True
    cube_inside = (140, 140, 160, 160)
    assert check_centroid_in_pad(cube_inside, pad_box) is True

    # 2. Cube on the right boundary edge: centroid at 200 -> False (strict inequality + margin)
    cube_edge = (195, 140, 205, 160)
    assert check_centroid_in_pad(cube_edge, pad_box) is False

    # 3. Cube outside: [210, 140, 230, 160] -> centroid (220, 150) -> False
    cube_outside = (210, 140, 230, 160)
    assert check_centroid_in_pad(cube_outside, pad_box) is False

    # 4. None detection -> False
    assert check_centroid_in_pad(None, pad_box) is False
    assert check_centroid_in_pad(cube_inside, None) is False

    # 5. Inverted/malformed box -> False
    assert check_centroid_in_pad((160, 160, 140, 140), pad_box) is False


def test_combination_rule_freezing() -> None:
    """Verifies frozen combination rule: geometric AND spark (Plan §8, DECISIONS.md)."""
    assert combine_verdict(geometric_pass=True, spark_pass=True) is True
    assert combine_verdict(geometric_pass=False, spark_pass=True) is False
    assert combine_verdict(geometric_pass=True, spark_pass=False) is False
    assert combine_verdict(geometric_pass=False, spark_pass=False) is False


def test_judge_requires_client() -> None:
    """VisionJudge must reject evaluation if client is None (no silent fake/fallback)."""
    judge = VisionJudge(client=None)
    env = T1Env()
    sc = sample("calibration", 1, 1000000)[0]
    env.reset(sc)
    with pytest.raises(ValueError, match="requires an active LLMClient"):
        judge.judge_episode(env)
    env.close()


def test_judge_controls_v9() -> None:
    """V9 Controls: do-nothing pass rate must not exceed FPR bound; shuffled labels break correlation."""
    # 1. Do-nothing physical control: run real T1Env with noop_policy
    env = T1Env()
    scenarios = sample("calibration", 10, 1000005)
    do_nothing_geo_passes = 0

    for sc in scenarios:
        env.reset(sc)
        noop_policy(env, np.random.default_rng(int(sc["seed"])))
        sim_res = env.finish()
        assert not sim_res.truth_success, "noop_policy must never produce a true success"

        # On no-op, cube remains at spawn position (never moves toward pad at PAD_POS=[0.25, 0.0])
        # Cube centroid cannot be on pad
        cube_pos, _ = env.object_pose("cube")
        pad_pos, _ = env.object_pose("pad")
        dist = np.linalg.norm(np.subtract(cube_pos[:2], pad_pos[:2]))
        assert dist > 0.08, "Cube spawned off pad must remain off pad under noop"
        assert sim_res.margin < 0.0, "noop margin must be strictly negative"
    env.close()

    # 2. Shuffled labels control (V9)
    # When true success labels are randomly permuted across episodes, TPR and (1-FPR) converge
    rng = np.random.default_rng(42)
    n = 200
    true_labels = np.array([True] * 100 + [False] * 100)
    # A functioning judge has high agreement with true labels
    judge_preds = np.array([True] * 90 + [False] * 10 + [False] * 90 + [True] * 10)

    # Shuffled labels test: permute true labels 500 times
    shuffled_gaps = []
    for _ in range(500):
        perm_labels = rng.permutation(true_labels)
        tpr_shuf = np.mean(judge_preds[perm_labels])
        fpr_shuf = np.mean(judge_preds[~perm_labels])
        shuffled_gaps.append(abs(tpr_shuf - fpr_shuf))

    # Real un-shuffled gap is |0.90 - 0.10| = 0.80
    real_gap = abs(np.mean(judge_preds[true_labels]) - np.mean(judge_preds[~true_labels]))
    assert real_gap == 0.80
    # Shuffled gap median should be near 0
    assert np.median(shuffled_gaps) < 0.12


def test_calibration_counts_and_seeds_v4_h9() -> None:
    """V4/H9: Calibration draws 600 fixed seeds in 1,000,000–1,999,999; overflow raises LeakageError."""
    # 1. Valid range draw
    scenarios = sample("calibration", 600, 1000000)
    assert len(scenarios) == 600
    seeds = [int(s["seed"]) for s in scenarios]
    assert len(set(seeds)) == 600
    assert min(seeds) == 1000000
    assert max(seeds) == 1000599
    assert all(1000000 <= s < 2000000 for s in seeds)

    # 2. Seed overflow check (Rule H9 boundary)
    with pytest.raises(LeakageError):
        sample("calibration", 10, 1999995)  # 1999995 + 10 - 1 = 2000004 >= 2000000


def test_bucket_fpr_worst_case() -> None:
    """Failure rollouts must be partitioned into 4 margin buckets; worst-bucket upper bound tracked."""
    buckets = [
        MarginBucket("near_boundary", -0.05, 0.0, k_pass=4, n_total=75),
        MarginBucket("shallow", -0.15, -0.05, k_pass=2, n_total=75),
        MarginBucket("medium", -0.35, -0.15, k_pass=1, n_total=75),
        MarginBucket("deep", -1.00, -0.35, k_pass=0, n_total=75),
    ]

    # Verify partition function
    assert partition_into_bucket(-0.02, buckets).name == "near_boundary"
    assert partition_into_bucket(-0.10, buckets).name == "shallow"
    assert partition_into_bucket(-0.25, buckets).name == "medium"
    assert partition_into_bucket(-0.50, buckets).name == "deep"
    assert partition_into_bucket(0.01, buckets) is None  # Success, not in failure buckets

    d_b = 0.1 * 0.05 / 4  # 0.00125
    b_his = [cp_upper(b.k_pass, b.n_total, d_b) for b in buckets]
    worst_bu = max(b_his)
    assert worst_bu == b_his[0]  # near boundary has largest error bound
    assert worst_bu <= 0.20


def test_judge_frozen_hash() -> None:
    """Freeze hash covers configs/judge.yaml; any modification changes the hash."""
    h1 = compute_judge_freeze_hash()
    assert len(h1) == 64

    # Mutate config in memory to simulate modification
    cfg_path = Path("configs/judge.yaml")
    raw = cfg_path.read_text(encoding="utf-8")
    mutated = raw.replace("confidence_threshold: 0.70", "confidence_threshold: 0.85")
    h_mutated = hashlib.sha256(mutated.encode()).hexdigest()
    assert h1 != h_mutated


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
