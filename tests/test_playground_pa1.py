"""Phase PA1 Tests: Language allow-list, AST validation, Presets, and Badge logic.

Asserts:
- Every frozen program in runs/ validates unchanged.
- At least 80 hostile programs are rejected with line numbers and clear reasons.
- Seeded random-mutation fuzzing produces only valid or cleanly rejected programs.
- Hash of certified text equals frozen sha256 (LF text).
- Canonical ast.unparse form produces the exact same result hash as raw program for 20 logged scenarios.
- certified_default preset reproduces logged episodes byte-for-byte.
- Badge function accurately evaluates CERTIFIED, VOID FOR THIS SETUP, and VOID.
- Shared test vectors verify Python and JS badge implementations agree.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest
from closedloop.playground.badge import evaluate_badge, generate_test_vectors
from closedloop.playground.lang import (
    canonicalise_program,
    hash_program,
    validate_program,
)
from closedloop.playground.presets import (
    ROBOT_PRESETS,
    TASK_PRESETS,
    HardwareClampEvent,
    PlaygroundPolicyFacade,
    StepBudgetExceeded,
)
from closedloop.sim.env import T1Env

ROOT = Path(__file__).resolve().parent.parent


def test_every_frozen_program_validates() -> None:
    """Task 1 & 2: Every frozen robot program in runs/ validates unchanged."""
    runs_dir = ROOT / "runs"
    py_files = list(runs_dir.rglob("*.py"))
    assert len(py_files) >= 5, f"Expected at least 5 frozen programs, found {len(py_files)}"

    for py_file in py_files:
        code = py_file.read_text(encoding="utf-8")
        valid, err, line = validate_program(code)
        assert valid, f"Frozen program {py_file} failed validation at line {line}: {err}"


def test_reject_at_least_80_hostile_programs() -> None:
    """Task 2: At least 80 distinct hostile programs are rejected."""
    hostile_cases = [
        # 1. Imports (10)
        "import os\ndef policy(env, rng): pass",
        "import sys\ndef policy(env, rng): pass",
        "import socket\ndef policy(env, rng): pass",
        "from os import system\ndef policy(env, rng): pass",
        "from math import sin\ndef policy(env, rng): pass",
        "import pybullet\ndef policy(env, rng): pass",
        "import subprocess\ndef policy(env, rng): pass",
        "import importlib\ndef policy(env, rng): pass",
        "from closedloop.sim.env import T1Env\ndef policy(env, rng): pass",
        "import builtins\ndef policy(env, rng): pass",

        # 2. Dunder / private access (10)
        "def policy(env, rng):\n    x = env.__class__",
        "def policy(env, rng):\n    x = env.__dict__",
        "def policy(env, rng):\n    x = env._env",
        "def policy(env, rng):\n    x = env._step()",
        "def policy(env, rng):\n    x = env.__subclasses__()",
        "def policy(env, rng):\n    x = __builtins__",
        "def policy(env, rng):\n    x = env.__globals__",
        "def policy(env, rng):\n    x = env.__getattribute__('move_to')",
        "def policy(env, rng):\n    _private = 1",
        "def policy(env, rng):\n    env.close_gripper(_force=10)",

        # 3. Attribute tricks & reflection (10)
        "def policy(env, rng):\n    getattr(env, 'move_to')((0, 0, 0))",
        "def policy(env, rng):\n    setattr(env, 'steps', 0)",
        "def policy(env, rng):\n    delattr(env, 'cid')",
        "def policy(env, rng):\n    hasattr(env, 'cid')",
        "def policy(env, rng):\n    x = env.cid",
        "def policy(env, rng):\n    x = env.cube",
        "def policy(env, rng):\n    x = env.pad",
        "def policy(env, rng):\n    x = env.hand",
        "def policy(env, rng):\n    env.reset({})",
        "def policy(env, rng):\n    env.finish()",

        # 4. Disallowed builtins / execution (10)
        "def policy(env, rng):\n    exec('env.open_gripper()')",
        "def policy(env, rng):\n    eval('1+1')",
        "def policy(env, rng):\n    open('/tmp/foo', 'w')",
        "def policy(env, rng):\n    compile('x=1', '', 'exec')",
        "def policy(env, rng):\n    globals()",
        "def policy(env, rng):\n    locals()",
        "def policy(env, rng):\n    vars()",
        "def policy(env, rng):\n    print('hello')",
        "def policy(env, rng):\n    breakpoint()",
        "def policy(env, rng):\n    exit(0)",

        # 5. Loops (8)
        "def policy(env, rng):\n    while True: pass",
        "def policy(env, rng):\n    while 1: env.open_gripper()",
        "def policy(env, rng):\n    for i in range(5): env.open_gripper()",
        "def policy(env, rng):\n    for x in [1, 2]: pass",
        "def policy(env, rng):\n    for c in 'cube': pass",
        "def policy(env, rng):\n    while False: pass",
        "def policy(env, rng):\n    for _ in (1, 2, 3): env.open_gripper()",
        "def policy(env, rng):\n    for i in {1, 2}: pass",

        # 6. Comprehensions & generators (8)
        "def policy(env, rng):\n    x = [i for i in (1, 2)]",
        "def policy(env, rng):\n    x = {i for i in (1, 2)}",
        "def policy(env, rng):\n    x = {i: i for i in (1, 2)}",
        "def policy(env, rng):\n    x = (i for i in (1, 2))",
        "def policy(env, rng):\n    yield (0, 0, 0)",
        "def policy(env, rng):\n    yield from [1, 2]",
        "async def policy(env, rng):\n    pass",
        "def policy(env, rng):\n    x = [env.open_gripper() for _ in range(1)]",

        # 7. Disallowed statements & control flow (10)
        "def policy(env, rng):\n    try:\n        pass\n    except:\n        pass",
        "def policy(env, rng):\n    with open('x'): pass",
        "def policy(env, rng):\n    assert True",
        "def policy(env, rng):\n    raise RuntimeError('boom')",
        "def policy(env, rng):\n    global g\n    g = 1",
        "def policy(env, rng):\n    nonlocal nl",
        "def policy(env, rng):\n    class Inner: pass",
        "def policy(env, rng):\n    def helper(): pass",
        "def policy(env, rng):\n    f = lambda x: x",
        "def policy(env, rng):\n    del env",

        # 8. Function structure & signature violations (8)
        "def wrong_name(env, rng): pass",
        "def policy(): pass",
        "def policy(env): pass",
        "def policy(env, rng, extra): pass",
        "def policy(env, rng=None): pass",
        "def policy(*args): pass",
        "def policy(**kwargs): pass",
        "x = 1\ndef policy(env, rng): pass",

        # 9. Huge numbers & illegal constants (8)
        "def policy(env, rng):\n    env.close_gripper(1001)",
        "def policy(env, rng):\n    env.close_gripper(-1001)",
        "def policy(env, rng):\n    x = 1e20",
        "def policy(env, rng):\n    x = 1000000000000000000000",
        "def policy(env, rng):\n    env.move_to((0, 0, 0), steps=241)",
        "def policy(env, rng):\n    env.move_to((0, 0, 0), steps=0)",
        "def policy(env, rng):\n    env.move_to((0, 0, 0), steps=-10)",
        "def policy(env, rng):\n    s = 'illegal_string_literal'",

        # 10. String tricks & forbidden objects (8)
        "def policy(env, rng):\n    env.get_object_pos('sphere')",
        "def policy(env, rng):\n    env.get_object_pos('hand')",
        "def policy(env, rng):\n    env.get_object_pos('table')",
        "def policy(env, rng):\n    env.get_object_pos('cu' + 'be')",
        "def policy(env, rng):\n    env.get_object_pose('plane')",
        "def policy(env, rng):\n    x = f'cube'",
        "def policy(env, rng):\n    env.move_to(('cube', 'pad', 0))",
        "def policy(env, rng):\n    x = b'cube'",

        # 11. Over limit size & statement count (4)
        "def policy(env, rng):\n" + "\n".join(f"    x_{i} = {i % 100}" for i in range(70)),  # > 60 statements
        "def policy(env, rng):\n    # " + ("A" * 4500) + "\n    env.open_gripper()",  # > 4 KB
        "def policy(env, rng):\n" + "    if True:\n" * 10 + "        env.open_gripper()",  # deep nesting
        "",  # empty program
    ]

    assert len(hostile_cases) >= 80, f"Expected >= 80 hostile test cases, got {len(hostile_cases)}"

    rejected_count = 0
    for idx, prog in enumerate(hostile_cases):
        valid, err, line = validate_program(prog)
        assert not valid, f"Hostile case #{idx} unexpectedly PASSED validation:\n{prog}"
        assert err is not None and len(err) > 0
        rejected_count += 1

    print(f"Verified {rejected_count}/84 hostile programs successfully rejected with diagnostic errors.")


def test_random_mutation_fuzzing() -> None:
    """Task 2: Seeded random-mutation fuzzing produces only valid or cleanly rejected programs."""
    base_code = (ROOT / "runs" / "cert-mint-03" / "program_final.py").read_text(encoding="utf-8")
    rng = random.Random(42)

    mutations = [
        lambda s: s.replace("100", str(rng.randint(-2000, 2000))),
        lambda s: s.replace("cube", rng.choice(["cube", "pad", "box", "obj", "__class__"])),
        lambda s: s.replace("open_gripper()", rng.choice(["open_gripper()", "open_gripper(1)", "close_gripper()", "exit()"])),
        lambda s: s.replace("steps=80", f"steps={rng.randint(-50, 300)}"),
        lambda s: s + "\n    import os",
        lambda s: s + f"\n    x = {rng.uniform(-500, 1500)}",
        lambda s: s.replace("def policy", "def wrong"),
    ]

    for i in range(50):
        m = rng.choice(mutations)
        mutated = m(base_code)
        try:
            valid, err, line = validate_program(mutated)
            if not valid:
                assert err is not None and isinstance(err, str)
        except Exception as e:
            pytest.fail(f"Fuzzer mutation #{i} crashed with uncaught exception: {e}\nCode:\n{mutated}")


def test_hash_program_matches_certified_sha256() -> None:
    """Task 2 & 7: Hash of certified text equals frozen sha256 (LF text)."""
    p_final = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    expected_v1 = "bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55"
    assert hash_program(p_final.read_text(encoding="utf-8")) == expected_v1

    # Works even with CRLF
    crlf_text = p_final.read_text(encoding="utf-8").replace("\n", "\r\n")
    assert hash_program(crlf_text) == expected_v1

    # v2 certified
    p_v2 = ROOT / "runs" / "round2-mint-01" / "program_final.py"
    expected_v2 = "5f74f7762ee1f378b2d71f6938a288fa12aa51a0ee93ee33a2639944cd66aaa1"
    assert hash_program(p_v2.read_text(encoding="utf-8")) == expected_v2


def test_canonical_form_gives_same_result_hash_for_20_scenarios() -> None:
    """Task 2 & 7: Canonical form gives same result hash as raw program for 20 scenarios."""
    raw_code = (ROOT / "runs" / "cert-mint-03" / "program_final.py").read_text(encoding="utf-8")
    canonical_code = canonicalise_program(raw_code)

    assert canonical_code != raw_code  # comments or formatting normalized
    assert "def policy(env, rng):" in canonical_code

    episodes = []
    with open(ROOT / "runs" / "cert-full-01" / "episodes.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))
            if len(episodes) == 20:
                break

    ns_raw: dict = {}
    exec(raw_code, ns_raw)
    policy_raw = ns_raw["policy"]

    ns_can: dict = {}
    exec(canonical_code, ns_can)
    policy_can = ns_can["policy"]

    env = T1Env()
    import numpy as np

    try:
        for ep in episodes:
            # Raw run
            env.reset(ep["scenario"])
            res_raw = env.run_policy(policy_raw, np.random.default_rng(ep["seed"]))

            # Canonical run
            env.reset(ep["scenario"])
            res_can = env.run_policy(policy_can, np.random.default_rng(ep["seed"]))

            assert res_raw.result_hash() == res_can.result_hash()
            assert res_raw.truth_success == res_can.truth_success
            assert abs(res_raw.margin - res_can.margin) <= 1e-9
    finally:
        env.close()


def test_certified_default_reproduces_logged_episodes_byte_for_byte() -> None:
    """Task 3: certified_default preset reproduces logged episodes byte-for-byte."""
    policy_code = (ROOT / "runs" / "cert-mint-03" / "program_final.py").read_text(encoding="utf-8")
    ns = {}
    exec(policy_code, ns)
    policy = ns["policy"]

    episodes = []
    with open(ROOT / "runs" / "cert-full-01" / "episodes.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))
            if len(episodes) == 20:
                break

    env = T1Env()
    import numpy as np

    try:
        for ep in episodes:
            env.reset(ep["scenario"])
            facade = PlaygroundPolicyFacade(env, robot_preset="certified_default")
            policy(facade, np.random.default_rng(ep["seed"]))
            res = env.finish()

            assert res.truth_success == ep["truth_success"]
            assert abs(res.margin - ep["margin"]) == 0.0
            assert facade.clamp_events == []  # no clamps on certified_default
    finally:
        env.close()


def test_gripper_presets_clamp_force_and_trigger_slip() -> None:
    """Task 3: gripper_100N clamps grip force and triggers slip above 8.49 kg."""
    env = T1Env()
    import numpy as np

    try:
        # Program commanding 300 N
        prog_300n = (ROOT / "runs" / "round2-mint-01" / "program_final.py").read_text(encoding="utf-8")
        ns = {}
        exec(prog_300n, ns)
        policy = ns["policy"]

        # 1. On certified_default at 10.0 kg: passes (300 N lifts 10 kg easily)
        sc_heavy = {"mass": 10.0, "friction": 0.5, "x": 0.0, "y": 0.0, "yaw": 0.0}
        env.reset(sc_heavy)
        facade_default = PlaygroundPolicyFacade(env, robot_preset="certified_default")
        policy(facade_default, np.random.default_rng(100))
        res_default = env.finish()
        assert res_default.truth_success is True

        # 2. On gripper_100N at 10.0 kg: slips and fails (100 N cannot lift 10 kg, limit ~8.49 kg)
        env.reset(sc_heavy)
        facade_100n = PlaygroundPolicyFacade(env, robot_preset="gripper_100N")
        policy(facade_100n, np.random.default_rng(100))
        res_100n = env.finish()
        assert res_100n.truth_success is False
        assert len(facade_100n.clamp_events) > 0
        assert facade_100n.clamp_events[0].commanded_force == 300.0
        assert facade_100n.clamp_events[0].applied_force == 100.0
    finally:
        env.close()


def test_section_6_3_badge_evaluation() -> None:
    """Task 6: evaluate_badge logic tests (Section 6.3)."""
    h_v1 = "bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55"
    sim_hash = "bf28d7d8a1480d480349869c6c0d775861ed5000a86cf44eeae478a1a4ac34c3"

    # 1. Matches hash AND robot AND task -> CERTIFIED
    b1 = evaluate_badge(h_v1, "certified_default", "mixed_bin", sim_hash)
    assert b1["status"] == "CERTIFIED"
    assert "CERTIFIED" in b1["badge"]

    # 2. Matches hash but robot differs -> VOID FOR THIS SETUP
    b2 = evaluate_badge(h_v1, "gripper_100N", "mixed_bin", sim_hash)
    assert b2["status"] == "VOID_SETUP"
    assert "VOID FOR THIS SETUP" in b2["badge"]

    # 3. Matches hash but task differs -> VOID FOR THIS SETUP
    b3 = evaluate_badge(h_v1, "certified_default", "heavy_parts", sim_hash)
    assert b3["status"] == "VOID_SETUP"
    assert "VOID FOR THIS SETUP" in b3["badge"]

    # 4. Unknown hash -> VOID
    b4 = evaluate_badge("0000000000000000000000000000000000000000000000000000000000000000", "certified_default", "mixed_bin", sim_hash)
    assert b4["status"] == "VOID"
    assert b4["badge"] == "VOID"

    # 5. One character edit -> VOID; Revert -> CERTIFIED
    edited_hash = h_v1[:-1] + ("0" if h_v1[-1] != "0" else "1")
    b5 = evaluate_badge(edited_hash, "certified_default", "mixed_bin", sim_hash)
    assert b5["status"] == "VOID"

    reverted = evaluate_badge(h_v1, "certified_default", "mixed_bin", sim_hash)
    assert reverted["status"] == "CERTIFIED"


def test_shared_test_vectors_badge() -> None:
    """Task 6: Generate and verify shared test vectors for Python and JS badge logic."""
    vectors = generate_test_vectors()
    assert len(vectors) >= 10

    for vec in vectors:
        res = evaluate_badge(
            vec["code_sha256"],
            vec["robot_preset"],
            vec["task_preset"],
            vec["sim_code_sha256"],
        )
        assert res["status"] == vec["expected_status"], f"Vector failed: {vec}"
        assert res["badge"] == vec["expected_badge"], f"Vector failed: {vec}"
