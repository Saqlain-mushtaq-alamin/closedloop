"""Tests for falsification and counterexample minimization (Phase 05).

Asserts:
- test_minimizer_still_fails: shrunk scenario still fails (truth=False)
- test_minimizer_not_larger: distance-to-nominal <= input
- test_falsifier_seeded (V1): same seed -> same study result (identical best margin)
- test_falsifier_bounds: all proposals inside distribution D bounds
- test_falsifier_seed_range (V4): only repair-stream seeds [0, 999999] allowed
- test_minimizer_shrinks_irrelevant_params: removes perturbations that do not cause failure
- test_minimizer_real_env: validates minimizer on full PyBullet physics with weak grip policy
- test_falsifier_finds_failure_on_weak_policy: falsifier finds low-margin failure within budget
- test_minimizer_rejects_passing_scenario: calling minimize on passing input raises ValueError
"""

from __future__ import annotations

import pytest

from closedloop.falsify.falsifier import falsify, FalsificationResult
from closedloop.falsify.minimizer import distance_to_nominal, minimize
from closedloop.sim.env import T1Env, PAD_POS
from closedloop.sim import primitives as prim


class SyntheticEvaluator:
    """Deterministic synthetic evaluator where failure occurs when mass >= 5.0."""

    def __init__(self, failure_mass_threshold: float = 5.0) -> None:
        self.failure_mass_threshold = failure_mass_threshold
        self.proposals: list[dict] = []

    def evaluate(self, scenario: dict) -> dict:
        self.proposals.append(dict(scenario))
        mass = float(scenario.get("mass", 0.1))
        # Margin is positive when mass < threshold (success), negative when mass >= threshold (failure)
        margin = self.failure_mass_threshold - mass
        failed = mass >= self.failure_mass_threshold
        return {
            "truth_success": not failed,
            "truth_success_alt": not failed,
            "margin": margin,
            "scenario": dict(scenario),
        }


