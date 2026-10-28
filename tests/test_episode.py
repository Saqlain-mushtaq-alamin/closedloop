"""Episode builder/result-check tests (written first; no pybullet, no network).

Fixtures are plain dicts: the child returns SimResult-as-data, so no
simulator import is needed to validate the trust boundary.
"""

import math

import pytest

from closedloop.exec.episode import (
    EpisodeError,
    build_episode_code,
    check_result,
)

POLICY = "def policy(env, rng):\n    env.open_gripper()\n"
SCENARIO = {"x": 0.05, "y": -0.02, "yaw": 0.1, "mass": 0.2,
            "friction": 0.5, "seed": 100}


def _good_result(**kw):
    base = {
        "truth_success": True, "truth_success_alt": True, "margin": 0.012,
        "final_pos": [0.25, 0.0, 0.03], "steps": 300, "agreed": True,
        "trace": [[i, [0.0, 0.0, 0.02]] for i in range(1, 301)],
    }
    base.update(kw)
    return base


def test_build_embeds_everything() -> None:
    """Built code carries scenario, seed, policy source, and isolation."""
    code = build_episode_code(SCENARIO, 100, POLICY, repo_root="/repo")
    assert '"x": 0.05' in code and "100" in code
    assert "def policy(env, rng)" in code  # embedded as data string
    assert "PolicyFacade" in code and "__result__" in code
    assert "_prog_ns" in code  # policy runs in a restricted sub-namespace
    assert "/repo" in code  # child-side import root travels as data


def test_check_result_accepts_good() -> None:
    """A well-formed result passes through with its fields."""
    out = check_result(_good_result())
    assert out["truth_success"] is True
    assert out["margin"] == pytest.approx(0.012)


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("margin"),
    lambda d: d.update(margin=float("nan")),
    lambda d: d.update(margin=True),
    lambda d: d.update(truth_success="yes"),
    lambda d: d.update(steps=0),
    lambda d: d.update(trace=[]),
    lambda d: d.update(final_pos=[0.0, 0.0]),
    lambda d: d.update(trace=[[2, [0, 0, 0]]] + d["trace"]),
])
def test_check_result_rejects_malformed(mutate) -> None:  # type: ignore[no-untyped-def]
    """B5: malformed results raise instead of becoming numbers."""
    bad = _good_result()
    mutate(bad)
    with pytest.raises(EpisodeError):
        check_result(bad)


def test_check_result_rejects_nondict() -> None:
    """Non-dict payloads (crashes, strings) raise."""
    with pytest.raises(EpisodeError):
        check_result("ok")
    with pytest.raises(EpisodeError):
        check_result(None)


def test_check_result_rejects_nonfinite_trace() -> None:
    """NaN inside the trace raises (no silent poisoning of statistics)."""
    bad = _good_result()
    bad["trace"][10][1][0] = math.inf
    with pytest.raises(EpisodeError):
        check_result(bad)


if __name__ == "__main__":
    pytest.main([__file__])
