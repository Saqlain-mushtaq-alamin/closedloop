"""Run Demo Sessions (Phase 10c extension).

Pre-registered in configs/demo_sessions.yaml.
Selects first 8 failing scenarios for start program(s), executes recorded repair sessions,
writes runs/demo-sessions-01/, and builds dashboard assets for Repair Theatre (Feature F7).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def run_all_demo_sessions(
    config_path: str = "configs/demo_sessions.yaml",
    runs_dir: str = "runs",
    output_dir: str = "runs/demo-sessions-01",
) -> dict[str, Any]:
    from closedloop.data.sampler import sample
    from closedloop.demo.session import run_repair_session, execute_policy_instrumented
    from closedloop.llm.client import LLMClient
    from closedloop.llm.cost import CostMeter

    cfg_file = ROOT / config_path
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    run_id = str(cfg.get("run_id", "demo-sessions-01"))
    target_count = int(cfg.get("target_sessions", 8))
    arm = str(cfg.get("arm", "B3"))
    model = str(cfg.get("model", "muse-spark-1.3"))
    budget_cap = float(cfg.get("budget_cap_usd", 3.0))

    start_progs = cfg["start_programs"]
    # Primary start program is v1
    v1_info = next(p for p in start_progs if p["id"] == "v1")
    v1_code = (ROOT / v1_info["path"]).read_text(encoding="utf-8").replace("\r\n", "\n")
    v1_sha = hashlib.sha256(v1_code.encode("utf-8")).hexdigest()

    v2_info = next((p for p in start_progs if p["id"] == "v2"), None)
    v2_code = (
        (ROOT / v2_info["path"]).read_text(encoding="utf-8").replace("\r\n", "\n")
        if v2_info and (ROOT / v2_info["path"]).exists()
        else None
    )

    bounds = cfg["distribution"]["bounds"]
    bounds_dict = {k: (float(v[0]), float(v[1])) for k, v in bounds.items()}

    seed_start = int(cfg["selection"]["seed_start"])
    seed_max = int(cfg["selection"]["seed_max"])

    meter = CostMeter(cap_usd=budget_cap)
    client: LLMClient | None = None
    try:
        client = LLMClient(meter)
    except Exception as e:
        print(f"LLMClient init notice (offline / fallback mode available): {e}")

    out_path = ROOT / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    cache_file = out_path / "llm_cache.json"
    cache: dict[str, Any] = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 1. Scenario Selection: Draw scenarios from D starting at seed_start
    print(f"Selecting first {target_count} failing scenarios starting at seed {seed_start}...")
    attempted_scenarios: list[dict[str, Any]] = []
    selected_scenarios: list[dict[str, Any]] = []

    curr_seed = seed_start
    while len(selected_scenarios) < target_count and curr_seed <= seed_max:
        sc = sample("repair", 1, curr_seed, bounds=bounds_dict)[0]
        # Evaluate simulator ground truth
        sim_res, _ = execute_policy_instrumented(v1_code, sc, curr_seed, capture_frames=False)
        ts = sim_res["truth_success"]
        mg = sim_res["margin"]

        attempt_record = {
            "seed": curr_seed,
            "params": {k: float(sc[k]) for k in ["x", "y", "yaw", "mass", "friction"]},
            "truth_success": ts,
            "margin": mg,
            "selected": not ts,
        }
        attempted_scenarios.append(attempt_record)

        if not ts:
            selected_scenarios.append(dict(sc))
            print(f"  Selected scenario {len(selected_scenarios)}/{target_count}: seed={curr_seed}, mass={sc['mass']:.2f}kg, friction={sc['friction']:.2f}, margin={mg:.4f}")

        curr_seed += 1

    # Save selection log
    selection_log = {
        "run_id": run_id,
        "seed_start": seed_start,
        "total_attempted": len(attempted_scenarios),
        "total_selected": len(selected_scenarios),
        "selected": selected_scenarios,
        "attempts": attempted_scenarios,
    }
    (out_path / "selection_log.json").write_text(json.dumps(selection_log, indent=2), encoding="utf-8")

    # 2. Run Repair Sessions
    sessions_meta: list[dict[str, Any]] = []
    mini_check_seed_start = int(cfg["mini_check"]["seed_start"])
    mini_check_n = int(cfg["mini_check"]["n_scenarios"])
    mini_seeds = [mini_check_seed_start + i for i in range(mini_check_n)]

    regression_set = [
        {"id": "nominal", "x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 1.0, "friction": 0.8, "seed": 713000},
        {"id": "ce_mint03", "x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 1.0, "friction": 0.8, "seed": 780000},
    ]

    for idx, sc in enumerate(selected_scenarios):
        sess_id = f"session_{idx:02d}"
        sess_dir = out_path / sess_id
        sess_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n--- Running Repair Session {idx+1}/{target_count} ({sess_id}, seed {sc['seed']}) ---")
        sess_record = run_repair_session(
            scenario=sc,
            start_program_code=v1_code,
            start_program_meta={
                "program_id": v1_info["program_id"],
                "sha256": v1_sha,
                "label": "v1",
            },
            arm=arm,
            model=model,
            client=client,
            meter=meter,
            session_id=sess_id,
            save_dir=sess_dir,
            regression_set=regression_set,
            mini_check_seeds=mini_seeds,
            llm_cache=cache,
        )

        sessions_meta.append({
            "session_id": sess_id,
            "scenario": sc,
            "failing_margin": sess_record["failing_episode"]["sim_result"]["margin"],
            "repaired_sha256": sess_record["repaired_program"]["sha256"],
            "accepted": sess_record["acceptance_stages"]["accepted"],
            "replay_verified": sess_record["replay"]["verified"],
            "cost_usd": sess_record["model_response"]["cost_usd"],
        })

    # Save LLM cache
    cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    # 3. Create Manifest
    git_sha = git_head()
    cfg_raw = cfg_file.read_bytes()
    cfg_hash = hashlib.sha256(cfg_raw).hexdigest()

    manifest = {
        "run_id": run_id,
        "config_hash": cfg_hash,
        "git_sha": git_sha,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_sessions": target_count,
        "total_sessions_run": len(sessions_meta),
        "total_spend_usd": round(meter.spent_usd, 4),
        "sessions": sessions_meta,
    }
    (out_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 4. Copy Assets and Export Repair Theatre data for Dashboard
    dash_dir = ROOT / "dashboard"
    theatre_dir = dash_dir / "theatre"
    theatre_dir.mkdir(parents=True, exist_ok=True)

    theatre_sessions: list[dict[str, Any]] = []

    for idx in range(target_count):
        sess_id = f"session_{idx:02d}"
        s_file = out_path / sess_id / "session.json"
        s_data = json.loads(s_file.read_text(encoding="utf-8"))

        dash_sess_frames = theatre_dir / sess_id / "frames"
        dash_sess_frames.mkdir(parents=True, exist_ok=True)

        # Copy frames to dashboard/theatre/<sess_id>/frames/
        failing_paths = []
        for fn in s_data["failing_episode"]["frames"]:
            src = out_path / sess_id / "frames" / fn
            dst = dash_sess_frames / fn
            if src.exists():
                shutil.copy2(src, dst)
            rel_path = f"theatre/{sess_id}/frames/{fn}"
            failing_paths.append(rel_path)

        replay_paths = []
        for fn in s_data["replay"]["frames"]:
            src = out_path / sess_id / "frames" / fn
            dst = dash_sess_frames / fn
            if src.exists():
                shutil.copy2(src, dst)
            rel_path = f"theatre/{sess_id}/frames/{fn}"
            replay_paths.append(rel_path)

        theatre_sessions.append({
            "session_id": sess_id,
            "label": f"Scenario {idx+1}: mass={s_data['scenario']['mass']:.2f}kg, μ={s_data['scenario']['friction']:.2f}",
            "scenario": s_data["scenario"],
            "failing_frames": failing_paths,
            "failing_sim": s_data["failing_episode"]["sim_result"],
            "falsifier_trace": s_data["falsifier_trace"],
            "minimizer_steps": s_data["minimizer_steps"],
            "minimal_ce": s_data["minimal_counterexample"],
            "repair_prompt": s_data["repair_prompt"],
            "model_response": s_data["model_response"],
            "repaired_program": s_data["repaired_program"],
            "acceptance_stages": s_data["acceptance_stages"],
            "replay_frames": replay_paths,
            "replay": s_data["replay"],
            "held_out_mini_check": s_data["held_out_mini_check"],
        })

    theatre_data = {
        "run_id": run_id,
        "git_sha": git_sha,
        "badge": f"RECORDED session {run_id} at git {git_sha[:8]}",
        "total_spend_usd": round(meter.spent_usd, 4),
        "sessions": theatre_sessions,
    }

    (dash_dir / "repair_theatre_data.json").write_text(json.dumps(theatre_data, indent=2), encoding="utf-8")
    (dash_dir / "repair_theatre_data.js").write_text(
        f"window.REPAIR_THEATRE_DATA = {json.dumps(theatre_data, indent=2)};\n", encoding="utf-8"
    )

    print("\nDemo Sessions & Repair Theatre evidence generated successfully!")
    print(f"Total sessions: {len(theatre_sessions)}, Total spend: ${meter.spent_usd:.4f}")
    return manifest


if __name__ == "__main__":
    run_all_demo_sessions()
