"""Phase 02 Tasks 2-4 tests: env, predicates, margin, controls (written first).

Requires a real PyBullet install; no fakes (H8). Each test runs live episodes.
"""

import numpy as np
import pybullet  # noqa: F401  (fail loudly if the simulator is missing)

from closedloop.data.sampler import sample
from closedloop.sim.env import T1Env, good_policy, noop_policy, random_policy

NOMINAL = {"x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 0.1, "friction": 0.8,
           "seed": 7}


def test_scripted_episode_runs() -> None:
    """A scripted good policy succeeds at the nominal scenario (env works)."""
    env = T1Env()
    try:
        res = env.run_episode(good_policy, NOMINAL, seed=7)
    finally:
        env.close()
    assert res.truth_success, f"good policy failed at nominal: margin={res.margin}"


def test_determinism() -> None:
    """V1: same (policy, scenario, seed) twice gives identical results."""
    scenario = sample("repair", 1, 7)[0]
    env = T1Env()
    try:
        first = env.run_episode(good_policy, scenario, seed=7)
        second = env.run_episode(good_policy, scenario, seed=7)
    finally:
        env.close()
    assert first == second
    assert first.result_hash() == second.result_hash()


def test_negative_control() -> None:
    """V2: do-nothing scores 0%; seeded random actions score ~0%."""
    env = T1Env()
    try:
        done = env.run_episode(noop_policy, NOMINAL, seed=7)
        assert not done.truth_success
        assert done.margin < 0.0
        wins = sum(
            env.run_episode(random_policy, NOMINAL, seed=s).truth_success
            for s in range(10)
        )
    finally:
        env.close()
    assert wins == 0, f"random policy won {wins}/10 (predicate too loose?)"


def test_margin_sign() -> None:
    """Margin < 0 agrees with failure on every episode of a mixed batch."""
    scenarios = sample("repair", 6, 21)
    env = T1Env()
    try:
        results = [
            env.run_episode(pol, sc, seed=sc["seed"])
            for sc in scenarios
            for pol in (good_policy, noop_policy)
        ]
    finally:
        env.close()
    assert results, "batch produced no episodes"
    for res in results:
        assert (res.margin < 0.0) == (not res.truth_success)


def test_predicate_agreement() -> None:
    """V8: the two predicates disagree on at most 2% of episodes."""
    scenarios = sample("repair", 10, 99)
    env = T1Env()
    try:
        results = [
            env.run_episode(pol, sc, seed=sc["seed"])
            for sc in scenarios
            for pol in (good_policy, noop_policy)
        ]
    finally:
        env.close()
    disagreements = sum(1 for r in results if not r.agreed)
    rate = disagreements / len(results)
    print(f"\npredicate disagreement: {disagreements}/{len(results)} = {rate:.3f}")
    assert rate <= 0.02
