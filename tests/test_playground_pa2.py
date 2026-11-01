"""Unit tests for Phase PA2: Simulation Runner Engine & Streaming API (Plan §9).

Verifies:
1. Deterministic and bounded scenario generation.
2. Validation gating (hostile code rejected with 0 simulator calls).
3. Exact reproduction of 20 certified episodes under certified_default.
4. Hardware force clamping causing slip on heavy parts under gripper_100N.
5. Strict failure accounting on step budget exceeded (H13).
6. Policy exception caught and recorded as failure (H13).
7. 4-tuple badge resolution dynamically bound to job presets.
8. SSE stream event ordering (start -> episode*N -> done).
9. FastAPI /run and /presets endpoints.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from closedloop.playground.lang import hash_program, validate_program
from closedloop.playground.presets import ROBOT_PRESETS, TASK_PRESETS
from closedloop.playground.runner import (
    PlaygroundJobResult,
    generate_playground_scenarios,
    run_playground_job,
    stream_playground_job,
)
from playground.server import app

ROOT = Path(__file__).resolve().parent.parent

VALID_CERTIFIED_CODE = """def policy(env, rng):
    pad_pos = env.get_object_pos('pad')
    cube_pos = env.get_object_pos('cube')
    env.open_gripper()
    env.move_to((cube_pos[0], cube_pos[1], cube_pos[2] + 0.1), steps=60)
    env.move_to(cube_pos, steps=60)
    env.close_gripper(force=300)
    env.move_to((cube_pos[0], cube_pos[1], cube_pos[2] + 0.15), steps=60)
    env.move_to((pad_pos[0], pad_pos[1], pad_pos[2] + 0.15), steps=60)
    env.move_to((pad_pos[0], pad_pos[1], pad_pos[2] + 0.05), steps=60)
    env.open_gripper()
    env.move_to((pad_pos[0], pad_pos[1], pad_pos[2] + 0.15), steps=60)
"""


def test_scenario_generation_deterministic_and_bounded() -> None:
    """Scenarios must be strictly bounded by task preset and deterministic across runs."""
    for preset_name, preset_cfg in TASK_PRESETS.items():
        bounds = preset_cfg["bounds"]
        scenarios_1 = generate_playground_scenarios(preset_name, n=5, seed_base=1000)
        scenarios_2 = generate_playground_scenarios(preset_name, n=5, seed_base=1000)
        scenarios_diff_seed = generate_playground_scenarios(preset_name, n=5, seed_base=2000)

        assert len(scenarios_1) == 5
        # Determinism
        assert scenarios_1 == scenarios_2
        assert scenarios_1 != scenarios_diff_seed

        # Bounds check
        for sc in scenarios_1:
            assert bounds["mass"][0] <= sc["mass"] <= bounds["mass"][1]
            assert bounds["friction"][0] <= sc["friction"] <= bounds["friction"][1]
            assert bounds["x"][0] <= sc["x"] <= bounds["x"][1]
            assert bounds["y"][0] <= sc["y"] <= bounds["y"][1]
            assert bounds["yaw"][0] <= sc["yaw"] <= bounds["yaw"][1]


def test_runner_validation_error_aborts_before_sim() -> None:
    """Invalid code must be rejected immediately without invoking simulation."""
    hostile_code = "def policy(env, rng):\n    import os"
    res = run_playground_job(
        code=hostile_code,
        robot_preset="certified_default",
        task_preset="mixed_bin",
        budget=5,
    )
    assert not res.ok
    assert res.status == "VALIDATION_ERROR"
    assert "Forbidden language construct 'Import'" in res.error
    assert res.episodes_tested == 0
    assert len(res.episodes) == 0


def test_runner_certified_program_20_episodes_reproduction() -> None:
    """Runner reproduces 20 certified episodes from cert-full-01 with certified badge."""
    prog_path = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    assert prog_path.exists()
    code = prog_path.read_text(encoding="utf-8")

    res = run_playground_job(
        code=code,
        robot_preset="certified_default",
        task_preset="mixed_bin",
        budget=20,
        replay_certified_episodes=True,
    )

    assert res.ok
    assert res.status == "OK"
    assert res.episodes_tested == 20
    assert res.badge == "CERTIFIED"
    assert res.k == 20
    assert res.success_rate == 1.0


def test_runner_hardware_force_clamping_fails_heavy_bin() -> None:
    """100 N gripper must fail on heavy parts (>8.5 kg) and log hardware clamp events."""
    prog_path = ROOT / "runs" / "round2-mint-01" / "program_final.py"
    assert prog_path.exists()
    code = prog_path.read_text(encoding="utf-8")

    # heavy_parts ranges from 6.0 to 14.0 kg
    res = run_playground_job(
        code=code,
        robot_preset="gripper_100N",
        task_preset="heavy_parts",
        budget=5,
        seed_base=5000,
    )

    assert res.ok
    assert res.badge == "VOID FOR THIS SETUP"
    assert res.episodes_tested == 5
    # Should observe clamp events and lower success rate
    assert res.total_clamp_events > 0
    assert res.k < 5


def test_runner_step_limit_failure_accounting() -> None:
    """A policy exceeding the 3000 step budget must be recorded as failure (H13)."""
    # Each move_to(..., steps=240) takes 240 steps. 15 moves = 3600 steps > 3000
    long_policy = """def policy(env, rng):
    pos = env.get_object_pos('cube')
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
    env.move_to(pos, steps=240)
