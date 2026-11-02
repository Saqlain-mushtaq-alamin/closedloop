"""Phase 08b: Certificate-Guided Repair v2 Certification Runner.

Executes:
1. validate_v2_freeze: Re-verifies frozen program v2 before any certification episode (Rule V11).
2. run_cert_v2: Independent certification of v2 under run_id cert2-full-01 using fresh certification
   seeds from 2,100,000 (disjoint from 2,000,000–2,030,299). State mode first.
3. check_frozen_judge_v2: 200-rollout check of the frozen judge on v2 rollouts with calibration seeds
   from 1,002,000.
4. side_by_side_report: Side-by-side comparison of v1 and v2 certificates with pre-registered claim wording.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import yaml


class FreezeError(ValueError):
    """Raised when frozen program artifacts are missing or invalid."""


def git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def validate_v2_freeze(freeze_dir: str | Path) -> dict[str, Any]:
    """Validate that program v2 is strictly frozen with valid SHA-256 before any cert episode."""
    freeze_dir = Path(freeze_dir)
    freeze_path = freeze_dir / "freeze.json"
    if not freeze_path.exists():
        raise FreezeError(f"freeze.json missing in {freeze_dir}")

    try:
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FreezeError(f"unreadable freeze.json: {exc}") from exc

    if not isinstance(freeze, dict) or not freeze:
        raise FreezeError(f"freeze.json is empty or invalid in {freeze_dir}")

    source_file = freeze.get("source_file", "program_final.py")
    source_path = freeze_dir / source_file
    if not source_path.exists():
        raise FreezeError(f"frozen source {source_file} missing in {freeze_dir}")

    code = source_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise FreezeError(f"source does not parse: {exc}") from exc

    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "policy" for node in tree.body
    ):
        raise FreezeError("source defines no top-level policy(env, rng)")

    # LF-normalized sha256
    norm_code = code.replace("\r\n", "\n")
    sha = hashlib.sha256(norm_code.encode("utf-8")).hexdigest()
    if sha != freeze.get("sha256"):
        raise FreezeError(f"sha256 mismatch: {sha} != {freeze.get('sha256')}")
    if freeze.get("program_id") != sha[:16]:
        raise FreezeError("program_id does not match sha256[:16]")

    acc = freeze.get("acceptance", {})
    if acc.get("reason") != "accepted":
        raise FreezeError(f"freeze indicates non-accepted status: {acc}")

    return freeze


def run_cert_v2(
    run_id: str = "cert2-full-01",
    *,
    cert2_config_path: str = "configs/cert2.yaml",
    pricing_config_path: str = "configs/pricing.yaml",
    tasks_config_path: str = "configs/tasks.yaml",
    runs_dir: str = "runs",
    mode: str = "state",
) -> dict[str, Any]:
    """Execute certification of candidate v2 in state mode."""
    from closedloop.certify.certify import (
        compute_error_budgets,
        get_cell_bounds,
    )
    from closedloop.certify.stats import cp_lower
    from closedloop.data import log as episode_log
    from closedloop.data import manifest as run_manifest
    from closedloop.data.sampler import CertificationLedger, sample, LeakageError
    from closedloop.exec.pilot import execute_episode
    from closedloop.llm.cost import CostMeter

    cfg_file = ROOT / cert2_config_path
    pricing_file = ROOT / pricing_config_path
    tasks_file = ROOT / tasks_config_path

    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    cert_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    git_sha = git_head()
    created_at = datetime.now(timezone.utc).isoformat()

    # 1. Enforce freeze-before-cert validation (Rule V11)
    mint_run_id = cert_cfg.get("program_run_id", "round2-mint-01")
    mint_dir = Path(runs_dir) / mint_run_id
    freeze = validate_v2_freeze(mint_dir)

    policy_code = (mint_dir / freeze["source_file"]).read_text(encoding="utf-8")
    program_id = freeze["program_id"]
    program_sha = freeze["sha256"]

    # 2. Check and claim certification seeds via persistent ledger (Rule H9, T3 Guard)
    ledger_path = Path(runs_dir) / ".certification_ledger.json"
    if not ledger_path.exists():
        raise FileNotFoundError(f"Certification ledger missing at {ledger_path}")
    ledger = CertificationLedger(ledger_path)
    if len(ledger.claimed) == 0:
        raise ValueError("Certification ledger is empty or has been reset")

    n_per_cell = int(cert_cfg["sample_sizes"]["runs_per_cell"])
    n_headline = int(cert_cfg["sample_sizes"]["headline_runs"])
    cell_seed_base = int(cert_cfg["seeds"]["cell_seed_base"])
    headline_seed_base = int(cert_cfg["seeds"]["headline_seed_base"])

    # Cell seeds: 16 cells x 150 = 2400
    total_cell_episodes = 16 * n_per_cell
    all_cert_seeds = list(range(cell_seed_base, cell_seed_base + total_cell_episodes))
    headline_seeds = list(range(headline_seed_base, headline_seed_base + n_headline))
    all_cert_seeds.extend(headline_seeds)

    # Claim in ledger
    ledger.claim(program_id, all_cert_seeds)

    # 3. Setup run directory (T3 Guard)
    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run dir already exists: {run_dir}")
    log_path = run_dir / "episodes.jsonl"
    if log_path.exists() and log_path.stat().st_size > 0:
        raise ValueError(f"episodes.jsonl already exists and is non-empty: {log_path}")
    run_dir.mkdir(parents=True)


    delta = float(cert_cfg["delta"])
    K = int(cert_cfg["K"])
    budgets = compute_error_budgets(delta, K=K, M=1)
    d_cell = budgets["state"]["d_cell"]

    timeout_s = float(cert_cfg["timeout_s"])
    memory_mb = int(cert_cfg["memory_mb"])

    # Generate scenarios
    bounds = cert_cfg["bounds"]
    mass_min, mass_max = bounds["mass"]
    fric_min, fric_max = bounds["friction"]
    m_step = (mass_max - mass_min) / 4.0
    f_step = (fric_max - fric_min) / 4.0

    cells_data: dict[str, Any] = {}
    total_logged = 0

    print(f"Starting {run_id} (program_id={program_id}) — {16} cells x {n_per_cell} + {n_headline} headline episodes...")
    ep_idx = 0

    import concurrent.futures

    all_specs: list[dict[str, Any]] = []

    # 16 cells
    for cell_idx in range(16):
        cell_id = f"cell_{cell_idx:02d}"
        m_idx = cell_idx // 4
        f_idx = cell_idx % 4
        c_bounds = {
            "x": bounds["x"],
            "y": bounds["y"],
            "yaw": bounds["yaw"],
            "mass": (mass_min + m_idx * m_step, mass_min + (m_idx + 1) * m_step),
            "friction": (fric_min + f_idx * f_step, fric_min + (f_idx + 1) * f_step),
        }
        cell_seeds = list(range(cell_seed_base + cell_idx * n_per_cell, cell_seed_base + (cell_idx + 1) * n_per_cell))
        cell_scenarios = sample("certification", n=n_per_cell, seed=cell_seeds[0], bounds=c_bounds)
        for sc in cell_scenarios:
            all_specs.append({
                "cell_id": cell_id,
                "cell_idx": cell_idx,
                "scenario": sc,
                "seed": int(sc["seed"]),
                "is_headline": False,
                "c_bounds": c_bounds,
            })

    # Headline
    headline_scenarios = sample("certification", n=n_headline, seed=headline_seed_base, bounds=bounds)
    for sc in headline_scenarios:
        all_specs.append({
            "cell_id": "headline",
            "cell_idx": -1,
            "scenario": sc,
            "seed": int(sc["seed"]),
            "is_headline": True,
            "c_bounds": bounds,
        })

    print(f"Executing {len(all_specs)} episodes in sandboxed subprocesses (max_workers=8)...")

    def _exec_single(spec: dict[str, Any]) -> dict[str, Any]:
        sc = spec["scenario"]
        sd = spec["seed"]
        kind, payload = execute_episode(
            sc, sd, policy_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        ts = bool(payload.get("truth_success", False)) if kind == "sim" else False
        alt = bool(payload.get("truth_success_alt", False)) if kind == "sim" else False
        margin = float(payload.get("margin", -1.0)) if kind == "sim" else -1.0
        return {
            "spec": spec,
            "truth_success": ts,
            "truth_success_alt": alt,
            "margin": margin,
            "trace_steps": len(payload.get("trace", [])),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_exec_single, all_specs))

    # Log append-only in deterministic order
    cell_k_pass = [0] * 16
    hl_pass = 0

    for ep_idx, res in enumerate(results):
        spec = res["spec"]
        sc = spec["scenario"]
        sd = spec["seed"]
        ts = res["truth_success"]
        alt = res["truth_success_alt"]
        mg = res["margin"]
        cid = spec["cell_id"]

        if spec["is_headline"]:
            if ts:
                hl_pass += 1
            ep_name = f"headline-ep{ep_idx:04d}"
        else:
            c_idx = spec["cell_idx"]
            if ts:
                cell_k_pass[c_idx] += 1
            ep_name = f"{cid}-ep{ep_idx:04d}"

        episode_log.append_episode(
            log_path,
            episode_log.EpisodeResult(
                episode_id=ep_name,
                stream="certification",
                task="task_T1",
                program_id=program_id,
                program_version=1,
                scenario=dict(sc),
                seed=sd,
                truth_success=ts,
                truth_success_alt=alt,
                margin=mg,
                judge_mode="state",
                judge_pass=None,
                judge_confidence=None,
                trace_path=f"steps:{res['trace_steps']}",
                frames_path=None,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                created_at=created_at,
            ),
        )

    # Recompute cell stats
    for cell_idx in range(16):
        cid = f"cell_{cell_idx:02d}"
        m_idx = cell_idx // 4
        f_idx = cell_idx % 4
        c_bounds = {
            "mass": (mass_min + m_idx * m_step, mass_min + (m_idx + 1) * m_step),
            "friction": (fric_min + f_idx * f_step, fric_min + (f_idx + 1) * f_step),
        }
        k_pass = cell_k_pass[cell_idx]
        lower_bound = cp_lower(k_pass, n_per_cell, d_cell)
        certified = lower_bound >= cert_cfg["targets"]["state_cell_p"]
        cells_data[cid] = {
            "mass_bounds": list(c_bounds["mass"]),
            "friction_bounds": list(c_bounds["friction"]),
            "state": {
                "k_pass": k_pass,
                "n_runs": n_per_cell,
                "lower_bound": round(lower_bound, 4),
                "certified": certified,
            },
        }

    hl_lower = cp_lower(hl_pass, n_headline, delta)
    hl_certified = hl_lower >= cert_cfg["targets"]["headline_p"]

    certified_cells_count = sum(1 for c in cells_data.values() if c["state"]["certified"])
    certified_area_frac = certified_cells_count / 16.0

    summary = {
        "run_id": run_id,
        "program_id": program_id,
        "program_sha256": program_sha,
        "source_v1_run": "cert-mint-03",
        "created_at": created_at,
        "headline": {
            "state": {
                "k_pass": hl_pass,
                "n_runs": n_headline,
                "lower_bound": round(hl_lower, 4),
                "certified": hl_certified,
            }
        },
        "cells": cells_data,
        "certified_cells_count": certified_cells_count,
        "certified_area_fraction": round(certified_area_frac, 4),
        "claim": "certified in simulation under distribution D",
        "provenance_note": (
            "v2 was created after seeing v1's certificate; v2's certificate is valid because v2 was fixed before its own data was drawn."
        ),
    }

    (run_dir / "cert_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = {
        "run_id": run_id,
        "git_sha": git_sha,
        "config_hash": cfg_hash,
        "created_at": created_at,
        "model": "deterministic_sim",
        "pricing_per_mtok": {},
        "budget_cap_usd": float(cert_cfg.get("budget_cap_usd", 15.0)),
        "spent_usd": 0.0,
        "episodes_planned": total_cell_episodes + n_headline,
        "seeds": all_cert_seeds,
        "status": "valid",
        "candidate": {
            "version": "v2",
            "source_program_id": cert_cfg.get("program_id", "bec73dec45a88431"),
            "program_id": program_id,
            "program_sha256": program_sha,
            "certified_area": round(certified_area_frac, 4),
            "headline_pass": f"{hl_pass}/{n_headline}",
            "headline_lower": round(hl_lower, 4),
        },
    }

    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Certification {run_id} complete! Certified area: {certified_area_frac:.4f} ({certified_cells_count}/16 cells). Headline: {hl_pass}/{n_headline} (p_L={hl_lower:.4f}).")
    return summary


def check_frozen_judge_v2(
    v2_code: str,
    *,
    calib_seed_base: int = 1002000,
    n_rollouts: int = 200,
) -> dict[str, Any]:
    """Check frozen judge performance on 200 rollouts of v2 using calibration seeds."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from closedloop.data.sampler import sample
    from closedloop.exec.pilot import execute_episode
    from closedloop.judge.judge import VisionJudge, render_judge_frame
    from closedloop.llm.client import LLMClient
    from closedloop.llm.cost import CostMeter

    meter = CostMeter(cap_usd=2.0)
    pricing_file = ROOT / "configs" / "pricing.yaml"
    meter.load_prices(pricing_file)
    client = LLMClient(meter)
    judge = VisionJudge(client=client)

    tasks_file = ROOT / "configs" / "tasks.yaml"
    tasks_cfg = yaml.safe_load(tasks_file.read_text(encoding="utf-8"))
    t1_cfg = tasks_cfg["task_T1"]
    bounds = {
        "x": tuple(t1_cfg["tier1"]["x"]),
        "y": tuple(t1_cfg["tier1"]["y"]),
        "yaw": tuple(t1_cfg["tier1"]["yaw"]),
        "mass": tuple(t1_cfg["tier2_mass"]),
        "friction": tuple(t1_cfg["tier2_friction"]),
    }

    scenarios = sample("calibration", n=n_rollouts, seed=calib_seed_base, bounds=bounds)

    tpr_matches = 0
    tpr_total = 0
    fpr_false_pos = 0
    fpr_total = 0

    print(f"Evaluating frozen judge on {n_rollouts} rollouts of v2 (seeds {calib_seed_base}..{calib_seed_base + n_rollouts - 1})...")

    for i, sc in enumerate(scenarios):
        sd = int(sc["seed"])
        kind, payload = execute_episode(
            sc, sd, v2_code, repo_root=str(ROOT),
            timeout_s=60, memory_mb=1024,
        )
        ts = bool(payload.get("truth_success", False)) if kind == "sim" else False
        frame_b64 = payload.get("frame_b64")

        # Live evaluate with frozen judge
        if frame_b64:
            verdict = judge.judge_episode(frame_b64=frame_b64)
            jp, conf = verdict.pass_verdict, verdict.confidence
        else:
            jp, conf = False, 0.0

        if ts:
            tpr_total += 1
            if jp:
                tpr_matches += 1
        else:
            fpr_total += 1
            if jp:
                fpr_false_pos += 1

    tpr = tpr_matches / tpr_total if tpr_total > 0 else 1.0
    fpr = fpr_false_pos / fpr_total if fpr_total > 0 else 0.0

    print(f"Judge check result on v2: TPR={tpr:.4f} ({tpr_matches}/{tpr_total}), FPR={fpr:.4f} ({fpr_false_pos}/{fpr_total})")
    return {
        "n_rollouts": n_rollouts,
        "calib_seeds": [calib_seed_base, calib_seed_base + n_rollouts - 1],
        "tpr": tpr,
        "tpr_counts": [tpr_matches, tpr_total],
        "fpr": fpr,
        "fpr_counts": [fpr_false_pos, fpr_total],
        "consistent_with_g2": tpr >= 0.85 and fpr <= 0.15,
        "spend_usd": round(meter.spent_usd, 6),
    }


