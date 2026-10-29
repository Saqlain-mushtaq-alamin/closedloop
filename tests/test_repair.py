"""Tests for repair protocol, acceptance, A/A null control, and H2/H3 (Phase 06).

Asserts:
- test_repair_acceptance_rejects_regression: repair failing regression set is rejected
- test_repair_acceptance_rejects_falsifier_failure: repair failing short rerun is rejected
- test_repair_acceptance_accepts_clean_repair: clean repair is accepted
- test_damage_rate_accounting: regression damage events detected and tracked by RepairEvaluator (V7)
- test_repair_evaluator_single_evaluation: counterexample evaluated once per attempt (no double-counting)
- test_build_repair_prompt: prompt builder formats current code, diagnostics, and primitives
- test_aa_null: A/A control verifies paired difference 95% CI contains 0 and rejects degenerate replay (V5)
- test_budget_parity: episodes and tokens per arm enforced within 5% tolerance (V6)
- test_h2_paired_diff: paired bootstrap CI computed for B2 vs B1 with non-trivial bounds
- test_h3_paired_diff: paired bootstrap CI computed for B3 vs B2 with non-trivial bounds
- test_filmstrip_rendering: multi-frame event boundary extraction with moving vs no-op policy contrast
"""

from __future__ import annotations

import hashlib
import numpy as np
import pytest

from closedloop.data.analysis import BudgetParityError, check_budget_parity, paired_bootstrap_ci
from closedloop.repair.filmstrip import generate_filmstrip
from closedloop.repair.repair import (
    DamageAccounting,
    RepairEvaluator,
    build_repair_prompt,
    verify_repair_acceptance,
)
from closedloop.sim.env import T1Env, good_policy, noop_policy


class FakeRepairPolicy:
    """Fake policy with configurable passing behavior for acceptance testing (H8 Fake*)."""

    def __init__(self, name: str, pass_keys: set[str]) -> None:
        self.name = name
        self.pass_keys = pass_keys
        self.eval_counts: dict[str, int] = {}

    def evaluate(self, scenario: dict) -> dict:
        key = str(scenario.get("id", scenario.get("mass", 0.0)))
        self.eval_counts[key] = self.eval_counts.get(key, 0) + 1
        passed = key in self.pass_keys
        return {
            "truth_success": passed,
            "truth_success_alt": passed,
            "margin": 0.01 if passed else -0.1,
            "scenario": dict(scenario),
        }


def test_repair_acceptance_rejects_regression() -> None:
    """A repair that fixes the counterexample but breaks any regression scenario must be rejected."""
    s_nom = {"id": "s_nom", "mass": 1.0, "x": 0.0, "y": 0.0}
    s_prior = {"id": "s_prior", "mass": 2.5, "x": 0.0, "y": 0.0}
    s_counter = {"id": "s_counter", "mass": 6.5, "x": 0.0, "y": 0.0}
    regression_set = [s_nom, s_prior]

    # Candidate fixes s_counter and s_nom, but breaks s_prior (regression)
    candidate_policy = FakeRepairPolicy("cand", pass_keys={"s_counter", "s_nom"})

    accepted, reason, details = verify_repair_acceptance(
        candidate_eval_fn=candidate_policy.evaluate,
        counterexample=s_counter,
        regression_set=regression_set,
        falsifier_fn=lambda eval_fn: None,
    )

    assert not accepted, "Candidate with regression was accepted!"
    assert "regression" in reason.lower()
    assert details["failed_regression_id"] == "s_prior"


def test_repair_acceptance_rejects_falsifier_failure() -> None:
    """A repair that passes counterexample and regression set but fails short falsifier rerun must be rejected."""
    s_nom = {"id": "s_nom", "mass": 1.0}
    s_counter = {"id": "s_counter", "mass": 6.5}
    regression_set = [s_nom]

    candidate_policy = FakeRepairPolicy("cand", pass_keys={"s_counter", "s_nom"})
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

    candidate_policy = FakeRepairPolicy("cand", pass_keys={"s_counter", "s_nom"})
    mock_falsifier = lambda eval_fn: None

    accepted, reason, details = verify_repair_acceptance(
        candidate_eval_fn=candidate_policy.evaluate,
        counterexample=s_counter,
        regression_set=regression_set,
        falsifier_fn=mock_falsifier,
    )

    assert accepted, f"Clean candidate was rejected: {reason}"
    assert reason == "accepted"


