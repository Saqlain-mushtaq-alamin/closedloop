"""Tests for the playground falsifier (real simulator, no fakes)."""

from __future__ import annotations

from closedloop.playground.falsify import falsify_program, hardware_lift_limit_kg
from closedloop.playground.presets import ROBOT_PRESETS, TASK_PRESETS

V1 = "\n".join([
    "def policy(env, rng):",
    "    cube_pos = env.get_object_pos(\"cube\")",
    "    pad_pos = env.get_object_pos(\"pad\")",
    "    env.open_gripper()",
    "    above_cube = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.20)",
    "    env.move_to(above_cube, steps=80)",
    "    grasp_pos = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.005)",
    "    env.move_to(grasp_pos, steps=80)",
    "    env.close_gripper(100)",
    "    env.move_to(grasp_pos, steps=20)",
    "    env.move_to(above_cube, steps=100)",
    "    above_pad = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.20)",
    "    env.move_to(above_pad, steps=100)",
    "    place_pos = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.02)",
    "    env.move_to(place_pos, steps=100)",
    "    env.open_gripper()",
    "    env.move_to(place_pos, steps=20)",
    "    env.move_to(above_pad, steps=80)",
    "",
])


def test_lift_limit_matches_plan() -> None:
    assert abs(hardware_lift_limit_kg(100.0) - 8.49) < 0.01
    assert hardware_lift_limit_kg(None) is None


def test_invalid_code_is_rejected_without_simulating() -> None:
    res = falsify_program("def policy(env, rng):\n    import os\n", "certified_default", "mixed_bin", budget=3)
    assert res["status"] == "VALIDATION_ERROR"
    assert res["evaluated"] == 0


def test_flawed_program_yields_counterexamples() -> None:
    res = falsify_program(V1, "certified_default", "heavy_parts", budget=6, seed_base=3100000)
    assert res["status"] == "OK"
    assert res["evaluated"] == 6
    assert res["failures"] >= 1
    mn, sv = res["minimal"], res["severe"]
    assert mn["mass"] <= sv["mass"] or mn["margin"] >= sv["margin"]
    assert sv["margin"] == min(c["margin"] for c in res["all_failures"])
    lo, hi = TASK_PRESETS["heavy_parts"]["bounds"]["mass"]
    assert lo <= mn["mass"] <= hi


def test_seeds_stay_in_playground_stream() -> None:
    res = falsify_program(V1, "certified_default", "mixed_bin", budget=3, seed_base=3100000)
    assert all(3_000_000 <= s < 4_000_000 for s in res["seeds"])


def test_hardware_limit_is_reported() -> None:
    res = falsify_program(V1, "gripper_100N", "heavy_parts", budget=4, seed_base=3100000)
    assert res["hardware_limit_kg"] is not None
    assert ROBOT_PRESETS["gripper_100N"]["force_limit_n"] == 100.0
