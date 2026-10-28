"""G0 episode assembly: one trusted code string per (scenario, policy).

The built string runs a trusted preamble (repo root fix, env build from
embedded scenario JSON, seeded rng, restricted facade), then executes the
untrusted policy source inside a sub-namespace holding ONLY the facade and
the rng, calls policy, and publishes a plain-data __result__ (SimResult as
a dict). The parent only accepts shape-validated results (check_result);
truth itself comes from the project's own finish() code, never from the
policy. Needs closedloop.sim.env importable in the child (allow-listed).
"""

from __future__ import annotations

import json
import math

ALLOW_MODULES = frozenset(
    {"closedloop.sim", "numpy", "pybullet", "dataclasses", "math", "random"}
)

POLICY_API_DOC = (
    "Define policy(env, rng) using ONLY these env methods: "
    "move_to(pos, steps=60) where pos is (x, y, z), open_gripper(), close_gripper(force), "
    "get_object_pos(name) which returns (x, y, z) position, "
    "get_object_pose(name) which returns (pos, orientation) where pos is (x, y, z). "
    "Use the provided rng for any randomness. Do not import anything."
)

PREAMBLE_TEMPLATE = """import sys as _sys
_sys.path.insert(0, {repo_root!r})
from closedloop.sim.env import T1Env, PolicyFacade
import numpy as _np
_env = T1Env()
try:
    _env.reset({scenario_json})
    _rng = _np.random.default_rng({seed})
    _prog_ns = {{"env": PolicyFacade(_env), "rng": _rng}}
    exec({policy_src}, _prog_ns)
    if "policy" not in _prog_ns:
        raise NameError("program defines no policy(env, rng)")
    import dataclasses as _dc
    __result__ = _dc.asdict(_env.run_policy(_prog_ns["policy"], _rng))
finally:
    _env.close()
"""



class EpisodeError(ValueError):
    """A result payload that must not become a number (B5)."""


def build_episode_code(scenario: dict, seed: int, policy_code: str,
                       repo_root: str) -> str:
    """Assemble the single trusted episode string (data embedded as JSON)."""
    return PREAMBLE_TEMPLATE.format(
        repo_root=repo_root,
        scenario_json=json.dumps(scenario, sort_keys=True),
        seed=int(seed),
        policy_src=json.dumps(policy_code),
    )


def _is_finite_number(value: object) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value))


def check_result(obj: object) -> dict:
    """Validate a child result dict; raise EpisodeError on anything malformed."""
    if not isinstance(obj, dict):
        raise EpisodeError(f"result is not a dict: {type(obj).__name__}")
    for key in ("truth_success", "truth_success_alt", "agreed"):
        if not isinstance(obj.get(key), bool):
            raise EpisodeError(f"bad {key}: {obj.get(key)!r}")
    if not _is_finite_number(obj.get("margin")):
        raise EpisodeError(f"bad margin: {obj.get('margin')!r}")
    steps = obj.get("steps")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
        raise EpisodeError(f"bad steps: {steps!r}")
    final = obj.get("final_pos")
    if (not isinstance(final, (list, tuple)) or len(final) != 3
            or not all(_is_finite_number(c) for c in final)):
        raise EpisodeError(f"bad final_pos: {final!r}")
    trace = obj.get("trace")
    if not isinstance(trace, list) or not trace:
        raise EpisodeError("empty or missing trace")
    expect = 1
    for entry in trace:
        if (not isinstance(entry, (list, tuple)) or len(entry) != 2):
            raise EpisodeError(f"bad trace entry: {entry!r}")
        step, pos = entry
        if step != expect:
            raise EpisodeError(f"trace steps not 1..N: got {step}, want {expect}")
        expect += 1
        if (not isinstance(pos, (list, tuple)) or len(pos) != 3
                or not all(_is_finite_number(c) for c in pos)):
            raise EpisodeError(f"bad trace pos at step {step}")
    if expect - 1 != steps:
        raise EpisodeError(f"trace length {expect - 1} != steps {steps}")
    return obj
