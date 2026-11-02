"""Playground falsifier: search the task preset for failing scenarios (Plan §10).

Runs the REAL simulator via ``run_single_episode`` (no mocks). Code is validated by the
AST allow-list before anything executes. Seeds come from the playground stream
(3,000,000 to 3,999,999), never from repair/calibration/certification streams (H9).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from closedloop.playground.lang import canonicalise_program, hash_program, validate_program
from closedloop.playground.presets import ROBOT_PRESETS, TASK_PRESETS
from closedloop.playground.repair import run_single_episode
from closedloop.sim.env import T1Env

SLIP_FACTOR = 1.2
GRAVITY = 9.81
FALSIFIER_SEED_MIN = 3_000_000
FALSIFIER_SEED_MAX = 3_999_999
MAX_BUDGET = 40


def hardware_lift_limit_kg(force_limit_n: float | None) -> float | None:
    """Heaviest liftable mass for a clamp force: F / (SLIP_FACTOR * g)."""
    if force_limit_n is None:
        return None
    return float(force_limit_n) / (SLIP_FACTOR * GRAVITY)


def _sample(task_preset: str, budget: int, seed_base: int) -> list[dict[str, Any]]:
    b = TASK_PRESETS[task_preset]["bounds"]
    rng = np.random.default_rng(seed_base)
    out: list[dict[str, Any]] = []
    for i in range(budget):
        out.append({
            "mass": float(rng.uniform(*b["mass"])),
            "friction": float(rng.uniform(*b["friction"])),
            "x": float(rng.uniform(*b["x"])),
            "y": float(rng.uniform(*b["y"])),
            "yaw": float(rng.uniform(*b["yaw"])),
            "seed": seed_base + i,
        })
    return out


def falsify_program(
    code: str,
    robot_preset: str = "certified_default",
    task_preset: str = "mixed_bin",
    budget: int = 20,
    seed_base: int = 3_100_000,
) -> dict[str, Any]:
    """Search for failing scenarios; return minimal and most severe counterexamples."""
    if robot_preset not in ROBOT_PRESETS:
        raise ValueError(f"Unknown robot preset '{robot_preset}'")
    if task_preset not in TASK_PRESETS:
        raise ValueError(f"Unknown task preset '{task_preset}'")
    if not (FALSIFIER_SEED_MIN <= seed_base <= FALSIFIER_SEED_MAX - MAX_BUDGET):
        raise ValueError("seed_base must be inside the playground stream 3000000-3999999")
    budget = max(1, min(MAX_BUDGET, int(budget)))

    robot = ROBOT_PRESETS[robot_preset]
    limit = hardware_lift_limit_kg(robot.get("force_limit_n"))
    base: dict[str, Any] = {
        "status": "OK", "error": "", "error_line": None, "evaluated": 0, "failures": 0,
        "minimal": None, "severe": None, "all_failures": [], "seeds": [],
        "hardware_limit_kg": limit, "robot_preset": robot_preset, "task_preset": task_preset,
    }

    ok, canon_or_err, line = validate_program(code)
    if not ok:
        base.update(status="VALIDATION_ERROR", error=canon_or_err, error_line=line)
        return base
    base["program_sha256"] = hash_program(code)

    ns: dict[str, Any] = {}
    exec(canonicalise_program(code), {}, ns)  # noqa: S102 - AST-validated allow-listed source
    policy = ns["policy"]

    scenarios = _sample(task_preset, budget, seed_base)
    env = T1Env()
    failures: list[dict[str, Any]] = []
    try:
        for sc in scenarios:
            out = run_single_episode(env, policy, sc, robot)
            base["evaluated"] += 1
            base["seeds"].append(sc["seed"])
            if not out.truth_success:
                failures.append({**sc, "margin": float(out.margin), "error": out.error,
                                 "clamped": out.hardware_clamps > 0})
    finally:
        env.close()

    base["failures"] = len(failures)
    base["all_failures"] = failures
    if failures:
        base["minimal"] = min(failures, key=lambda c: (c["mass"], -c["margin"]))
        base["severe"] = min(failures, key=lambda c: c["margin"])
        if limit is not None:
            base["beyond_hardware"] = bool(base["severe"]["mass"] > limit)
    return base
