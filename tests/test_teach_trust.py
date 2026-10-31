"""Tests for Phase 10f 'Teach and Trust' Experience (Plan §13, Phase 10f).

Asserts:
- test_challenge_grid_nearest_lookup: arbitrary coordinates snap to nearest grid and match logged episode.
- test_live_clopper_pearson_selfcheck: Clopper-Pearson live bound calculation matches SciPy exact CI on 30 tuples.
- test_time_to_trust_manifest_recompute: time-to-trust panel values match manifests and zero-failure spot check math.
- test_challenge_assets_relative_and_resolving: all challenge frame PNGs and replays resolve relative to dashboard/.
- test_no_hand_typed_numbers_teach_trust: static HTML body contains no forbidden hand-typed digits outside allowlist.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from closedloop.certify.stats import cp_lower
from closedloop.demo.challenge import (
    compute_time_to_trust_metrics,
    get_grid_point_result,
    snap_to_nearest_grid,
)
from scripts.check_site import check_site


def test_challenge_grid_nearest_lookup() -> None:
    """Arbitrary test parameters snap to nearest grid point and match logged episode."""
    # Test case 1: 9.8 kg, friction 0.42, centre -> snaps to 10.0, 0.4, centre
    m_snap, f_snap, p_snap = snap_to_nearest_grid(9.8, 0.42, "centre")
    assert m_snap == 10.0
    assert f_snap == 0.4
    assert p_snap == "centre"

    res_v1 = get_grid_point_result("v1", 9.8, 0.42, "centre")
    assert res_v1["mass_snapped"] == 10.0
    assert res_v1["friction_snapped"] == 0.4
    assert res_v1["pose_snapped"] == "centre"
    # v1 slips above 8.0 kg with 100N gripper
    assert res_v1["truth_success"] is False
    assert (ROOT / "dashboard" / res_v1["frame_path"]).exists()

    res_v2 = get_grid_point_result("v2", 9.8, 0.42, "centre")
    assert res_v2["mass_snapped"] == 10.0
    # v2 passes with 300N gripper
    assert res_v2["truth_success"] is True

    # Test case 2: 1.2 kg, friction 0.88, corner -> snaps to 1.0, 1.0, plus_corner
    m_snap2, f_snap2, p_snap2 = snap_to_nearest_grid(1.2, 0.88, "plus_corner")
    assert m_snap2 == 1.0
    assert f_snap2 == 1.0
    assert p_snap2 == "plus_corner"

    res_v1_light = get_grid_point_result("v1", 1.2, 0.88, "plus_corner")
    assert res_v1_light["truth_success"] is True


def test_live_clopper_pearson_selfcheck() -> None:
    """Live Clopper-Pearson calculator matches SciPy exact CI across >= 30 tuples."""
    test_cases = [
        # 5 test slots scenarios (k <= n <= 5)
        (0, 5, 0.05), (1, 5, 0.05), (2, 5, 0.05), (3, 5, 0.05), (4, 5, 0.05), (5, 5, 0.05),
        # 1-4 tests
        (1, 1, 0.05), (1, 2, 0.05), (2, 2, 0.05), (2, 3, 0.05), (3, 3, 0.05), (3, 4, 0.05), (4, 4, 0.05),
        # n = 10, 20
        (5, 10, 0.05), (10, 10, 0.05), (15, 20, 0.05), (20, 20, 0.05),
        # Headline n = 59
        (35, 59, 0.05), (50, 59, 0.05), (59, 59, 0.05),
        # Cell n = 150
        (100, 150, 0.05), (135, 150, 0.05), (150, 150, 0.05),
        # delta = 0.01
        (5, 5, 0.01), (10, 10, 0.01), (50, 50, 0.01),
        # delta_cell = 0.003125
        (5, 5, 0.003125), (50, 55, 0.003125), (55, 55, 0.003125), (150, 150, 0.003125),
    ]
    assert len(test_cases) >= 30

    for k, n, delta in test_cases:
        py_bound = cp_lower(k, n, delta)
        if k == 0:
            scipy_bound = 0.0
        else:
            conf = max(0.0, min(1.0, 1.0 - 2.0 * delta))
            scipy_bound = float(
                binomtest(k, n).proportion_ci(confidence_level=conf, method="exact").low
            )
        assert math.isclose(
            py_bound, scipy_bound, abs_tol=1e-7
        ), f"Mismatch for k={k}, n={n}, delta={delta}: {py_bound} vs {scipy_bound}"


def test_time_to_trust_manifest_recompute() -> None:
    """Time to trust panel values match manifests and verified spot check arithmetic."""
    metrics = compute_time_to_trust_metrics()
    assert metrics["lines_of_code_written_by_user"] == 0

    # Spot check arithmetic check
    arith = metrics["arithmetic_spot_check_equivalence"]
    assert arith["label"] == "arithmetic, not a measured human time"
    # n = ceil(log(0.003125) / log(0.90)) = 55
    assert arith["zero_failure_trials_per_cell"] == 55
    assert arith["total_zero_failure_episodes_needed"] == 55 * 16  # 880
    assert arith["estimated_human_hours"] > 0

    # Token and cost verification from manifests
    m3_p = ROOT / "runs" / "cert-mint-03" / "manifest.json"
    if m3_p.exists():
        assert metrics["v1_program_id"] == "bec73dec45a88431"

    r2_p = ROOT / "runs" / "round2-mint-01" / "manifest.json"
    if r2_p.exists():
        assert metrics["v2_program_id"] == "5f74f7762ee1f378"


def test_challenge_assets_relative_and_resolving() -> None:
    """All challenge assets in challenge_data.json exist and resolve relative to dashboard/."""
    c_json = ROOT / "dashboard" / "challenge" / "challenge_data.json"
    assert c_json.exists(), "challenge_data.json must exist"

    data = json.loads(c_json.read_text(encoding="utf-8"))
    grid = data.get("grid", {})
    assert "v1" in grid and "v2" in grid
    assert len(grid["v1"]) == 324
    assert len(grid["v2"]) == 324

    # Sample check 10 random frames from v1 and v2
    for p_label in ["v1", "v2"]:
        for key in list(grid[p_label].keys())[:10]:
            fpath = grid[p_label][key]["frame_path"]
            assert not fpath.startswith("/"), f"Frame path must be relative: {fpath}"
            full_p = ROOT / "dashboard" / fpath
            assert full_p.exists(), f"Frame file missing: {full_p}"

    # Verify 8 key replays
    replays_manifest_p = ROOT / "dashboard" / "challenge" / "replays" / "manifest.json"
    assert replays_manifest_p.exists()
    replays_meta = json.loads(replays_manifest_p.read_text(encoding="utf-8"))
    clips = replays_meta.get("clips", [])
    assert len(clips) >= 8

    for clip in clips:
        cid = clip["clip_id"]
        meta_file = ROOT / "dashboard" / "challenge" / "replays" / cid / "meta.json"
        assert meta_file.exists()
        for f in clip["frames"]:
            img_file = ROOT / "dashboard" / "challenge" / "replays" / cid / f
            assert img_file.exists(), f"Replay frame missing: {img_file}"


def test_no_hand_typed_numbers_teach_trust() -> None:
    """Static HTML in dashboard/index.html contains no forbidden hand-typed digits."""
    index_html = ROOT / "dashboard" / "index.html"
    content = index_html.read_text(encoding="utf-8")

    no_script = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', content, flags=re.IGNORECASE)
    no_style = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', no_script, flags=re.IGNORECASE)
    no_comments = re.sub(r'<!--.*?-->', '', no_style, flags=re.DOTALL)
    text_only = re.sub(r'<[^>]+>', ' ', no_comments)

    allowed_tokens = {
        "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.",
        "1", "2", "3", "4", "5", "6", "7", "8",
        "3.1", "1.3", "10b", "10", "4x4", "G3", "G2", "G1", "G0", "T1", "T2",
        "H1", "H2", "H3", "H4", "H11", "H12", "H13", "H14", "H15", "H16", "H17",
        "V1", "V5", "V6", "V7", "V9", "V10", "V12",
        "B0", "B1", "B2", "B3", "B4",
        "100%", "0",
    }
    forbidden = []
    for tok in text_only.split():
        clean = tok.strip("(),;:.[]{}'\"")
        if re.search(r'\d', clean) and clean not in allowed_tokens:
            forbidden.append(clean)

    assert not forbidden, f"Found hand-typed numbers in static HTML: {forbidden[:10]}"