"""
    res = run_playground_job(
        code=long_policy,
        robot_preset="certified_default",
        task_preset="mixed_bin",
        budget=3,
        seed_base=7000,
    )

    assert res.ok
    assert res.episodes_tested == 3
    assert res.k == 0  # all failed
    for ep in res.episodes:
        assert not ep["truth_success"]
        assert "step budget" in ep["error"].lower()


def test_runner_policy_exception_recorded_as_failure() -> None:
    """Policy raising an exception must be recorded as an episode failure (H13)."""
    crash_policy = """def policy(env, rng):
    x = 1 / 0
    env.open_gripper()
"""
    res = run_playground_job(
        code=crash_policy,
        robot_preset="certified_default",
        task_preset="mixed_bin",
        budget=3,
        seed_base=8000,
    )

    assert res.ok
    assert res.episodes_tested == 3
    assert res.k == 0
    for ep in res.episodes:
        assert not ep["truth_success"]
        assert "division by zero" in ep["error"]


def test_badge_evaluated_per_job_configuration() -> None:
    """Badge evaluates accurately per 4-tuple binding (Plan §6.3)."""
    prog_path = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    code = prog_path.read_text(encoding="utf-8")

    # 1. Matching config -> CERTIFIED
    res1 = run_playground_job(code, "certified_default", "mixed_bin", budget=3)
    assert res1.badge == "CERTIFIED"

    # 2. Hardware changed -> VOID FOR THIS SETUP
    res2 = run_playground_job(code, "gripper_100N", "mixed_bin", budget=3)
    assert res2.badge == "VOID FOR THIS SETUP"

    # 3. Task distribution changed -> VOID FOR THIS SETUP
    res3 = run_playground_job(code, "certified_default", "heavy_parts", budget=3)
    assert res3.badge == "VOID FOR THIS SETUP"

    # 4. Uncertified code -> VOID
    res4 = run_playground_job(VALID_CERTIFIED_CODE, "certified_default", "mixed_bin", budget=3)
    assert res4.badge == "VOID"


@pytest.mark.asyncio
async def test_sse_stream_generator_events_sequence() -> None:
    """stream_playground_job must yield start, episode*N, and done events in order."""
    prog_path = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    code = prog_path.read_text(encoding="utf-8")

    events = []
    async for event in stream_playground_job(
        code=code,
        robot_preset="certified_default",
        task_preset="mixed_bin",
        budget=3,
        seed_base=9000,
    ):
        events.append(event)

    assert len(events) == 5  # 1 start + 3 episodes + 1 done
    assert events[0]["event"] == "start"
    assert events[0]["data"]["total"] == 3
    assert events[0]["data"]["badge"] == "CERTIFIED"

    for i in range(1, 4):
        assert events[i]["event"] == "episode"
        assert events[i]["data"]["index"] == i
        assert "truth_success" in events[i]["data"]
        assert "margin" in events[i]["data"]

    assert events[4]["event"] == "done"
    assert events[4]["data"]["k"] >= 0
    assert events[4]["data"]["n"] == 3
    assert events[4]["data"]["badge"] == "CERTIFIED"


def test_server_run_and_presets_api() -> None:
    """FastAPI server handles /presets and /run endpoints."""
    client = TestClient(app)

    # 1. Test /presets
    resp_presets = client.get("/presets")
    assert resp_presets.status_code == 200
    data_presets = resp_presets.json()
    assert "robot_presets" in data_presets
    assert "task_presets" in data_presets
    assert "certified_default" in data_presets["robot_presets"]
    assert "mixed_bin" in data_presets["task_presets"]

    # 2. Test /run valid
    prog_path = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    code = prog_path.read_text(encoding="utf-8")
    payload = {
        "code": code,
        "robot_preset": "certified_default",
        "task_preset": "mixed_bin",
        "budget": 3,
        "seed_base": 12000,
        "render_frames": False,
    }
    resp_run = client.post("/run", json=payload)
    assert resp_run.status_code == 200
    data_run = resp_run.json()
    assert data_run["status"] == "OK"
    assert data_run["badge"] == "CERTIFIED"
    assert data_run["episodes_tested"] == 3

    # 3. Test /run validation failure
    bad_payload = {
        "code": "def policy(env, rng):\n    import sys",
        "robot_preset": "certified_default",
        "task_preset": "mixed_bin",
        "budget": 3,
    }
    resp_bad = client.post("/run", json=bad_payload)
    assert resp_bad.status_code == 400
    assert "Forbidden language construct" in resp_bad.json()["detail"]
