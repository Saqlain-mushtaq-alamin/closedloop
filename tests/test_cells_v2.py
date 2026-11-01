"""Tests for P-1: fix cells_v2 export in dashboard/data.json (Plan v2, §3).

Asserts:
- No cells_v2 entry has a zero mass or friction range.
- Every bound_state equals the stats function cp_lower(k, n, delta) where delta = 0.05 / 16.
- certified_state is consistent with bound_state >= target_p (0.90).
- Data generation determinism: running generator produces byte-identical output.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from closedloop.certify.stats import cp_lower
from closedloop.report.build_ui_data import build_ui_data

ROOT = Path(__file__).resolve().parent.parent


def test_cells_v2_nonzero_ranges() -> None:
    """Section 3: No cells_v2 entry has a zero range."""
    data_path = ROOT / "dashboard" / "data.json"
    assert data_path.exists(), "dashboard/data.json must exist"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    assert "cells_v2" in data, "cells_v2 must exist in data.json"
    cells_v2 = data["cells_v2"]
    assert len(cells_v2) == 16, f"Expected 16 cells in cells_v2, got {len(cells_v2)}"

    for cell in cells_v2:
        cid = cell.get("id")
        m_range = cell.get("mass_range")
        f_range = cell.get("friction_range")

        assert m_range is not None and len(m_range) == 2, f"{cid} missing mass_range"
        assert f_range is not None and len(f_range) == 2, f"{cid} missing friction_range"

        assert m_range[1] > m_range[0], f"{cid} mass range has zero or negative span: {m_range}"
        assert f_range[1] > f_range[0], f"{cid} friction range has zero or negative span: {f_range}"
        assert m_range != [0.0, 0.0], f"{cid} mass range is [0.0, 0.0]"
        assert f_range != [0.0, 0.0], f"{cid} friction range is [0.0, 0.0]"


def test_cells_v2_bound_state_matches_stats() -> None:
    """Section 3: Every bound_state equals cp_lower(k, n, delta)."""
    data_path = ROOT / "dashboard" / "data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    cells_v2 = data["cells_v2"]
    delta_cell = 0.05 / 16  # 0.003125 per-cell budget

    for cell in cells_v2:
        cid = cell.get("id")
        k = cell.get("k_state")
        n = cell.get("n")
        bound = cell.get("bound_state")

        assert k is not None and n is not None and bound is not None
        expected_bound = round(cp_lower(k, n, delta_cell), 4)
        assert math.isclose(bound, expected_bound, abs_tol=1e-4), (
            f"{cid}: bound_state {bound} != expected {expected_bound} from cp_lower({k}, {n}, {delta_cell})"
        )


def test_cells_v2_certified_state_consistency() -> None:
    """Section 3: certified_state is consistent with bound_state >= target_p (0.90)."""
    data_path = ROOT / "dashboard" / "data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    cells_v2 = data["cells_v2"]
    target_p = 0.90

    for cell in cells_v2:
        cid = cell.get("id")
        bound = cell.get("bound_state", 0.0)
        certified = cell.get("certified_state")
        expected_certified = bound >= target_p
        assert certified == expected_certified, (
            f"{cid}: certified_state={certified} is inconsistent with bound_state={bound} >= {target_p}"
        )


def test_build_ui_data_determinism(tmp_path: Path) -> None:
    """Section 3: build_ui_data twice gives byte-identical output."""
    js1 = tmp_path / "data1.js"
    json1 = tmp_path / "data1.json"
    js2 = tmp_path / "data2.js"
    json2 = tmp_path / "data2.json"

    build_ui_data(output_js=js1, output_json=json1)
    build_ui_data(output_js=js2, output_json=json2)

    assert js1.read_bytes() == js2.read_bytes(), "data.js output is not byte-identical across runs"
    assert json1.read_bytes() == json2.read_bytes(), "data.json output is not byte-identical across runs"
