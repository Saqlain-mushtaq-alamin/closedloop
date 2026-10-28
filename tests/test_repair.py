"""Tests for repair protocol, acceptance, A/A null control, and H2/H3 (Phase 06).

Asserts:
- test_repair_acceptance: repair failing regression set or falsifier rerun is rejected
- test_damage_rate_accounting: damage events counted when repairs break regression set (V7)
- test_aa_null: same arm twice yields paired bootstrap difference 95% CI containing 0 (V5)
- test_budget_parity: episodes and tokens per arm enforced within 5% tolerance (V6)
- test_h2_paired_diff: paired bootstrap CI computed for B2 vs B1
- test_h3_paired_diff: paired bootstrap CI computed for B3 vs B2
"""

from __future__ import annotations

import numpy as np
import pytest

from closedloop.data.analysis import BudgetParityError, check_budget_parity, paired_bootstrap_ci
from closedloop.repair.repair import (
    DamageAccounting,
    RepairCandidate,
    RepairEvaluator,
    verify_repair_acceptance,
)


class FakeRepairPolicy:
    """Fake policy with configurable passing behavior for acceptance testing (H8 Fake*)."""

    def __init__(self, name: str, pass_keys: set[str]) -> None:
        self.name = name
        self.pass_keys = pass_keys

    def evaluate(self, scenario: dict) -> dict:
        key = scenario.get("id", str(scenario.get("mass", 0.0)))
        passed = key in self.pass_keys
        return {
            "truth_success": passed,
            "truth_success_alt": passed,
            "margin": 0.01 if passed else -0.1,
            "scenario": dict(scenario),
        }


def test_repair_acceptance_rejects_regression() -> None:
    """A repair that fixes the counterexample but breaks any regression scenario must be rejected."""
    # S_nominal and S_prior are earlier scenarios in the regression set
    s_nom = {"id": "s_nom", "mass": 1.0, "x": 0.0, "y": 0.0}
    s_prior = {"id": "s_prior", "mass": 2.5, "x": 0.0, "y": 0.0}
    # S_counter is the minimal counterexample the candidate aims to fix
    s_counter = {"id": "s_counter", "mass": 6.5, "x": 0.0, "y": 0.0}
    regression_set = [s_nom, s_prior]

    # Candidate fixes s_counter and s_nom, but breaks s_prior (regression)
    candidate_policy = FakeRepairPolicy("cand", pass_keys={"s_counter", "s_nom"})

    accepted, reason, details = verify_repair_acceptance(
        candidate_eval_fn=candidate_policy.evaluate,
        counterexample=s_counter,
        regression_set=regression_set,
        falsifier_fn=lambda eval_fn: None,  # would pass falsifier if reached
    )

    assert not accepted, "Candidate with regression was accepted!"
    assert "regression" in reason.lower()
    assert details["failed_regression_id"] == "s_prior"


def test_repair_acceptance_rejects_falsifier_failure() -> None:
    """A repair that passes counterexample and regression set but fails short falsifier rerun must be rejected."""
    s_nom = {"id": "s_nom", "mass": 1.0}
    s_counter = {"id": "s_counter", "mass": 6.5}
    regression_set = [s_nom]

    # Candidate passes counterexample and regression set
    candidate_policy = FakeRepairPolicy("cand", pass_keys={"s_counter", "s_nom"})

    # Falsifier re-run finds a failing scenario
    failing_nearby = {"id": "s_nearby_fail", "mass": 6.8}
    mock_falsifier = lambda eval_fn: failing_nearby

    accepted, reason, details = verify_repair_acceptance(
        candidate_eval_fn=candidate_policy.evaluate,
        counterexample=s_counter,
        regression_set=regression_set,
        falsifier_fn=mock_falsifier,
    )

    assert not accepted, "Candidate failing falsifier rerun was accepted!"
    assert "falsifier" in reason.lower()


def test_repair_acceptance_accepts_clean_repair() -> None:
    """A repair that passes counterexample, regression set, and falsifier rerun is accepted."""
    s_nom = {"id": "s_nom", "mass": 1.0}
    s_counter = {"id": "s_counter", "mass": 6.5}
    regression_set = [s_nom]

    # Candidate passes everything
    candidate_policy = FakeRepairPolicy("cand", pass_keys={"s_counter", "s_nom"})
    mock_falsifier = lambda eval_fn: None  # no failure found in short rerun

    accepted, reason, details = verify_repair_acceptance(
        candidate_eval_fn=candidate_policy.evaluate,
        counterexample=s_counter,
        regression_set=regression_set,
        falsifier_fn=mock_falsifier,
    )

    assert accepted, f"Clean candidate was rejected: {reason}"
    assert reason == "accepted"