def test_damage_rate_accounting() -> None:
    """RepairEvaluator accumulates regression set and tracks damage events (V7)."""
    evaluator = RepairEvaluator(falsifier_budget=5)
    s_nom = {"id": "s_nom", "mass": 1.0}
    evaluator.add_to_regression_set(s_nom)

    # Attempt 1: Fixes ce1, passes nominal -> Accepted, ce1 added to regression set
    ce1 = {"id": "ce1", "mass": 4.0}
    cand1 = FakeRepairPolicy("cand1", pass_keys={"s_nom", "ce1"})
    acc1, _, _ = evaluator.evaluate_candidate(cand1.evaluate, ce1)
    assert acc1 is True
    assert len(evaluator.regression_set) == 2  # s_nom + ce1

    # Attempt 2: Fixes ce2, but breaks ce1 (regression damage event) -> Rejected
    ce2 = {"id": "ce2", "mass": 6.0}
    cand2 = FakeRepairPolicy("cand2", pass_keys={"s_nom", "ce2"})  # breaks ce1
    acc2, reason2, _ = evaluator.evaluate_candidate(cand2.evaluate, ce2)
    assert acc2 is False
    assert "regression" in reason2.lower()
    assert evaluator.accounting.damage_count == 1

    # Attempt 3: Does not fix ce3 -> Rejected, no damage
    ce3 = {"id": "ce3", "mass": 8.0}
    cand3 = FakeRepairPolicy("cand3", pass_keys={"s_nom", "ce1"})  # fails ce3
    acc3, reason3, _ = evaluator.evaluate_candidate(cand3.evaluate, ce3)
    assert acc3 is False
    assert "counterexample" in reason3.lower()

    # Attempt 4: Clean fix of ce3 preserving s_nom and ce1 -> Accepted
    cand4 = FakeRepairPolicy("cand4", pass_keys={"s_nom", "ce1", "ce3"})
    acc4, _, _ = evaluator.evaluate_candidate(cand4.evaluate, ce3)
    assert acc4 is True

    assert evaluator.accounting.total_attempts == 4
    assert evaluator.accounting.fixed_count == 3  # cand1, cand2, cand4 fixed CE
    assert evaluator.accounting.damage_count == 1  # cand2 damaged regression
    assert evaluator.accounting.accepted_count == 2  # cand1, cand4 accepted
    assert evaluator.accounting.repair_rate == 0.75
    assert evaluator.accounting.damage_rate == 0.25
    assert evaluator.accounting.acceptance_rate == 0.50


def test_repair_evaluator_single_evaluation() -> None:
    """RepairEvaluator evaluates candidate on the counterexample exactly once per attempt."""
    evaluator = RepairEvaluator()
    ce = {"id": "ce_unique", "mass": 3.0}
    cand = FakeRepairPolicy("cand", pass_keys={"ce_unique"})

    acc, _, _ = evaluator.evaluate_candidate(cand.evaluate, ce)
    assert acc is True
    assert cand.eval_counts["ce_unique"] == 1, "Counterexample was evaluated multiple times!"


def test_build_repair_prompt() -> None:
    """Prompt builder provides current code, minimal counterexample, margin, and primitives."""
    curr_code = "def policy(env, rng):\n    pass"
    ce = {"x": 0.05, "y": -0.02, "mass": 5.5, "friction": 0.3}
    primitives_doc = "move_to, close_gripper, open_gripper"

    prompt = build_repair_prompt(
        curr_code,
        ce,
        primitives_doc,
        margin=-0.125,
        trace_summary="Cube dropped during transit",
        filmstrip_description="Frame 2: grasp missed",
    )

    assert "def policy(env, rng):" in prompt
    assert "mass=5.500" in prompt or "mass=5.5" in prompt
    assert "friction=0.300" in prompt or "friction=0.3" in prompt
    assert "Margin: -0.1250" in prompt
    assert "Cube dropped during transit" in prompt
    assert "Frame 2: grasp missed" in prompt
    assert "move_to, close_gripper" in prompt


def test_aa_null() -> None:
    """A/A control: independent replicates yield CI containing 0; degenerate replays flagged (V5)."""
    # 1. Independent replicates from identical distribution
    rng = np.random.default_rng(999)
    n_trajectories = 25
    b2_scores = rng.binomial(4, 0.75, size=n_trajectories) / 4.0
    b2_alt_scores = rng.binomial(4, 0.75, size=n_trajectories) / 4.0

    res = paired_bootstrap_ci(b2_scores, b2_alt_scores, n_resamples=10000, seed=42)
    ci_low = float(res["ci_lower"])
    ci_high = float(res["ci_upper"])
    assert ci_low <= 0.0 <= ci_high, f"A/A CI [{ci_low:.3f}, {ci_high:.3f}] excludes 0"

    # 2. Degenerate replay (element-wise identical scores with zero variance) must be detected
    identical_scores = np.array([0.75] * n_trajectories)
    deg_res = paired_bootstrap_ci(identical_scores, identical_scores, n_resamples=1000)
    is_degenerate = (float(deg_res["ci_lower"]) == 0.0 and float(deg_res["ci_upper"]) == 0.0 and float(deg_res["diff"]) == 0.0)
    assert is_degenerate, "Degenerate identical scores failed detection"


