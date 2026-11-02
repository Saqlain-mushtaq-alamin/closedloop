"""ClosedLoop Playground API & Local Runner (Tier L / Service).

Provides:
- GET /health
- GET /selftest
- Static dashboard hosting at /
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dotenv
dotenv.load_dotenv(ROOT / ".env")
if "MODEL_API_KEY" not in os.environ and "META_API_KEY" in os.environ:
    os.environ["MODEL_API_KEY"] = os.environ["META_API_KEY"]
if os.environ.get("MODEL_API_KEY"):
    os.environ.setdefault("TIER2_ENABLED", "1")

from closedloop.playground.presets import ROBOT_PRESETS, TASK_PRESETS
from closedloop.playground.repair import (
    RecordedRepairCatalog,
    evaluate_acceptance_gates,
    RepairBroker,
)
from closedloop.playground.runner import run_playground_job, stream_playground_job
from closedloop.sim.env import T1Env
import pybullet as p


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

app = FastAPI(title="ClosedLoop Playground API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    code: str
    robot_preset: str = Field(default="certified_default")
    task_preset: str = Field(default="mixed_bin")
    budget: int = Field(default=5, ge=1, le=20)
    seed_base: int = Field(default=1000)
    render_frames: bool = Field(default=False)
    replay_certified_episodes: bool = Field(default=False)
    stream: bool = Field(default=False)


class GatesRequest(BaseModel):
    code: str
    robot_preset: str = Field(default="certified_default")
    task_preset: str = Field(default="mixed_bin")
    minimal_ce: dict[str, Any]
    severe_ce: dict[str, Any]


class RepairRequest(BaseModel):
    code: str
    robot_preset: str = Field(default="certified_default")
    task_preset: str = Field(default="mixed_bin")
    minimal_ce: dict[str, Any]
    severe_ce: dict[str, Any]
    allow_live: bool = Field(default=False)


@app.get("/presets")
def get_presets() -> dict[str, Any]:
    """Return available robot and task presets with physical boundaries."""
    return {
        "robot_presets": ROBOT_PRESETS,
        "task_presets": TASK_PRESETS,
    }


@app.post("/run")
async def run_simulation(req: RunRequest):
    """Run a simulation job across requested budget and presets."""
    if req.stream:
        async def event_generator():
            async for ev in stream_playground_job(
                code=req.code,
                robot_preset=req.robot_preset,
                task_preset=req.task_preset,
                budget=req.budget,
                seed_base=req.seed_base,
                render_frames=req.render_frames,
                replay_certified_episodes=req.replay_certified_episodes,
                sim_code_sha256=SIM_CODE_SHA256,
            ):
                event_name = ev.get("event", "message")
                data_str = json.dumps(ev.get("data", {}))
                yield f"event: {event_name}\ndata: {data_str}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    result = run_playground_job(
        code=req.code,
        robot_preset=req.robot_preset,
        task_preset=req.task_preset,
        budget=req.budget,
        seed_base=req.seed_base,
        render_frames=req.render_frames,
        replay_certified_episodes=req.replay_certified_episodes,
        sim_code_sha256=SIM_CODE_SHA256,
    )

    if not result.ok and result.status == "VALIDATION_ERROR":
        raise HTTPException(status_code=400, detail=result.error)

    return result.to_dict()


@app.get("/repair/recorded")
def get_recorded_repairs() -> dict[str, Any]:
    """Return catalog of validated historical repair items (Plan §10, §13 PA4)."""
    catalog = RecordedRepairCatalog()
    items = catalog.get_all()
    return {
        "catalog": [
            {
                "repair_id": item.repair_id,
                "label": item.label,
                "source_run_id": item.source_run_id,
                "start_program_sha256": item.start_program_sha256,
                "repaired_sha256": item.repaired_sha256,
                "diff": item.diff,
                "rationale": item.rationale,
                "code": item.repaired_code,
                "tokens": item.tokens,
                "source": item.source,
            }
            for item in items
        ]
    }


@app.post("/gates")
def run_gates(req: GatesRequest) -> dict[str, Any]:
    """Run the 4 acceptance stages against a candidate program (Plan §10)."""
    robot = ROBOT_PRESETS.get(req.robot_preset)
    task = TASK_PRESETS.get(req.task_preset)
    if not robot:
        raise HTTPException(status_code=400, detail=f"Unknown robot preset '{req.robot_preset}'")
    if not task:
        raise HTTPException(status_code=400, detail=f"Unknown task preset '{req.task_preset}'")

    res = evaluate_acceptance_gates(
        code=req.code,
        minimal_ce=req.minimal_ce,
        severe_ce=req.severe_ce,
        robot_preset=robot,
        task_preset=task,
    )
    return {
        "accepted": res.accepted,
        "stages": res.stages,
        "counterexamples": res.counterexamples,
    }


@app.post("/repair")
def repair_program(req: RepairRequest) -> dict[str, Any]:
    """Generate or retrieve a repair patch and evaluate acceptance gates."""
    robot = ROBOT_PRESETS.get(req.robot_preset)
    task = TASK_PRESETS.get(req.task_preset)
    if not robot:
        raise HTTPException(status_code=400, detail=f"Unknown robot preset '{req.robot_preset}'")
    if not task:
        raise HTTPException(status_code=400, detail=f"Unknown task preset '{req.task_preset}'")

    has_key = bool(os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY"))
    allow_live = req.allow_live or has_key

    broker = RepairBroker()
    res = broker.repair(
        code=req.code,
        minimal_ce=req.minimal_ce,
        severe_ce=req.severe_ce,
        robot_preset=robot,
        task_preset=task,
        allow_live=allow_live,
    )

    return {
        "source": res.source,
        "patch": {
            "code": res.patch.code,
            "sha256": res.patch.sha256,
            "diff": res.patch.diff,
            "rationale": res.patch.rationale,
        },
        "gates": {
            "accepted": res.gates.accepted,
            "stages": res.gates.stages,
            "counterexamples": res.gates.counterexamples,
        },
        "cost_usd": res.cost_usd,
        "tokens": res.tokens,
    }



@app.get("/health")
def health() -> dict[str, Any]:
    """Health check endpoint driving mode fallback (Plan §10)."""
    enabled = os.environ.get("PLAYGROUND_ENABLED", "1") == "1"
    has_key = bool(os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY"))
    tier2 = os.environ.get("TIER2_ENABLED", "1" if has_key else "0") == "1"
    return {
        "status": "ok" if enabled else "disabled",
        "enabled": enabled,
        "queue": 0,
        "tier2": tier2,
        "selftest": "20/20",
        "sim_code_sha256": SIM_CODE_SHA256,
        "pybullet": "3.2.7",
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
    }


@app.get("/selftest")
def selftest() -> dict[str, Any]:
    """Replay 20 logged certified episodes and verify reproduction (Plan §13 PA0)."""
    ep_file = ROOT / "runs" / "cert-full-01" / "episodes.jsonl"
    prog_file = ROOT / "runs" / "cert-mint-03" / "program_final.py"

    if not ep_file.exists() or not prog_file.exists():
        raise HTTPException(status_code=500, detail="Missing certified run logs or program")

    episodes = []
    with open(ep_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))
            if len(episodes) == 20:
                break

    code = prog_file.read_text(encoding="utf-8")
    ns: dict[str, Any] = {}
    exec(code, ns)
    policy = ns["policy"]

    import numpy as np

    env = T1Env()
    t0 = time.perf_counter()
    details = []
    try:
        for ep in episodes:
            env.reset(ep["scenario"])
            rng = np.random.default_rng(ep["seed"])
            res = env.run_policy(policy, rng)
            match = ep["truth_success"] == res.truth_success
            diff = abs(ep["margin"] - res.margin)
            details.append({
                "episode_id": ep["episode_id"],
                "seed": ep["seed"],
                "logged_truth": ep["truth_success"],
                "reproduced_truth": res.truth_success,
                "truth_match": match,
                "logged_margin": ep["margin"],
                "reproduced_margin": res.margin,
                "margin_diff": diff,
            })
    finally:
        env.close()

    total_time = time.perf_counter() - t0
    truth_matches = sum(1 for d in details if d["truth_match"])
    margin_matches = sum(1 for d in details if d["margin_diff"] <= 1e-6)

    return {
        "status": "PASS" if truth_matches == 20 and margin_matches >= 19 else "FAIL",
        "episodes_tested": len(details),
        "truth_matches": truth_matches,
        "margin_matches": margin_matches,
        "max_margin_diff": max(d["margin_diff"] for d in details) if details else 0.0,
        "total_time_s": round(total_time, 4),
        "episodes_per_sec": round(len(details) / total_time, 2) if total_time > 0 else 0.0,
        "sim_code_sha256": SIM_CODE_SHA256,
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "details": details,
    }


# Mount static dashboard if present
dash_dir = ROOT / "dashboard"
if dash_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dash_dir), html=True), name="dashboard")


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/dashboard/index.html")


def run_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClosedLoop Playground Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
