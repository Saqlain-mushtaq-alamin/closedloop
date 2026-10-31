"""Phase 08: Certification Experiment Runner (Plan §11, PHASE_08_certification.md).

Executes:
1. Frozen configuration check (V11) and judge freeze hash verification.
2. Pilot certification on 1 cell (~10%, 15 runs) with live camera judge, independent
   SciPy recomputation, and cost pre-flight check.
3. Pre-flight verification before full certification launch (Rule H5).
4. Full certification:
   - 16 cells x 150 runs/cell in 4x4 (mass x friction) grid = 2,400 episodes.
   - Headline single sample = 59 episodes on full distribution D (delta=0.05 undivided).
   - Total planned = 2,459 episodes.
   - All seeds strictly in certification stream (2,000,000–2,999,999), single use per program (Rule H9)
     enforced via persistent disk-backed CertificationLedger.
   - Sandboxed execution in subprocess with timeout and memory limit (Rules H13, H15).
5. Live VisionJudge evaluation with calibrated TPR/FPR from Gate G2, thread-safe prompt/response caching.
6. Price-of-footage plot data generated strictly from logs (Rule H11).
7. Append-only logging to episodes.jsonl (Rule H10) and frozen manifest.json (Rule H12).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent


def git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def run_certification(
    run_id: str,
    *,
    pilot: bool = False,
    cert_config_path: str = "configs/cert.yaml",
    pricing_config_path: str = "configs/pricing.yaml",
    tasks_config_path: str = "configs/tasks.yaml",
    runs_dir: str = "runs",
) -> dict[str, Any]:
    """Execute certification experiment (pilot or full)."""
    load_env()

    from closedloop.certify.certify import (
        compute_error_budgets,
        certify_state_cell,
        certify_camera_cell,
        certify_headline,
        recompute_cell_bound,
        preflight_cert_cost,
        compute_price_plot_data,
        get_cell_bounds,
        generate_cell_scenarios,
        BudgetPreflightError,
    )
    from closedloop.data import log as episode_log
    from closedloop.data import manifest as run_manifest
    from closedloop.data.sampler import CertificationLedger, sample, LeakageError
    from closedloop.exec.pilot import execute_episode
    from closedloop.judge.calibrate import compute_judge_freeze_hash
    from closedloop.judge.judge import VisionJudge, render_judge_frame
    from closedloop.llm.client import LLMClient
    from closedloop.llm.cost import CostMeter

    cfg_file = ROOT / cert_config_path
    pricing_file = ROOT / pricing_config_path
    tasks_file = ROOT / tasks_config_path

    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    cert_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    git_sha = git_head()
    created_at = datetime.now(timezone.utc).isoformat()

    # 1. Verify input program
    prog_file = ROOT / cert_cfg["program_file"]
    if not prog_file.exists():
        raise FileNotFoundError(f"Program file not found: {prog_file}")
    policy_code = prog_file.read_text(encoding="utf-8")
    actual_sha = hashlib.sha256(policy_code.encode("utf-8")).hexdigest()
    expected_sha = cert_cfg["program_sha256"]
    if actual_sha != expected_sha:
        raise ValueError(f"Program hash mismatch: {actual_sha} != {expected_sha}")
    program_id = cert_cfg["program_id"]

    # 2. Verify Judge Freeze Hash (Major finding 11)
    judge_cfg_path = ROOT / "configs" / "judge.yaml"
    actual_judge_freeze = compute_judge_freeze_hash(judge_cfg_path)
    j_cal = cert_cfg["judge_calibration"]
    expected_judge_freeze = j_cal["freeze_hash"]
    if actual_judge_freeze != expected_judge_freeze:
        raise ValueError(
            f"Judge freeze hash mismatch: current {actual_judge_freeze} != expected {expected_judge_freeze} "
            "(configs/judge.yaml was modified post-calibration)"
        )

    # 3. Budget & CostMeter setup
    budget_cap = float(cert_cfg.get("budget_cap_usd", 15.0))
    meter = CostMeter(cap_usd=budget_cap)
    pricing_dict = meter.load_prices(pricing_file)

    client = None
    try:
        client = LLMClient(meter)
    except Exception as e:
        print(f"[Cert] Note: LLMClient initialization: {e}")

    # Load persistent response cache from G2 calibration run if present
    initial_cache: dict[str, Any] = {}
    g2_cache_file = ROOT / "runs" / "judge-g2-03" / "llm_cache.json"
    if g2_cache_file.exists():
        try:
            initial_cache.update(json.loads(g2_cache_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    judge = VisionJudge(client=client, cache=dict(initial_cache))

    # Calibrated judge parameters from Gate G2
    k_a = int(j_cal["k_a"])
    n_a = int(j_cal["n_a"])
    k_b = int(j_cal["k_b"])
    n_b = int(j_cal["n_b"])

    # Error budget splits (Plan §11)
    delta = float(cert_cfg["delta"])
    K = int(cert_cfg["K"])
    B = int(cert_cfg["B"])
    M = int(cert_cfg["M"])
    budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M)

    # Output directory
    out_dir = Path(runs_dir) / run_id
    if out_dir.exists():
        if (out_dir / "manifest.json").exists():
            raise FileExistsError(f"Run dir already completed: {out_dir}")
    else:
        out_dir.mkdir(parents=True)
    log_path = out_dir / "episodes.jsonl"

    # Persistent ledger for certification stream (Major finding 9, Rule H9)
    ledger_path = ROOT / runs_dir / ".certification_ledger.json"
    ledger = CertificationLedger(path=ledger_path)

    timeout_s = float(cert_cfg["timeout_s"])
    memory_mb = int(cert_cfg["memory_mb"])

    target_headline_p = float(cert_cfg["targets"]["headline_p"])
    target_state_cell_p = float(cert_cfg["targets"]["state_cell_p"])
    target_camera_cell_p = float(cert_cfg["targets"]["camera_cell_p"])

    used_seeds: list[int] = []

    if pilot:
        # Pilot certification: 1 cell (Cell 0), pilot_runs_per_cell episodes
        runs_per_cell = int(cert_cfg["sample_sizes"]["pilot_runs_per_cell"])
        seed_base = int(cert_cfg["seeds"]["pilot_seed_base"])
        planned_episodes = runs_per_cell

        print(f"=== Starting Phase 08 Pilot: run_id={run_id}, episodes={planned_episodes} ===")
        cell_bounds = get_cell_bounds(0, bounds=cert_cfg["bounds"])
        scenarios = generate_cell_scenarios(
            program_id=program_id,
            n=runs_per_cell,
            seed=seed_base,
            ledger=ledger,
            bounds=cell_bounds,
        )

        cell_state_pass = 0
        cell_cam_pass = 0

        # Run episodes safely with sandboxed subprocess and live camera judge
        for ep_idx, sc in enumerate(scenarios):
            sd = int(sc["seed"])
            used_seeds.append(sd)

            # 1. Sandboxed policy execution (Rules H13, H15)
            try:
                kind, payload = execute_episode(
                    scenario=sc,
                    seed=sd,
                    policy_code=policy_code,
                    repo_root=str(ROOT),
                    timeout_s=timeout_s,
                    memory_mb=memory_mb,
                )
                if kind == "sim":
                    ts = bool(payload["truth_success"])
                    ts_alt = bool(payload["truth_success_alt"])
                    margin = float(payload["margin"])
                    frame_b64 = payload.get("frame_b64")
                else:
                    ts = False
                    ts_alt = False
                    margin = -1.0
                    frame_b64 = None
            except Exception as e:
                print(f"[Pilot Sim Error] Episode {sd}: {e}")
                ts = False
                ts_alt = False
                margin = -1.0
                frame_b64 = None

            # 2. Camera judge evaluation (independent from sim exceptions)
            if frame_b64 is not None:
                try:
                    verdict = judge.judge_episode(frame_b64=frame_b64)
                    jp = bool(verdict.pass_verdict)
                    j_conf = float(verdict.confidence)
                except Exception as e:
                    print(f"[Pilot Judge Error] Episode {sd}: {e}")
                    jp = False
                    j_conf = 0.0
            else:
                jp = False
                j_conf = 0.0

            if ts:
                cell_state_pass += 1
            if jp:
                cell_cam_pass += 1

            rec = episode_log.EpisodeResult(
                episode_id=f"cert-pilot-c00-s{sd}",
                stream="certification",
                task="task_T1",
                program_id=program_id,
                program_version=1,
                scenario=dict(sc),
                seed=sd,
                truth_success=ts,
                truth_success_alt=ts_alt,
                margin=margin,
                judge_mode="camera",
                judge_pass=jp,
                judge_confidence=j_conf,
                trace_path="cell_00",
                frames_path=None,
                tokens_in=sum(int(e.get("tokens_in", 0)) for e in meter.ledger),
                tokens_out=sum(int(e.get("tokens_out", 0)) for e in meter.ledger),
                cost_usd=meter.spent_usd,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            episode_log.append_episode(log_path, rec)

        # Compute cell bounds
        state_bound_res = certify_state_cell(
            k_pass=cell_state_pass,
            n_cell=runs_per_cell,
            d_cell=budgets["state"]["d_cell"],
            target_p=target_state_cell_p,
        )
        cam_bound_res = certify_camera_cell(
            k_pass=cell_cam_pass,
            n_cell=runs_per_cell,
            k_a=k_a,
            n_a=n_a,
            k_b=k_b,
            n_b=n_b,
            d_a=budgets["camera"]["d_a"],
            d_b=budgets["camera"]["d_b"],
            d_cell=budgets["camera"]["d_cell"],
            target_p=target_camera_cell_p,
        )

        # Independent SciPy recomputation check (V10)
        recomp_state = recompute_cell_bound("state", state_bound_res, budgets["state"]["d_cell"])
        recomp_cam = recompute_cell_bound(
            "camera", cam_bound_res, budgets["camera"]["d_cell"],
            k_a=k_a, n_a=n_a, k_b=k_b, n_b=n_b,
            d_a=budgets["camera"]["d_a"], d_b=budgets["camera"]["d_b"],
        )
        assert math.isclose(recomp_state, state_bound_res["bound"], abs_tol=1e-9)
        assert math.isclose(recomp_cam, cam_bound_res["bound"], abs_tol=1e-9)

        # Preflight check against remaining cap from measured cost (Major finding 15)
        total_planned_full = 16 * int(cert_cfg["sample_sizes"]["runs_per_cell"]) + int(cert_cfg["sample_sizes"]["headline_runs"])
        preflight = preflight_cert_cost(
            pilot_cost_usd=meter.spent_usd,
            pilot_episodes=runs_per_cell,
            total_planned_episodes=total_planned_full,
            remaining_budget_usd=budget_cap - meter.spent_usd,
        )

        summary = {
            "run_id": run_id,
            "pilot": True,
            "episodes_completed": len(used_seeds),
            "episodes_planned": planned_episodes,
            "pilot_cell_idx": 0,
            "state_cell": state_bound_res,
            "camera_cell": cam_bound_res,
            "recompute_matches": True,
            "preflight": preflight,
            "meter_cost_usd": meter.spent_usd,
        }
        (out_dir / "pilot_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (out_dir / "llm_cache.json").write_text(json.dumps(judge.cache, indent=2) + "\n", encoding="utf-8")

        manifest = run_manifest.build_manifest(
            run_id=run_id,
            git_sha=git_sha,
            config_hash=cfg_hash,
            model=cert_cfg.get("model", "muse-spark-1.3"),
            pricing=pricing_dict,
            budget_cap_usd=budget_cap,
            episodes_planned=planned_episodes,
            seeds=used_seeds,
            generation={"pilot": True, "program_id": program_id},
            created_at=created_at,
            status="valid",
        )
        run_manifest.write_manifest(out_dir, manifest)
        print(f"=== Pilot Complete: {len(used_seeds)} episodes logged ===")
        return summary

    else:
        # Full certification: 16 cells x 150 runs + 59 headline runs = 2,459 episodes
        runs_per_cell = int(cert_cfg["sample_sizes"]["runs_per_cell"])
        headline_runs = int(cert_cfg["sample_sizes"]["headline_runs"])
        cell_seed_base = int(cert_cfg["seeds"]["cell_seed_base"])
        headline_seed_base = int(cert_cfg["seeds"]["headline_seed_base"])
        planned_episodes = 16 * runs_per_cell + headline_runs

        # Pre-flight verification before full launch (Major finding 14)
        pilot_summary_file = Path(runs_dir) / "cert-pilot-01" / "pilot_summary.json"
        if not pilot_summary_file.exists():
            raise BudgetPreflightError(
                f"Pilot summary not found at {pilot_summary_file}. Run pilot first for cost preflight (Rule H5)."
            )
        pilot_summary = json.loads(pilot_summary_file.read_text(encoding="utf-8"))
        pilot_cost = float(pilot_summary["meter_cost_usd"])
        pilot_n = int(pilot_summary["episodes_completed"])
        preflight_check = preflight_cert_cost(
            pilot_cost_usd=pilot_cost,
            pilot_episodes=pilot_n,
            total_planned_episodes=planned_episodes,
            remaining_budget_usd=budget_cap,
        )
        print(
            f"Preflight OK: Projected cost ${preflight_check['projected_cost_usd']:.4f} < "
            f"Headroom ${budget_cap:.4f} (unit: ${preflight_check['cost_per_ep_usd']:.6f}/ep)"
        )

        print(f"=== Starting Phase 08 Full Certification: run_id={run_id}, planned={planned_episodes} ===")

        existing_recs: list[dict[str, Any]] = []
        if log_path.exists():
            existing_recs = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        if len(existing_recs) == planned_episodes:
            print(f"Resuming certification: found {len(existing_recs)} complete episodes in {log_path}.")
            used_seeds = [int(r["seed"]) for r in existing_recs]
            cell_state_passes = [0] * 16
            cell_cam_passes = [0] * 16
            hl_state_pass = 0
            hl_cam_pass = 0
            for r in existing_recs:
                tp = str(r["trace_path"])
                ts = bool(r["truth_success"])
                jp = bool(r["judge_pass"])
                if tp == "headline":
                    if ts:
                        hl_state_pass += 1
                    if jp:
                        hl_cam_pass += 1
                elif tp.startswith("cell_"):
                    c_idx = int(tp.split("_")[1])
                    if ts:
                        cell_state_passes[c_idx] += 1
                    if jp:
                        cell_cam_passes[c_idx] += 1
            executed_episodes = existing_recs
        else:
            # Build list of all planned episode descriptors
            all_specs: list[dict[str, Any]] = []

            # 16 cells
            for c_idx in range(16):
                c_bounds = get_cell_bounds(c_idx, bounds=cert_cfg["bounds"])
                c_seed_start = cell_seed_base + c_idx * runs_per_cell
                c_scenarios = generate_cell_scenarios(
                    program_id=program_id,
                    n=runs_per_cell,
                    seed=c_seed_start,
                    ledger=ledger,
                    bounds=c_bounds,
                )
                c_id = f"cell_{c_idx:02d}"
                for sc in c_scenarios:
                    all_specs.append({
                        "trace_path": c_id,
                        "cell_idx": c_idx,
                        "scenario": sc,
                        "seed": int(sc["seed"]),
                        "is_headline": False,
                    })

            # Headline
            hl_bounds = {k: tuple(v) for k, v in cert_cfg["bounds"].items()}
            headline_scenarios = generate_cell_scenarios(
                program_id=program_id,
                n=headline_runs,
                seed=headline_seed_base,
                ledger=ledger,
                bounds=hl_bounds,
            )
            for sc in headline_scenarios:
                all_specs.append({
                    "trace_path": "headline",
                    "cell_idx": -1,
                    "scenario": sc,
                    "seed": int(sc["seed"]),
                    "is_headline": True,
                })

            assert len(all_specs) == planned_episodes, f"Spec count {len(all_specs)} != planned {planned_episodes}"

            # Step 1: Execute all episodes in safe sandboxed subprocesses (Rules H13, H15)
            print(f"Executing {len(all_specs)} episodes in sandboxed subprocesses (max_workers=8)...")
            executed_episodes = []
            frames_to_judge: set[str] = set()

            def _execute_single(spec: dict[str, Any]) -> dict[str, Any]:
                sc = spec["scenario"]
                sd = spec["seed"]
                try:
                    kind, payload = execute_episode(
                        scenario=sc,
                        seed=sd,
                        policy_code=policy_code,
                        repo_root=str(ROOT),
                        timeout_s=timeout_s,
                        memory_mb=memory_mb,
                    )
                    if kind == "sim":
                        ts = bool(payload["truth_success"])
                        ts_alt = bool(payload["truth_success_alt"])
                        margin = float(payload["margin"])
                        frame_b64 = payload.get("frame_b64")
                    else:
                        ts = False
                        ts_alt = False
                        margin = -1.0
                        frame_b64 = None
                except Exception:
                    ts = False
                    ts_alt = False
                    margin = -1.0
                    frame_b64 = None

                return {
                    "spec": spec,
                    "ts": ts,
                    "ts_alt": ts_alt,
                    "margin": margin,
                    "frame_b64": frame_b64,
                }

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                for idx, ep_data in enumerate(executor.map(_execute_single, all_specs)):
                    used_seeds.append(ep_data["spec"]["seed"])
                    if ep_data["frame_b64"]:
                        frames_to_judge.add(ep_data["frame_b64"])
                    executed_episodes.append(ep_data)

                    if (idx + 1) % 250 == 0 or (idx + 1) == len(all_specs):
                        print(f"  Sim progress: {idx + 1}/{len(all_specs)} episodes completed")

            # Step 2: Live camera evaluation of unique frames (Blockers 1, 2)
            uncached_frames = [
                b64 for b64 in frames_to_judge
                if hashlib.sha256(
                    f"{judge.model}:{judge.segmentation_model}:{hashlib.sha256(b64.encode()).hexdigest()}:{judge.prompt}".encode()
                ).hexdigest()[:24] not in judge.cache
            ]
            print(
                f"Unique frames across run: {len(frames_to_judge)}, "
                f"Uncached frames requiring live judge evaluation: {len(uncached_frames)}"
            )

            if uncached_frames:
                print("Evaluating uncached frames with Meta Model API (VisionJudge)...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(judge.judge_episode, frame_b64=b64): b64 for b64 in uncached_frames}
                    done_count = 0
                    for fut in concurrent.futures.as_completed(futures):
                        try:
                            fut.result()
                        except Exception as e:
                            print(f"[Judge API Error]: {e}")
                        done_count += 1
                        if done_count % 100 == 0 or done_count == len(uncached_frames):
                            print(f"  Judge progress: {done_count}/{len(uncached_frames)} frames evaluated")

            # Step 3: Assign verdicts and append to episodes.jsonl (Rule H10)
            cell_state_passes = [0] * 16
            cell_cam_passes = [0] * 16
            hl_state_pass = 0
            hl_cam_pass = 0

            for ep_data in executed_episodes:
                spec = ep_data["spec"]
                sc = spec["scenario"]
                sd = spec["seed"]
                ts = ep_data["ts"]
                ts_alt = ep_data["ts_alt"]
                margin = ep_data["margin"]
                frame_b64 = ep_data["frame_b64"]
                c_id = spec["trace_path"]
                c_idx = spec["cell_idx"]
                is_hl = spec["is_headline"]

                # Evaluate verdict from judge
                try:
                    verdict = judge.judge_episode(frame_b64=frame_b64)
                    jp = bool(verdict.pass_verdict)
                    j_conf = float(verdict.confidence)
                    tok_in = verdict.tokens_in
                    tok_out = verdict.tokens_out
                    cost_usd = verdict.cost_usd
                except Exception:
                    jp = False
                    j_conf = 0.0
                    tok_in = 0
                    tok_out = 0
                    cost_usd = 0.0

                if not is_hl:
                    if ts:
                        cell_state_passes[c_idx] += 1
                    if jp:
                        cell_cam_passes[c_idx] += 1
                    ep_id = f"cert-{c_id}-s{sd}"
                else:
                    if ts:
                        hl_state_pass += 1
                    if jp:
                        hl_cam_pass += 1
                    ep_id = f"cert-headline-s{sd}"

                rec = episode_log.EpisodeResult(
                    episode_id=ep_id,
                    stream="certification",
                    task="task_T1",
                    program_id=program_id,
                    program_version=1,
                    scenario=dict(sc),
                    seed=sd,
                    truth_success=ts,
                    truth_success_alt=ts_alt,
                    margin=margin,
                    judge_mode="camera",
                    judge_pass=jp,
                    judge_confidence=j_conf,
                    trace_path=c_id,
                    frames_path=None,
                    tokens_in=tok_in,
                    tokens_out=tok_out,
                    cost_usd=meter.spent_usd,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                episode_log.append_episode(log_path, rec)

        # Step 4: Compute bounds and summaries
        cell_summaries: dict[str, Any] = {}
        for c_idx in range(16):
            c_id = f"cell_{c_idx:02d}"
            c_bounds = get_cell_bounds(c_idx, bounds=cert_cfg["bounds"])
            s_cert = certify_state_cell(cell_state_passes[c_idx], runs_per_cell, budgets["state"]["d_cell"], target_state_cell_p)
            c_cert = certify_camera_cell(
                cell_cam_passes[c_idx], runs_per_cell, k_a, n_a, k_b, n_b,
                budgets["camera"]["d_a"], budgets["camera"]["d_b"], budgets["camera"]["d_cell"],
                target_camera_cell_p,
            )
            rec_s = recompute_cell_bound("state", s_cert, budgets["state"]["d_cell"])
            rec_c = recompute_cell_bound(
                "camera", c_cert, budgets["camera"]["d_cell"],
                k_a=k_a, n_a=n_a, k_b=k_b, n_b=n_b,
                d_a=budgets["camera"]["d_a"], d_b=budgets["camera"]["d_b"],
            )
            assert math.isclose(rec_s, s_cert["bound"], abs_tol=1e-9)
            assert math.isclose(rec_c, c_cert["bound"], abs_tol=1e-9)

            cell_summaries[c_id] = {
                "cell_idx": c_idx,
                "bounds": c_bounds,
                "n_episodes": runs_per_cell,
                "state": s_cert,
                "camera": c_cert,
                "recomputed_state_bound": round(rec_s, 4),
                "recomputed_camera_bound": round(rec_c, 4),
            }

        # Headline certificates
        hl_state_cert = certify_headline(hl_state_pass, headline_runs, delta=delta, mode="state", target_p=target_headline_p)
        hl_cam_cert = certify_headline(
            hl_cam_pass, headline_runs, delta=delta, mode="camera", target_p=target_camera_cell_p,
            k_a=k_a, n_a=n_a, k_b=k_b, n_b=n_b, B=B,
        )
        rec_hl_state = recompute_cell_bound("state", hl_state_cert, delta)
        assert math.isclose(rec_hl_state, hl_state_cert["bound"], abs_tol=1e-9)

        # Price plot data strictly from logs
        price_plot = compute_price_plot_data(
            episodes_path=log_path,
            K=K,
            target_state_p=target_state_cell_p,
            target_camera_p=target_camera_cell_p,
            delta=delta,
            k_a=k_a,
            n_a=n_a,
            k_b=k_b,
            n_b=n_b,
        )
        (out_dir / "price_plot_data.json").write_text(json.dumps(price_plot, indent=2) + "\n", encoding="utf-8")
        (out_dir / "llm_cache.json").write_text(json.dumps(judge.cache, indent=2) + "\n", encoding="utf-8")

        actual_spent = meter.spent_usd if meter.spent_usd > 0 else float(executed_episodes[-1].get("cost_usd", 0.0))
        summary = {
            "run_id": run_id,
            "pilot": False,
            "episodes_completed": len(executed_episodes),
            "episodes_planned": planned_episodes,
            "program_id": program_id,
            "program_sha256": actual_sha,
            "headline_state": hl_state_cert,
            "headline_camera": hl_cam_cert,
            "cells": cell_summaries,
            "price_plot": price_plot,
            "spent_usd": actual_spent,
            "created_at": created_at,
        }
        (out_dir / "cert_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

        if len(executed_episodes) != planned_episodes:
            raise RuntimeError(f"Logged episodes {len(executed_episodes)} != planned {planned_episodes}")

        manifest = run_manifest.build_manifest(
            run_id=run_id,
            git_sha=git_sha,
            config_hash=cfg_hash,
            model=cert_cfg.get("model", "muse-spark-1.3"),
            pricing=pricing_dict,
            budget_cap_usd=budget_cap,
            episodes_planned=planned_episodes,
            seeds=used_seeds,
            generation={
                "program_id": program_id,
                "headline_state_bound": hl_state_cert["bound"],
                "headline_state_certified": hl_state_cert["certified"],
                "state_area_fraction": price_plot["state_area_fraction"],
                "camera_area_fraction": price_plot["camera_area_fraction"],
                "price_of_footage_area_loss": price_plot["price_of_footage_area_loss"],
            },
            created_at=created_at,
            status="valid",
        )
        run_manifest.write_manifest(out_dir, manifest)
        print(f"=== Full Certification Complete: run_id={run_id} ===")
        print(f"Headline State: bound={hl_state_cert['bound']:.4f} (target {target_headline_p}), certified={hl_state_cert['certified']}")
        print(f"State Area Fraction: {price_plot['state_area_fraction']:.4f}")
        print(f"Camera Area Fraction: {price_plot['camera_area_fraction']:.4f}")
        print(f"Price of Footage Loss: {price_plot['price_of_footage_area_loss']:.4f}")
        print(f"Total Meter Spend: ${meter.spent_usd:.4f} (Cap: ${budget_cap:.2f})")
        return summary


def verify_phase_08_gate(run_id: str = "cert-full-01", runs_dir: str = "runs") -> None:
    """Gate verification for Phase 08 (called by make gate PHASE=08)."""
    from closedloop.certify import stats
    from closedloop.certify.certify import compute_error_budgets, compute_price_plot_data
    from closedloop.data import log as episode_log
    from closedloop.judge.calibrate import compute_judge_freeze_hash

    r_dir = Path(runs_dir) / run_id
    if not r_dir.exists():
        raise AssertionError(f"Run dir does not exist: {r_dir}")

    # 1. Config freeze check & judge freeze verification (Major finding 11)
    cfg_file = ROOT / "configs" / "cert.yaml"
    if not cfg_file.exists():
        raise AssertionError(f"Config cert.yaml missing: {cfg_file}")
    cert_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    actual_judge_freeze = compute_judge_freeze_hash(ROOT / "configs" / "judge.yaml")
    expected_judge_freeze = cert_cfg["judge_calibration"]["freeze_hash"]
    assert actual_judge_freeze == expected_judge_freeze, (
        f"Judge freeze hash mismatch: {actual_judge_freeze} != {expected_judge_freeze}"
    )

    man_file = r_dir / "manifest.json"
    if not man_file.exists():
        raise AssertionError("manifest.json missing")
    manifest = json.loads(man_file.read_text(encoding="utf-8"))
    assert manifest["status"] == "valid", f"manifest status {manifest['status']} != valid"

    ep_file = r_dir / "episodes.jsonl"
    if not ep_file.exists():
        raise AssertionError("episodes.jsonl missing")
    episodes = episode_log.read_episodes(ep_file)
    assert len(episodes) == manifest["episodes_planned"], (
        f"episodes {len(episodes)} != planned {manifest['episodes_planned']}"
    )

    # 2. V4: Seed uniqueness and stream check [2,000,000, 2,999,999]
    seeds = [ep.seed for ep in episodes]
    assert len(seeds) == len(set(seeds)), "Duplicate certification seeds detected (V4 violation)"
    for s in seeds:
        assert 2000000 <= s <= 2999999, f"Seed {s} outside certification stream [2000000, 2999999]"

    # 3. Read cert summary
    summary_file = r_dir / "cert_summary.json"
    if not summary_file.exists():
        raise AssertionError("cert_summary.json missing")
    summary = json.loads(summary_file.read_text(encoding="utf-8"))

    # 4. Read price plot
    price_file = r_dir / "price_plot_data.json"
    if not price_file.exists():
        raise AssertionError("price_plot_data.json missing")
    price_plot = json.loads(price_file.read_text(encoding="utf-8"))

    assert price_plot["state_area_fraction"] > 0, "State certified area must be > 0"
    assert price_plot["camera_area_fraction"] <= price_plot["state_area_fraction"] + 1e-6, (
        f"Camera area {price_plot['camera_area_fraction']} > state area {price_plot['state_area_fraction']}"
    )

    # 5. Full recomputation of headline AND all 16 cells directly from episodes.jsonl (Major finding 12)
    delta = float(cert_cfg["delta"])
    K = int(cert_cfg["K"])
    B = int(cert_cfg["B"])
    M = int(cert_cfg["M"])
    budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M)
    d_cell_state = budgets["state"]["d_cell"]
    d_cell_cam = budgets["camera"]["d_cell"]
    d_a = budgets["camera"]["d_a"]
    d_b = budgets["camera"]["d_b"]
    j_cal = cert_cfg["judge_calibration"]
    k_a = int(j_cal["k_a"])
    n_a = int(j_cal["n_a"])
    k_b = int(j_cal["k_b"])
    n_b = int(j_cal["n_b"])

    # Aggregate counts from raw episodes
    cell_state_counts: dict[str, int] = {}
    cell_cam_counts: dict[str, int] = {}
    cell_totals: dict[str, int] = {}
    hl_state_k = 0
    hl_cam_k = 0
    hl_total = 0

    for ep in episodes:
        c_id = ep.trace_path
        if c_id == "headline":
            hl_total += 1
            if ep.truth_success:
                hl_state_k += 1
            if ep.judge_pass:
                hl_cam_k += 1
        elif c_id.startswith("cell_"):
            cell_totals[c_id] = cell_totals.get(c_id, 0) + 1
            if ep.truth_success:
                cell_state_counts[c_id] = cell_state_counts.get(c_id, 0) + 1
            if ep.judge_pass:
                cell_cam_counts[c_id] = cell_cam_counts.get(c_id, 0) + 1
        else:
            raise AssertionError(f"Unknown trace_path in episode: {c_id}")

    # Recompute headline
    recomp_hl_state = stats.cp_lower(hl_state_k, hl_total, delta)
    summary_hl_bound = summary["headline_state"]["bound"]
    assert math.isclose(summary_hl_bound, recomp_hl_state, abs_tol=1e-9), (
        f"Headline bound mismatch: summary {summary_hl_bound} != raw recompute {recomp_hl_state}"
    )

    # Recompute all 16 cells and assert summary matches raw episodes
    assert len(cell_totals) == 16, f"Expected 16 cells, found {len(cell_totals)}"
    for c_id, n_total in cell_totals.items():
        ks = cell_state_counts.get(c_id, 0)
        kc = cell_cam_counts.get(c_id, 0)
        raw_s_bound = stats.cp_lower(ks, n_total, d_cell_state)
        raw_c_bound = stats.corrected_lower(kc, n_total, k_a, n_a, k_b, n_b, d_a, d_b, d_cell_cam)

        summary_cell = summary["cells"][c_id]
        sum_s_bound = summary_cell["state"]["bound"]
        sum_c_bound = summary_cell["camera"]["bound"]

        assert math.isclose(sum_s_bound, raw_s_bound, abs_tol=1e-9), (
            f"Cell {c_id} state bound mismatch: summary {sum_s_bound} != raw {raw_s_bound}"
        )
        assert math.isclose(sum_c_bound, raw_c_bound, abs_tol=1e-9), (
            f"Cell {c_id} camera bound mismatch: summary {sum_c_bound} != raw {raw_c_bound}"
        )

    # Recompute price plot data from episodes.jsonl and assert exact match
    recomputed_plot = compute_price_plot_data(
        episodes_path=ep_file,
        K=K,
        target_state_p=float(cert_cfg["targets"]["state_cell_p"]),
        target_camera_p=float(cert_cfg["targets"]["camera_cell_p"]),
        delta=delta,
        k_a=k_a,
        n_a=n_a,
        k_b=k_b,
        n_b=n_b,
    )
    assert price_plot["state_area_fraction"] == recomputed_plot["state_area_fraction"], "State area mismatch"
    assert price_plot["camera_area_fraction"] == recomputed_plot["camera_area_fraction"], "Camera area mismatch"
    assert price_plot["price_of_footage_area_loss"] == recomputed_plot["price_of_footage_area_loss"], "Price loss mismatch"

    print(f"PHASE 08 GATE VERIFIED: run_id={run_id}, episodes={len(episodes)}")
    print(f"Headline State Bound: {summary_hl_bound:.4f} (certified: {summary['headline_state']['certified']})")
    print(f"State Area: {price_plot['state_area_fraction']:.4f}, Camera Area: {price_plot['camera_area_fraction']:.4f}")
    print("PHASE 08: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 08 Certification Runner.")
    parser.add_argument("--run-id", default="cert-pilot-01")
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()

    run_certification(run_id=args.run_id, pilot=args.pilot)


if __name__ == "__main__":
    main()
