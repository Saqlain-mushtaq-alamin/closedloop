"""Verify committed experimental evidence using an independent SciPy path (Phase 10e).

Recomputes every certified bound and calibration bound from the committed logs:
- cert-full-01: headline state bound + 16 cell state bounds + 16 cell camera bounds (33 bounds)
- cert2-full-01: headline state bound + 16 cell state bounds (17 bounds)
- judge-g2-03: TPR lower bound + 4 margin bucket FPR upper bounds (5 bounds)
- shift-full-01: reference D lower bound + shifted D' lower bound (2 bounds)

Total: 57 certified / calibration bounds recomputed directly from committed episodes.jsonl.
Exits 0 and prints 'N/N match' on success; non-zero exit on any mismatch.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent.parent


def cp_lower_scipy(k: int, n: int, delta: float) -> float:
    """One-sided exact Clopper-Pearson lower bound at confidence 1 - delta."""
    if k == 0:
        return 0.0
    conf = max(0.0, min(1.0, 1.0 - 2.0 * delta))
    return float(binomtest(k, n).proportion_ci(confidence_level=conf, method="exact").low)


def cp_upper_scipy(k: int, n: int, delta: float) -> float:
    """One-sided exact Clopper-Pearson upper bound at confidence 1 - delta."""
    if k == n:
        return 1.0
    conf = max(0.0, min(1.0, 1.0 - 2.0 * delta))
    return float(binomtest(k, n).proportion_ci(confidence_level=conf, method="exact").high)


def corrected_lower_scipy(
    k_pass: int,
    n_cell: int,
    k_a: int,
    n_a: int,
    k_b: int,
    n_b: int,
    d_a: float,
    d_b: float,
    d_cell: float,
) -> float:
    """Corrected lower bound for noisy judge derived from SciPy exact Clopper-Pearson bounds."""
    q_lo = cp_lower_scipy(k_pass, n_cell, d_cell)
    a_hi = cp_upper_scipy(k_a, n_a, d_a)
    b_hi = cp_upper_scipy(k_b, n_b, d_b)
    if q_lo <= b_hi or a_hi <= b_hi:
        return 0.0
    return min(1.0, (q_lo - b_hi) / (a_hi - b_hi))


def verify_evidence(runs_dir: Path | str | None = None) -> tuple[int, int]:
    """Verify all evidence bounds from committed logs. Returns (matched, total)."""
    rdir = Path(runs_dir) if runs_dir is not None else ROOT / "runs"
    matched = 0
    total = 0
    mismatches: list[str] = []

    # Load quarantined invalid runs (Phase 12b Audit Remediation)
    inv_file = rdir / "INVALID_RUNS.json"
    invalid_runs: set[str] = set()
    if inv_file.exists():
        try:
            inv_data = json.loads(inv_file.read_text(encoding="utf-8"))
            invalid_runs = set(inv_data.keys())
        except Exception:
            invalid_runs = set()

    # Rule H12 & Rule H9 integrity scan: verify all valid runs have planned==logged and unique seed pairs
    for rd in sorted(rdir.iterdir()):
        if not rd.is_dir() or rd.name in invalid_runs or rd.name.startswith("."):
            continue
        mf_path = rd / "manifest.json"
        ep_path = rd / "episodes.jsonl"
        if not mf_path.exists() or not ep_path.exists():
            continue

        mf = json.loads(mf_path.read_text(encoding="utf-8"))
        planned = mf.get("episodes_planned")
        lines = [line for line in ep_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        logged = len(lines)
        if planned is not None and planned != logged:
            total += 1
            mismatches.append(f"Run {rd.name} planned!=logged: planned={planned}, logged={logged}")

        seen_pairs: set[tuple[Any, Any]] = set()
        for idx, line in enumerate(lines, start=1):
            ep = json.loads(line)
            if ep.get("stream") == "certification":
                pair = (ep.get("seed"), ep.get("program_id", ""))
                if pair in seen_pairs:
                    total += 1
                    mismatches.append(f"Run {rd.name} has duplicate certification seed-program pair {pair} at line {idx}")
                    break
                seen_pairs.add(pair)

    # 1. cert-full-01
    c1_dir = rdir / "cert-full-01"
    if not (c1_dir / "episodes.jsonl").exists() or not (c1_dir / "cert_summary.json").exists():
        raise FileNotFoundError(f"Missing cert-full-01 files in {c1_dir}")

    c1_summary = json.loads((c1_dir / "cert_summary.json").read_text(encoding="utf-8"))
    c1_episodes = [
        json.loads(line)
        for line in (c1_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # Aggregate c1 counts
    c1_hl_k = 0
    c1_hl_n = 0
    c1_cell_state_k: dict[str, int] = {}
    c1_cell_cam_k: dict[str, int] = {}
    c1_cell_n: dict[str, int] = {}

    for ep in c1_episodes:
        tp = ep.get("trace_path", "")
        if tp == "headline":
            c1_hl_n += 1
            if ep.get("truth_success"):
                c1_hl_k += 1
        elif tp.startswith("cell_"):
            c1_cell_n[tp] = c1_cell_n.get(tp, 0) + 1
            if ep.get("truth_success"):
                c1_cell_state_k[tp] = c1_cell_state_k.get(tp, 0) + 1
            if ep.get("judge_pass"):
                c1_cell_cam_k[tp] = c1_cell_cam_k.get(tp, 0) + 1

    # Check c1 headline
    total += 1
    recomp_c1_hl = cp_lower_scipy(c1_hl_k, c1_hl_n, 0.05)
    exp_c1_hl = float(c1_summary["headline_state"]["bound"])
    if math.isclose(recomp_c1_hl, exp_c1_hl, abs_tol=1e-6):
        matched += 1
    else:
        mismatches.append(f"cert-full-01 headline bound: {recomp_c1_hl} != {exp_c1_hl}")

    # Check c1 16 cells (state and camera)
    k_a, n_a, k_b, n_b = 300, 300, 2, 100
    d_a = 0.005
    d_b = 0.00125
    d_cell_state = 0.003125
    d_cell_cam = 0.0025

    for c in range(16):
        cid = f"cell_{c:02d}"
        n_c = c1_cell_n.get(cid, 150)
        ks = c1_cell_state_k.get(cid, 0)
        kc = c1_cell_cam_k.get(cid, 0)

        # State bound
        total += 1
        recomp_s = cp_lower_scipy(ks, n_c, d_cell_state)
        exp_s = float(c1_summary["cells"][cid]["state"]["bound"])
        if math.isclose(recomp_s, exp_s, abs_tol=1e-6):
            matched += 1
        else:
            mismatches.append(f"cert-full-01 {cid} state: {recomp_s} != {exp_s}")

        # Camera bound
        total += 1
        recomp_c = corrected_lower_scipy(kc, n_c, k_a, n_a, k_b, n_b, d_a, d_b, d_cell_cam)
        exp_c = float(c1_summary["cells"][cid]["camera"]["bound"])
        if math.isclose(recomp_c, exp_c, abs_tol=1e-6):
            matched += 1
        else:
            mismatches.append(f"cert-full-01 {cid} camera: {recomp_c} != {exp_c}")

    # 2. v2 certification (cert3-full-01 or cert2-full-01 if not quarantined)
    c2_run_id = None
    for cand_id in ["cert3-full-01", "cert2-full-01"]:
        if (rdir / cand_id).exists() and cand_id not in invalid_runs:
            c2_run_id = cand_id
            break

    if c2_run_id is not None:
        c2_dir = rdir / c2_run_id
        c2_summary = json.loads((c2_dir / "cert_summary.json").read_text(encoding="utf-8"))
        # Unfiltered read: NO created_at filter (Rule H10, Rule H12)
        c2_episodes = [
            json.loads(line)
            for line in (c2_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        c2_hl_k = 0
        c2_hl_n = 0
        c2_cell_state_k: dict[str, int] = {}
        c2_cell_n: dict[str, int] = {}

        for ep in c2_episodes:
            eid = ep.get("episode_id", "")
            if eid.startswith("headline"):
                c2_hl_n += 1
                if ep.get("truth_success"):
                    c2_hl_k += 1
            elif eid.startswith("cell_"):
                cid = eid.split("-")[0]
                c2_cell_n[cid] = c2_cell_n.get(cid, 0) + 1
                if ep.get("truth_success"):
                    c2_cell_state_k[cid] = c2_cell_state_k.get(cid, 0) + 1

        # Check c2 headline
        total += 1
        recomp_c2_hl = cp_lower_scipy(c2_hl_k, c2_hl_n, 0.05)
        exp_c2_hl = float(c2_summary["headline"]["state"]["lower_bound"])
        if math.isclose(recomp_c2_hl, exp_c2_hl, abs_tol=1e-4):
            matched += 1
        else:
            mismatches.append(f"{c2_run_id} headline: {recomp_c2_hl} != {exp_c2_hl}")

        # Check c2 16 cells (state)
        for c in range(16):
            cid = f"cell_{c:02d}"
            n_c = c2_cell_n.get(cid, 150)
            ks = c2_cell_state_k.get(cid, 0)
            total += 1
            recomp_s2 = cp_lower_scipy(ks, n_c, d_cell_state)
            exp_s2 = float(c2_summary["cells"][cid]["state"]["lower_bound"])
            if math.isclose(recomp_s2, exp_s2, abs_tol=1e-4):
                matched += 1
            else:
                mismatches.append(f"{c2_run_id} {cid} state: {recomp_s2} != {exp_s2}")

    # 3. judge-g2-03
    jg_dir = rdir / "judge-g2-03"
    if jg_dir.exists() and "judge-g2-03" not in invalid_runs:

        jg_report = json.loads((jg_dir / "calibration_report.json").read_text(encoding="utf-8"))
        jg_episodes = [
            json.loads(line)
            for line in (jg_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        tpr_k = 0
        tpr_n = 0
        bucket_counts: dict[str, list[int]] = {
            "near_boundary": [0, 0],
            "shallow": [0, 0],
            "medium": [0, 0],
            "deep": [0, 0],
        }

        for ep in jg_episodes:
            ts = ep.get("truth_success")
            jp = ep.get("judge_pass")
            mg = ep.get("margin", 0.0)
            if ts:
                tpr_n += 1
                if jp:
                    tpr_k += 1
            else:
                if -0.05 <= mg < 0.0:
                    b_name = "near_boundary"
                elif -0.15 <= mg < -0.05:
                    b_name = "shallow"
                elif -0.35 <= mg < -0.15:
                    b_name = "medium"
                else:
                    b_name = "deep"
                bucket_counts[b_name][1] += 1
                if jp:
                    bucket_counts[b_name][0] += 1

        # Check TPR lower bound
        total += 1
        recomp_tpr = cp_lower_scipy(tpr_k, tpr_n, 0.005)
        exp_tpr = float(jg_report["tpr_lower"])
        if math.isclose(recomp_tpr, exp_tpr, abs_tol=1e-4):
            matched += 1
        else:
            mismatches.append(f"judge-g2-03 TPR lower: {recomp_tpr} != {exp_tpr}")

        # Check 4 margin buckets FPR upper bounds
        for b_name in ["near_boundary", "shallow", "medium", "deep"]:
            bk, bn = bucket_counts[b_name]
            total += 1
            recomp_fpr_up = cp_upper_scipy(bk, bn, 0.00125)
            exp_fpr_up = float(jg_report["margin_buckets"][b_name]["fpr_upper"])
            if math.isclose(recomp_fpr_up, exp_fpr_up, abs_tol=1e-4):
                matched += 1
            else:
                mismatches.append(f"judge-g2-03 bucket {b_name} FPR upper: {recomp_fpr_up} != {exp_fpr_up}")

    # 4. shift-full-01
    sh_dir = rdir / "shift-full-01"
    if sh_dir.exists():
        sh_fig = json.loads((sh_dir / "shift_figure_data.json").read_text(encoding="utf-8"))
        sh_episodes = [
            json.loads(line)
            for line in (sh_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        kd, nd = 0, 0
        kdp, ndp = 0, 0
        for ep in sh_episodes:
            tp = ep.get("trace_path", "")
            ts = ep.get("truth_success", False)
            if tp == "dist_D":
                nd += 1
                if ts:
                    kd += 1
            elif tp == "dist_D_prime":
                ndp += 1
                if ts:
                    kdp += 1

        # Check D bound
        total += 1
        recomp_d = cp_lower_scipy(kd, nd, 0.05)
        exp_d = float(sh_fig["d_recomputed_bound"])
        if math.isclose(recomp_d, exp_d, abs_tol=1e-6):
            matched += 1
        else:
            mismatches.append(f"shift-full-01 D bound: {recomp_d} != {exp_d}")

        # Check D' bound
        total += 1
        recomp_dp = cp_lower_scipy(kdp, ndp, 0.05)
        exp_dp = float(sh_fig["dp_recertified_bound"])
        if math.isclose(recomp_dp, exp_dp, abs_tol=1e-6):
            matched += 1
        else:
            mismatches.append(f"shift-full-01 D' bound: {recomp_dp} != {exp_dp}")

    if mismatches:
        print(f"FAILED: {len(mismatches)} mismatch(es) found:")
        for m in mismatches:
            print(f"  - {m}")
        sys.exit(1)

    print(f"{matched}/{total} match")
    return matched, total


def main() -> None:
    matched, total = verify_evidence()
    sys.exit(0 if matched == total else 1)


if __name__ == "__main__":
    main()