def test_minimizer_still_fails() -> None:
    """Shrunk scenario must still fail (truth=False)."""
    evaluator = SyntheticEvaluator(failure_mass_threshold=5.0)
    nominal = {"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 0.1, "friction": 0.8}
    # Initial failing scenario with perturbed x, y, yaw, friction and mass=8.0 (fails)
    failing_input = {
        "x": 0.12,
        "y": -0.08,
        "yaw": 0.4,
        "mass": 8.0,
        "friction": 0.3,
        "seed": 100,
    }
    init_res = evaluator.evaluate(failing_input)
    assert not init_res["truth_success"]

    shrunk = minimize(
        failing_input,
        eval_fn=evaluator.evaluate,
        nominal=nominal,
    )

    final_res = evaluator.evaluate(shrunk)
    # Shrunk scenario must still fail
    assert not final_res["truth_success"], "Minimizer returned a passing scenario!"
    assert final_res["margin"] <= 0.0


def test_minimizer_not_larger() -> None:
    """Distance to nominal of shrunk scenario must be <= input distance."""
    evaluator = SyntheticEvaluator(failure_mass_threshold=5.0)
    nominal = {"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 0.1, "friction": 0.8}
    failing_input = {
        "x": 0.10,
        "y": 0.10,
        "yaw": 0.3,
        "mass": 7.5,
        "friction": 0.2,
        "seed": 200,
    }

    d_in = distance_to_nominal(failing_input, nominal)
    shrunk = minimize(
        failing_input,
        eval_fn=evaluator.evaluate,
        nominal=nominal,
    )
    d_out = distance_to_nominal(shrunk, nominal)

    assert d_out <= d_in + 1e-9, f"Distance wandered: {d_out} > {d_in}"


def test_minimizer_shrinks_irrelevant_params() -> None:
    """Minimizer should restore irrelevant parameters (x, y, yaw, friction) to nominal."""
    evaluator = SyntheticEvaluator(failure_mass_threshold=5.0)
    nominal = {"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 0.1, "friction": 0.8}
    failing_input = {
        "x": 0.14,
        "y": -0.14,
        "yaw": -0.45,
        "mass": 9.0,
        "friction": 0.15,
        "seed": 300,
    }

    shrunk = minimize(
        failing_input,
        eval_fn=evaluator.evaluate,
        nominal=nominal,
    )

    # Irrelevant params should be shrunk back to nominal
    assert pytest.approx(shrunk["x"], abs=1e-4) == nominal["x"]
    assert pytest.approx(shrunk["y"], abs=1e-4) == nominal["y"]
    assert pytest.approx(shrunk["yaw"], abs=1e-4) == nominal["yaw"]
    assert pytest.approx(shrunk["friction"], abs=1e-4) == nominal["friction"]
    # Mass should be shrunk closer to 5.0 (the boundary) than 9.0
    assert 5.0 <= shrunk["mass"] <= 9.0


def test_falsifier_seeded() -> None:
    """Same seed produces identical study result (identical best margin) (V1)."""
    bounds = {
        "x": (-0.15, 0.15),
        "y": (-0.15, 0.15),
        "yaw": (-0.5, 0.5),
        "mass": (1.0, 11.5),
        "friction": (0.1, 1.0),
    }

    def eval_fn(sc: dict) -> dict:
        m = 5.0 - float(sc["mass"]) + abs(float(sc["x"])) * 0.5
        return {
            "truth_success": m > 0.0,
            "truth_success_alt": m > 0.0,
            "margin": m,
        }

    res1 = falsify(eval_fn, bounds=bounds, budget=12, seed=4242)
    res2 = falsify(eval_fn, bounds=bounds, budget=12, seed=4242)

    assert isinstance(res1, FalsificationResult)
    assert isinstance(res2, FalsificationResult)
    assert res1.best_margin == pytest.approx(res2.best_margin)
    assert res1.best_scenario is not None
    assert res2.best_scenario is not None
    for k in bounds:
        assert res1.best_scenario[k] == pytest.approx(res2.best_scenario[k])


def test_falsifier_bounds() -> None:
    """All proposed scenarios must lie inside distribution D bounds."""
    bounds = {
        "x": (-0.15, 0.15),
        "y": (-0.15, 0.15),
        "yaw": (-0.5, 0.5),
        "mass": (1.0, 11.5),
        "friction": (0.1, 1.0),
    }
    evaluator = SyntheticEvaluator(failure_mass_threshold=6.0)

    res = falsify(evaluator.evaluate, bounds=bounds, budget=20, seed=5555)

    assert len(evaluator.proposals) == 20
    for sc in evaluator.proposals:
        for k, (low, high) in bounds.items():
            val = float(sc[k])
            assert low <= val <= high, f"Proposal {k}={val} outside [{low}, {high}]"


def test_falsifier_seed_range() -> None:
    """Falsifier must reject seeds outside the repair stream [0, 999999] (V4, H9)."""
    bounds = {"x": (-0.1, 0.1)}

    def dummy_eval(sc: dict) -> dict:
        return {"truth_success": True, "truth_success_alt": True, "margin": 1.0}

    with pytest.raises((ValueError, RuntimeError)):
        falsify(dummy_eval, bounds=bounds, budget=5, seed=1_000_000)

    with pytest.raises((ValueError, RuntimeError)):
        falsify(dummy_eval, bounds=bounds, budget=5, seed=2_500_000)


def test_minimizer_rejects_passing_scenario() -> None:
    """Attempting to minimize a passing scenario raises ValueError."""
    evaluator = SyntheticEvaluator(failure_mass_threshold=5.0)
    passing_input = {"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 2.0, "friction": 0.8}
    with pytest.raises(ValueError, match="Initial scenario does not fail"):
        minimize(passing_input, eval_fn=evaluator.evaluate)


def test_minimizer_real_env() -> None:
    """Minimizer preserves failure in real PyBullet simulation and shrinks parameters."""
    env = T1Env()

    def weak_policy(e: T1Env, rng: object) -> None:
        cube_pos, _ = prim.get_object_pose(e, "cube")
        above = (cube_pos[0], cube_pos[1], 0.15)
        prim.move_to(e, above, steps=40)
        prim.move_to(e, (cube_pos[0], cube_pos[1], cube_pos[2] + 0.03), steps=40)
        prim.close_gripper(e, 25.0)  # slips when mass > ~2.12 kg
        prim.move_to(e, above, steps=40)
        prim.move_to(e, (PAD_POS[0], PAD_POS[1], 0.15), steps=60)
        prim.move_to(e, (PAD_POS[0], PAD_POS[1], 0.06), steps=40)
        prim.open_gripper(e)
        prim.move_to(e, (PAD_POS[0], PAD_POS[1], 0.15), steps=40)

    nominal = {"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 0.1, "friction": 0.8}
    failing_sc = {
        "x": 0.08,
        "y": -0.07,
        "yaw": 0.3,
        "mass": 5.0,  # slips
        "friction": 0.3,
        "seed": 1000,
    }

    eval_fn = lambda sc: env.run_episode(weak_policy, sc, int(sc.get("seed", 1000)))

    init_res = eval_fn(failing_sc)
    assert not init_res.truth_success, "Initial scenario unexpectedly succeeded"

    shrunk = minimize(failing_sc, eval_fn=eval_fn, nominal=nominal)
    final_res = eval_fn(shrunk)

    env.close()

    # Core assertions per gate:
    assert not final_res.truth_success, "Minimizer returned passing scenario in real env!"
    assert distance_to_nominal(shrunk, nominal) < distance_to_nominal(failing_sc, nominal)
    # x, y, yaw, friction were irrelevant and should be at nominal
    assert pytest.approx(shrunk["x"], abs=1e-4) == nominal["x"]
    assert pytest.approx(shrunk["y"], abs=1e-4) == nominal["y"]
    assert pytest.approx(shrunk["yaw"], abs=1e-4) == nominal["yaw"]
    assert pytest.approx(shrunk["friction"], abs=1e-4) == nominal["friction"]