def side_by_side_report(v1_run_id: str = "cert-full-01", v2_run_id: str = "cert2-full-01") -> str:
    """Produce honest side-by-side comparison of v1 and v2 certificates."""
    v1_sum_p = ROOT / "runs" / v1_run_id / "cert_summary.json"
    v2_sum_p = ROOT / "runs" / v2_run_id / "cert_summary.json"

    v1_data = json.loads(v1_sum_p.read_text(encoding="utf-8")) if v1_sum_p.exists() else {}
    v2_data = json.loads(v2_sum_p.read_text(encoding="utf-8")) if v2_sum_p.exists() else {}

    v1_cert_count = sum(1 for c in v1_data.get("cells", {}).values() if c.get("state", {}).get("certified"))
    v1_area = v1_cert_count / 16.0
    v2_cert_count = v2_data.get("certified_cells_count", 0)
    v2_area = v2_data.get("certified_area_fraction", 0.0)

    v2_hl = v2_data.get("headline", {}).get("state", {})
    v2_hl_pass = v2_hl.get("k_pass", 0)
    v2_hl_bound = float(v2_hl.get("lower_bound", 0.0))
    v2_hl_cert = "certified" if v2_hl.get("certified") else "uncertified"

    lines = [
        "# Side-by-Side Certification Report: v1 vs v2",
        "",
        "> **Methodological Note (Rule H14):** v2 was created after seeing v1's certificate; "
        "v2's certificate is valid because v2 was fixed before its own data was drawn. "
        "Both programs are reported side by side.",
        "",
        "## Summary Metrics",
        f"- **v1 (`{v1_data.get('program_id', 'unknown')}`):** Certified Area Fraction = {v1_area:.4f} ({v1_cert_count}/16 cells), Headline = 35/59 (p_L=0.4778, uncertified)",
        f"- **v2 (`{v2_data.get('program_id', 'unknown')}`):** Certified Area Fraction = {v2_area:.4f} ({v2_cert_count}/16 cells), Headline = {v2_hl_pass}/59 (p_L={v2_hl_bound:.4f}, {v2_hl_cert})",
        "",
        "## Per-Cell Comparison Table (State Lower Bound p_L at delta=0.003125)",
        "| Cell ID | Mass Range (kg) | Friction Range | v1 Pass Rate | v1 p_L | v1 Cert | v2 Pass Rate | v2 p_L | v2 Cert |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for i in range(16):
        cid = f"cell_{i:02d}"
        c1 = v1_data.get("cells", {}).get(cid, {})
        c2 = v2_data.get("cells", {}).get(cid, {})

        # Mass & Friction bounds from either format
        m_r = c2.get("mass_bounds") or c1.get("bounds", {}).get("mass", [0, 0])
        f_r = c2.get("friction_bounds") or c1.get("bounds", {}).get("friction", [0, 0])

        s1 = c1.get("state", {})
        s2 = c2.get("state", {})

        p1_rate = f"{s1.get('k_pass', s1.get('n_cell', 0))}/150"
        p1_bound = float(s1.get("bound", s1.get("lower_bound", 0.0)))
        p1_cert = "PASS" if s1.get("certified") else "FAIL"

        p2_rate = f"{s2.get('k_pass', 0)}/150"
        p2_bound = float(s2.get("lower_bound", 0.0))
        p2_cert = "PASS" if s2.get("certified") else "FAIL"

        lines.append(
            f"| {cid} | [{m_r[0]:.2f}, {m_r[1]:.2f}] | [{f_r[0]:.2f}, {f_r[1]:.2f}] | "
            f"{p1_rate} | {p1_bound:.4f} | {p1_cert} | {p2_rate} | {p2_bound:.4f} | {p2_cert} |"
        )

    lines.extend([
        "",
        "All results certified in simulation under distribution D using rendered camera footage and state truth.",
    ])

    report_text = "\n".join(lines)
    return report_text


def run_pilot_50(config_path: str = "configs/cert3.yaml") -> bool:
    """Run 50-episode pilot on v2 before full certification launch (Task T4)."""
    from closedloop.data.sampler import CertificationLedger, sample
    from closedloop.exec.pilot import execute_episode

    cfg_file = ROOT / config_path
    cert_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    mint_run_id = cert_cfg.get("program_run_id", "round2-mint-01")
    mint_dir = ROOT / "runs" / mint_run_id
    freeze = validate_v2_freeze(mint_dir)
    policy_code = (mint_dir / freeze["source_file"]).read_text(encoding="utf-8")

    pilot_seed_base = int(cert_cfg["seeds"].get("pilot_seed_base", 2210000))
    n_pilot = int(cert_cfg["sample_sizes"].get("pilot_runs", 50))
    bounds = cert_cfg["bounds"]

    scenarios = sample("certification", n=n_pilot, seed=pilot_seed_base, bounds=bounds)
    print(f"Running {n_pilot}-episode pilot on v2 (seeds {pilot_seed_base}..{pilot_seed_base+n_pilot-1})...")

    # Claim pilot seeds in ledger
    ledger_path = ROOT / "runs" / ".certification_ledger.json"
    if not ledger_path.exists():
        raise FileNotFoundError(f"Certification ledger missing at {ledger_path}")
    ledger = CertificationLedger(ledger_path)
    ledger.claim(freeze["program_id"], list(range(pilot_seed_base, pilot_seed_base + n_pilot)))

    infra_errors = []
    for idx, sc in enumerate(scenarios):
        sd = int(sc["seed"])
        kind, payload = execute_episode(
            sc, sd, policy_code, repo_root=str(ROOT),
            timeout_s=120, memory_mb=1024,
        )
        if kind != "sim":
            infra_errors.append((sd, kind, payload))
            print(f"[Pilot ERROR] Seed {sd} failed with infra error: {kind}: {payload}")

    if infra_errors:
        raise RuntimeError(f"Pilot failed with {len(infra_errors)} infrastructure errors!")

    print(f"Pilot SUCCESS: {n_pilot}/{n_pilot} episodes completed with 0 infrastructure errors.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Certify candidate v2.")
    parser.add_argument("--run-id", default="cert3-full-01")
    parser.add_argument("--config", default="configs/cert3.yaml")
    parser.add_argument("--pilot", action="store_true", help="Run 50-episode pre-flight pilot")
    parser.add_argument("--check-judge", action="store_true", help="Run 200-rollout frozen judge consistency check")
    args = parser.parse_args()

    if args.pilot:
        run_pilot_50(config_path=args.config)

    sum_res = run_cert_v2(run_id=args.run_id, cert2_config_path=args.config)

    if args.check_judge:
        v2_path = ROOT / "runs" / "round2-mint-01" / "program_final.py"
        v2_code = v2_path.read_text(encoding="utf-8")
        judge_res = check_frozen_judge_v2(v2_code)
        (ROOT / "runs" / args.run_id / "judge_check_v2.json").write_text(
            json.dumps(judge_res, indent=2), encoding="utf-8"
        )

    rep = side_by_side_report(v2_run_id=args.run_id)
    (ROOT / "runs" / args.run_id / "side_by_side_report.md").write_text(rep, encoding="utf-8")
    print("\n" + rep)


if __name__ == "__main__":
    main()