def test_damage_rate_accounting() -> None:
    """Repairs that break previously passing scenarios must be counted in damage rate (V7)."""
    acc = DamageAccounting()
    assert acc.total_attempts == 0
    assert acc.damage_rate == 0.0

    # Attempt 1: successful repair, no damage
    acc.record_attempt(fixed_counterexample=True, damaged_regression=False, accepted=True)
    # Attempt 2: fixed counterexample but damaged regression (damage event)
    acc.record_attempt(fixed_counterexample=True, damaged_regression=True, accepted=False)
    # Attempt 3: did not fix counterexample, did not damage regression
    acc.record_attempt(fixed_counterexample=False, damaged_regression=False, accepted=False)
    # Attempt 4: successful repair, no damage
    acc.record_attempt(fixed_counterexample=True, damaged_regression=False, accepted=True)

    assert acc.total_attempts == 4
    assert acc.fixed_count == 3
    assert acc.damage_count == 1
    assert acc.accepted_count == 2
    assert acc.repair_rate == 0.75  # 3/4
    assert acc.damage_rate == 0.25  # 1/4 (25% <= 30% expected threshold)


def test_aa_null() -> None:
    """A/A control: same arm evaluated twice yields paired bootstrap 95% CI containing 0.0 (V5)."""
    rng = np.random.default_rng(12345)
    n_trajectories = 25
    # Both arms draw from identical Bernoulli distribution with p = 0.75
    arm_a = rng.binomial(1, 0.75, size=n_trajectories).astype(float)
    arm_b = rng.binomial(1, 0.75, size=n_trajectories).astype(float)

    res = paired_bootstrap_ci(arm_a, arm_b, n_resamples=10000, seed=42)
    ci_low = float(res["ci_lower"])
    ci_high = float(res["ci_upper"])

    # V5 assertion: 95% CI must contain 0.0
    assert ci_low <= 0.0 <= ci_high, f"A/A null control failed: CI [{ci_low:.3f}, {ci_high:.3f}] excludes 0"


def test_budget_parity() -> None:
    """Budget parity: episodes and tokens per arm must be within 5% (V6)."""
    # 1. Matching budgets (within 5%)
    check_budget_parity({
        "arm1": {"episodes": 120, "tokens": 40000},
        "arm2": {"episodes": 122, "tokens": 41000},  # 1.6% and 2.5% diff
    })

    # 2. Episode disparity > 5% must raise BudgetParityError
    with pytest.raises(BudgetParityError, match="episodes difference"):
        check_budget_parity({
            "arm1": {"episodes": 100, "tokens": 40000},
            "arm2": {"episodes": 110, "tokens": 40000},  # 9.5% diff
        })

    # 3. Token disparity > 5% must raise BudgetParityError
    with pytest.raises(BudgetParityError, match="tokens difference"):
        check_budget_parity({
            "arm1": {"episodes": 100, "tokens": 40000},
            "arm2": {"episodes": 100, "tokens": 43000},  # 7.2% diff
        })


def test_h2_paired_diff() -> None:
    """H2 paired difference computation on B2 (falsifier) vs B1 (random)."""
    b1_scores = np.array([0.5, 0.6, 0.75, 0.5, 0.8, 0.6, 0.7, 0.75, 0.6, 0.5])
    b2_scores = np.array([0.75, 0.8, 0.85, 0.75, 0.85, 0.7, 0.8, 0.9, 0.75, 0.7])

    res = paired_bootstrap_ci(b2_scores, b1_scores, n_resamples=10000, seed=100)
    mean_diff = float(res["diff"])
    ci_low = float(res["ci_lower"])
    ci_high = float(res["ci_upper"])

    assert mean_diff > 0.0
    assert ci_low < mean_diff < ci_high
    assert isinstance(ci_low, float) and isinstance(ci_high, float)


def test_h3_paired_diff() -> None:
    """H3 paired difference computation on B3 (multimodal filmstrip) vs B2 (text only)."""
    b2_scores = np.array([0.7, 0.75, 0.8, 0.7, 0.85, 0.75, 0.8, 0.85, 0.75, 0.8])
    b3_scores = np.array([0.8, 0.85, 0.85, 0.75, 0.9, 0.85, 0.9, 0.85, 0.8, 0.85])

    res = paired_bootstrap_ci(b3_scores, b2_scores, n_resamples=10000, seed=200)
    mean_diff = float(res["diff"])
    ci_low = float(res["ci_lower"])
    ci_high = float(res["ci_upper"])

    assert ci_low < mean_diff < ci_high
    assert isinstance(ci_low, float) and isinstance(ci_high, float)


def test_filmstrip_rendering() -> None:
    """Filmstrip renderer extracts valid base64 PNG frames at event boundaries."""
    from closedloop.repair.filmstrip import generate_filmstrip
    from closedloop.sim.env import T1Env, noop_policy

    env = T1Env()
    try:
        sc = {"x": 0.05, "y": -0.05, "yaw": 0.1, "mass": 3.0, "friction": 0.5}
        strip = generate_filmstrip(env, sc, noop_policy, seed=1000)
        assert len(strip["images_b64"]) >= 3
        for b64 in strip["images_b64"]:
            assert b64.startswith("iVBORw0KGgo")  # Standard PNG header in base64
        assert "Initial" in strip["summary"]
    finally:
        env.close()