def test_budget_parity() -> None:
    """Budget parity: episodes and tokens per arm must be within 5% (V6)."""
    # 1. Valid matching budgets (<= 5%)
    check_budget_parity({
        "arm1": {"episodes": 120, "tokens": 40000},
        "arm2": {"episodes": 122, "tokens": 41500},
    }, max_rel_diff=0.05)

    # 2. Episode disparity > 5% must raise BudgetParityError
    with pytest.raises(BudgetParityError, match="episodes difference"):
        check_budget_parity({
            "arm1": {"episodes": 100, "tokens": 40000},
            "arm2": {"episodes": 110, "tokens": 40000},
        }, max_rel_diff=0.05)

    # 3. Token disparity > 5% must raise BudgetParityError
    with pytest.raises(BudgetParityError, match="tokens difference"):
        check_budget_parity({
            "arm1": {"episodes": 100, "tokens": 40000},
            "arm2": {"episodes": 100, "tokens": 44000},
        }, max_rel_diff=0.05)


def test_h2_paired_diff() -> None:
    """H2 paired difference computation on B2 (falsifier) vs B1 (random) detects superior arm."""
    b1_scores = np.array([0.25, 0.50, 0.25, 0.50, 0.25, 0.50, 0.25, 0.50, 0.25, 0.50])
    b2_scores = np.array([0.75, 1.00, 0.75, 0.75, 1.00, 0.75, 1.00, 0.75, 0.75, 1.00])

    res = paired_bootstrap_ci(b2_scores, b1_scores, n_resamples=10000, seed=100)
    mean_diff = float(res["diff"])
    ci_low = float(res["ci_lower"])
    ci_high = float(res["ci_upper"])

    assert mean_diff >= 0.40
    assert ci_low > 0.0, "Expected significant positive difference for superior arm"
    assert ci_high > ci_low


def test_h3_paired_diff() -> None:
    """H3 paired difference computation asserts valid confidence bounds."""
    b2_scores = np.array([0.75, 0.75, 0.75, 0.50, 0.75, 0.75, 0.50, 0.75, 0.75, 0.75])
    b3_scores = np.array([0.75, 1.00, 0.75, 0.75, 1.00, 0.75, 0.75, 1.00, 0.75, 1.00])

    res = paired_bootstrap_ci(b3_scores, b2_scores, n_resamples=10000, seed=200)
    mean_diff = float(res["diff"])
    ci_low = float(res["ci_lower"])
    ci_high = float(res["ci_upper"])

    assert mean_diff > 0.0
    assert ci_low > -0.10
    assert ci_high > ci_low


def test_filmstrip_rendering() -> None:
    """Filmstrip renderer extracts requested number of frames and differentiates moving vs noop policy."""
    env = T1Env()
    try:
        sc = {"x": 0.05, "y": -0.05, "yaw": 0.1, "mass": 3.0, "friction": 0.5}

        # 1. Request 6 frames: must return exactly 6 frames
        strip_noop = generate_filmstrip(env, sc, noop_policy, seed=1000, num_frames=6)
        assert len(strip_noop["images_b64"]) == 6
        assert len(strip_noop["descriptions"]) == 6

        # 2. Moving policy: must return 6 frames and have different content from noop
        strip_move = generate_filmstrip(env, sc, good_policy, seed=1000, num_frames=6)
        assert len(strip_move["images_b64"]) == 6

        # Frame 1 is initial (identical scene before action)
        h1_noop = hashlib.sha256(strip_noop["images_b64"][0].encode()).hexdigest()
        h1_move = hashlib.sha256(strip_move["images_b64"][0].encode()).hexdigest()
        assert h1_noop == h1_move, "Initial frame 1 should match for same scenario"

        # Subsequent frames must differ between moving policy and noop policy
        h_mid_noop = hashlib.sha256(strip_noop["images_b64"][2].encode()).hexdigest()
        h_mid_move = hashlib.sha256(strip_move["images_b64"][2].encode()).hexdigest()
        assert h_mid_noop != h_mid_move, "Moving policy produced identical frame to noop policy!"
    finally:
        env.close()
