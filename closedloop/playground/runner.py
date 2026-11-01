"""Simulation Runner Engine & Streaming Controller (Plan §9).

Features:
- Deterministic bounded scenario sampler.
- Immediate AST validation gating (zero simulator spend on rejected code).
- Sub-budget execution (3, 5, 20 episodes).
- Policy execution under PlaygroundPolicyFacade (hardware clamping & step budget).
- Strict failure accounting: exceptions, crashes, and budget overruns recorded as failures (H13).
- Optional camera frame rendering (192x144 base64).
- Dynamic 4-tuple badge resolution.
- Asynchronous generator yielding SSE events (start -> episode*N -> done).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np

from closedloop.judge.judge import render_judge_frame
from closedloop.playground.badge import evaluate_badge
from closedloop.playground.lang import (
    canonicalise_program,
    hash_program,
    validate_program,
)
from closedloop.playground.presets import (
    PlaygroundPolicyFacade,
    ROBOT_PRESETS,
    StepBudgetExceeded,
    TASK_PRESETS,
)
from closedloop.sim.env import T1Env

ROOT = Path(__file__).resolve().parent.parent.parent


def compute_sim_code_sha256() -> str:
    """Compute deterministic SHA-256 of sim source files (LF normalized)."""
    sim_files = sorted((ROOT / "closedloop" / "sim").glob("*.py"))
    h = hashlib.sha256()
    for f in sim_files:
        content = f.read_bytes().replace(b"\r\n", b"\n")
        h.update(f.name.encode("utf-8"))
        h.update(content)
    return h.hexdigest()


SIM_CODE_SHA256 = compute_sim_code_sha256()


def generate_playground_scenarios(
    task_preset: str = "mixed_bin",
    n: int = 5,
    seed_base: int = 1000,
) -> list[dict[str, Any]]:
    """Draw n deterministic scenarios uniformly from task preset bounds."""
    if task_preset not in TASK_PRESETS:
        raise ValueError(
            f"Unknown task preset: '{task_preset}' (valid: {list(TASK_PRESETS.keys())})"
        )

    bounds = TASK_PRESETS[task_preset]["bounds"]
    rng = np.random.default_rng(seed_base)
    scenarios: list[dict[str, Any]] = []

    for i in range(n):
        mass = float(rng.uniform(bounds["mass"][0], bounds["mass"][1]))
        friction = float(rng.uniform(bounds["friction"][0], bounds["friction"][1]))
        x = float(rng.uniform(bounds["x"][0], bounds["x"][1]))
        y = float(rng.uniform(bounds["y"][0], bounds["y"][1]))
        yaw = float(rng.uniform(bounds["yaw"][0], bounds["yaw"][1]))
        scenarios.append(
            {
                "scenario_id": f"pg_{task_preset}_{seed_base}_{i}",
                "mass": mass,
                "friction": friction,
                "x": x,
                "y": y,
                "yaw": yaw,
                "seed": seed_base + i,
            }
        )

    return scenarios


@dataclass
class PlaygroundJobResult:
    """Complete summary of a playground execution run."""

    ok: bool
    status: str  # "OK" | "VALIDATION_ERROR" | "EXECUTION_ERROR"
    error: str = ""
    error_line: int | None = None
    program_sha256: str = ""
    sim_code_sha256: str = ""
    badge: str = "UNCERTIFIED"
    badge_info: dict[str, Any] = field(default_factory=dict)
    k: int = 0
    n: int = 0
    episodes_tested: int = 0
    success_rate: float = 0.0
    total_clamp_events: int = 0
    duration_ms: float = 0.0
    episodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_certified_reproduction_episodes(limit: int = 20) -> list[dict[str, Any]]:
    """Load logged certified episodes for reproduction checks."""
    ep_file = ROOT / "runs" / "cert-full-01" / "episodes.jsonl"
    if not ep_file.exists():
        raise FileNotFoundError(f"Missing certified run file: {ep_file}")

    episodes: list[dict[str, Any]] = []
    with open(ep_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                sc = dict(data["scenario"])
                sc["seed"] = data["seed"]
                sc["logged_truth"] = data["truth_success"]
                sc["logged_margin"] = data["margin"]
                episodes.append(sc)
            if len(episodes) == limit:
                break
    return episodes


def run_playground_job(
    code: str,
    robot_preset: str = "certified_default",
    task_preset: str = "mixed_bin",
    budget: int = 5,
    seed_base: int = 1000,
    render_frames: bool = False,
    replay_certified_episodes: bool = False,
    sim_code_sha256: str | None = None,
) -> PlaygroundJobResult:
    """Run sandboxed simulation job with sub-budget and preset enforcement."""
    t0 = time.perf_counter()

    # 1. Immediate AST Validation Gating
    valid, err_or_canonical, line = validate_program(code)
    prog_hash = hash_program(code) if code else ""
    sim_hash = sim_code_sha256 or SIM_CODE_SHA256

    if not valid:
        return PlaygroundJobResult(
            ok=False,
            status="VALIDATION_ERROR",
            error=str(err_or_canonical),
            error_line=line,
            program_sha256=prog_hash,
            sim_code_sha256=sim_hash,
            badge="UNCERTIFIED",
            badge_info={"status": "UNCERTIFIED", "badge": "UNCERTIFIED"},
            episodes_tested=0,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    canonical_code = str(err_or_canonical)

    # 2. Dynamic 4-tuple badge evaluation
    badge_info = evaluate_badge(prog_hash, robot_preset, task_preset, sim_hash)
    badge_str = badge_info.get("badge", "UNCERTIFIED")

    # 3. Load or generate scenarios
    if replay_certified_episodes:
        scenarios = load_certified_reproduction_episodes(limit=budget)
    else:
        scenarios = generate_playground_scenarios(
            task_preset=task_preset, n=budget, seed_base=seed_base
        )

    # 4. Compile policy in restricted namespace
    policy_ns: dict[str, Any] = {}
    try:
        exec(canonical_code, policy_ns)
        policy_func = policy_ns.get("policy")
        if not callable(policy_func):
            return PlaygroundJobResult(
                ok=False,
                status="EXECUTION_ERROR",
                error="Program did not define a callable policy(env, rng) function",
                program_sha256=prog_hash,
                sim_code_sha256=sim_hash,
                badge=badge_str,
                badge_info=badge_info,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
    except Exception as e:
        return PlaygroundJobResult(
            ok=False,
            status="EXECUTION_ERROR",
            error=f"Compile error: {type(e).__name__}: {str(e)}",
            program_sha256=prog_hash,
            sim_code_sha256=sim_hash,
            badge=badge_str,
            badge_info=badge_info,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    # 5. Run simulation across scenarios
    episodes: list[dict[str, Any]] = []
    total_clamp_events = 0
    k = 0

    env = T1Env()
    try:
        for idx, sc in enumerate(scenarios):
            ep_seed = sc.get("seed", seed_base + idx)
            env.reset(sc)
            rng = np.random.default_rng(ep_seed)
            facade = PlaygroundPolicyFacade(env, robot_preset=robot_preset)

            ep_error = ""
            truth_success = False
            margin = -1.0
            steps = 0

            try:
                policy_func(facade, rng)
                sim_res = env.finish()
                truth_success = bool(sim_res.truth_success)
                margin = float(sim_res.margin)
                steps = int(sim_res.steps)
            except StepBudgetExceeded as e:
                ep_error = f"StepBudgetExceeded: {str(e)}"
                truth_success = False
                margin = -1.0
                steps = int(getattr(env, "steps", 0))
            except Exception as e:
                ep_error = f"{type(e).__name__}: {str(e)}"
                truth_success = False
                margin = -1.0
                steps = int(getattr(env, "steps", 0))

            total_clamp_events += len(facade.clamp_events)

            frame_b64 = None
            if render_frames:
                try:
                    _, frame_b64 = render_judge_frame(
                        env, {"width": 192, "height": 144}
                    )
                except Exception:
                    frame_b64 = None

            ep_entry = {
                "index": idx + 1,
                "seed": ep_seed,
                "mass": round(sc["mass"], 4),
                "friction": round(sc["friction"], 4),
                "truth_success": truth_success,
                "margin": round(margin, 6),
                "steps": steps,
                "error": ep_error,
                "clamp_events": [asdict(c) for c in facade.clamp_events],
            }
            if frame_b64:
                ep_entry["frame_b64"] = frame_b64

            episodes.append(ep_entry)
            if truth_success:
                k += 1
    finally:
        env.close()

    total_time_ms = round((time.perf_counter() - t0) * 1000, 2)
    n = len(episodes)
    rate = round(k / n, 4) if n > 0 else 0.0

    return PlaygroundJobResult(
        ok=True,
        status="OK",
        program_sha256=prog_hash,
        sim_code_sha256=sim_hash,
        badge=badge_str,
        badge_info=badge_info,
        k=k,
        n=n,
        episodes_tested=n,
        success_rate=rate,
        total_clamp_events=total_clamp_events,
        duration_ms=total_time_ms,
        episodes=episodes,
    )


async def stream_playground_job(
    code: str,
    robot_preset: str = "certified_default",
    task_preset: str = "mixed_bin",
    budget: int = 5,
    seed_base: int = 1000,
    render_frames: bool = False,
    replay_certified_episodes: bool = False,
    sim_code_sha256: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield sequential SSE events for live playground progress."""
    t0 = time.perf_counter()

    # 1. Validation gating
    valid, err_or_canonical, line = validate_program(code)
    prog_hash = hash_program(code) if code else ""
    sim_hash = sim_code_sha256 or SIM_CODE_SHA256

    if not valid:
        yield {
            "event": "error",
            "data": {
                "status": "VALIDATION_ERROR",
                "message": str(err_or_canonical),
                "line": line,
            },
        }
        return

    canonical_code = str(err_or_canonical)
    badge_info = evaluate_badge(prog_hash, robot_preset, task_preset, sim_hash)
    badge_str = badge_info.get("badge", "UNCERTIFIED")

    # 2. Scenarios
    if replay_certified_episodes:
        scenarios = load_certified_reproduction_episodes(limit=budget)
    else:
        scenarios = generate_playground_scenarios(
            task_preset=task_preset, n=budget, seed_base=seed_base
        )

    # 3. Emit start event
    yield {
        "event": "start",
        "data": {
            "total": len(scenarios),
            "badge": badge_str,
            "badge_info": badge_info,
            "program_sha256": prog_hash,
            "robot_preset": robot_preset,
            "task_preset": task_preset,
        },
    }
    await asyncio.sleep(0)

    # 4. Compile policy
    policy_ns: dict[str, Any] = {}
    try:
        exec(canonical_code, policy_ns)
        policy_func = policy_ns.get("policy")
    except Exception as e:
        yield {
            "event": "error",
            "data": {
                "status": "EXECUTION_ERROR",
                "message": f"Compile error: {type(e).__name__}: {str(e)}",
            },
        }
        return

    # 5. Execute episodes and yield progress
    episodes: list[dict[str, Any]] = []
    total_clamp_events = 0
    k = 0

    env = T1Env()
    try:
        for idx, sc in enumerate(scenarios):
            ep_seed = sc.get("seed", seed_base + idx)
            env.reset(sc)
            rng = np.random.default_rng(ep_seed)
            facade = PlaygroundPolicyFacade(env, robot_preset=robot_preset)

            ep_error = ""
            truth_success = False
            margin = -1.0
            steps = 0

            try:
                policy_func(facade, rng)
                sim_res = env.finish()
                truth_success = bool(sim_res.truth_success)
                margin = float(sim_res.margin)
                steps = int(sim_res.steps)
            except StepBudgetExceeded as e:
                ep_error = f"StepBudgetExceeded: {str(e)}"
                truth_success = False
                margin = -1.0
                steps = int(getattr(env, "steps", 0))
            except Exception as e:
                ep_error = f"{type(e).__name__}: {str(e)}"
                truth_success = False
                margin = -1.0
                steps = int(getattr(env, "steps", 0))

            total_clamp_events += len(facade.clamp_events)

            frame_b64 = None
            if render_frames:
                try:
                    _, frame_b64 = render_judge_frame(
                        env, {"width": 192, "height": 144}
                    )
                except Exception:
                    frame_b64 = None

            ep_entry = {
                "index": idx + 1,
                "total": len(scenarios),
                "seed": ep_seed,
                "mass": round(sc["mass"], 4),
                "friction": round(sc["friction"], 4),
                "truth_success": truth_success,
                "margin": round(margin, 6),
                "steps": steps,
                "error": ep_error,
                "clamp_events": [asdict(c) for c in facade.clamp_events],
            }
            if frame_b64:
                ep_entry["frame_b64"] = frame_b64

            episodes.append(ep_entry)
            if truth_success:
                k += 1

            yield {
                "event": "episode",
                "data": ep_entry,
            }
            await asyncio.sleep(0)
    finally:
        env.close()

    total_time_ms = round((time.perf_counter() - t0) * 1000, 2)
    n = len(episodes)
    rate = round(k / n, 4) if n > 0 else 0.0

    yield {
        "event": "done",
        "data": {
            "status": "OK",
            "k": k,
            "n": n,
            "success_rate": rate,
            "badge": badge_str,
            "badge_info": badge_info,
            "total_clamp_events": total_clamp_events,
            "duration_ms": total_time_ms,
        },
    }

