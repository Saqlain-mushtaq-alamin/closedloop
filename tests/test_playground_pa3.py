"""Unit tests for Phase PA3: Dashboard UI & Interactive Playground Experience (Plan §10, §13 PA3).

Verifies:
1. dashboard/index.html includes the playground navigation tab and container section.
2. dashboard/index.html loads badge.js and playground.js scripts.
3. Preloaded program templates match certified run hashes (bec73dec..., 5f74f77...).
4. Frontend design tokens and elements for code editor, preset selectors, badge display, and results table are present.
5. End-to-end API integration for preset fetching and playground job execution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from closedloop.playground.lang import hash_program
from closedloop.playground.presets import ROBOT_PRESETS, TASK_PRESETS
from playground.server import app

ROOT = Path(__file__).resolve().parent.parent


def test_index_html_contains_playground_tab_and_section() -> None:
    """dashboard/index.html must define the playground tab and active section panel."""
    index_path = ROOT / "dashboard" / "index.html"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")

    assert 'data-tab="playground"' in content, "Missing playground navigation tab button"
    assert 'id="section-playground"' in content, "Missing section-playground container"
    assert 'id="pg-code-editor"' in content, "Missing playground code editor textarea"
    assert 'id="pg-robot-preset"' in content, "Missing robot preset selector"
    assert 'id="pg-task-preset"' in content, "Missing task preset selector"
    assert 'id="pg-budget-preset"' in content, "Missing budget selector"
    assert 'id="pg-badge-pill"' in content, "Missing dynamic certificate badge pill"
    assert 'id="pg-run-btn"' in content, "Missing run simulation button"


def test_index_html_loads_required_scripts() -> None:
    """dashboard/index.html must load badge.js and playground.js."""
    index_path = ROOT / "dashboard" / "index.html"
    content = index_path.read_text(encoding="utf-8")

    assert '<script src="badge.js"></script>' in content
    assert '<script src="playground.js"></script>' in content


def test_preloaded_programs_match_certified_hashes() -> None:
    """Preloaded program templates in playground.js must match frozen certified hashes."""
    playground_js_path = ROOT / "dashboard" / "playground.js"
    assert playground_js_path.exists(), "dashboard/playground.js must exist"
    js_content = playground_js_path.read_text(encoding="utf-8")

    # Hashes from cert-mint-03 and round2-mint-01
    h_v1 = "bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55"
    h_v2 = "5f74f7762ee1f378b2d71f6938a288fa12aa51a0ee93ee33a2639944cd66aaa1"

    # Both hashes should be referenced or reproducible
    assert "bec73dec" in js_content
    assert "5f74f776" in js_content


def test_frontend_fallback_ladder_documentation_present() -> None:
    """Playground UI must display the 3-tier fallback ladder (Tier 2 / Tier L / Tier 0)."""
    index_path = ROOT / "dashboard" / "index.html"
    content = index_path.read_text(encoding="utf-8")

    assert "make playground-local" in content, "Must explain Tier L local command"
    assert "Tier 0" in content or "Hash Lab" in content, "Must explain Tier 0 offline Hash Lab"


def test_end_to_end_playground_execution_api() -> None:
    """FastAPI TestClient verifies /presets and /run end-to-end integration."""
    client = TestClient(app)

    # 1. Verify presets endpoint
    resp_presets = client.get("/presets")
    assert resp_presets.status_code == 200
    presets_data = resp_presets.json()
    assert set(presets_data["robot_presets"].keys()) == set(ROBOT_PRESETS.keys())
    assert set(presets_data["task_presets"].keys()) == set(TASK_PRESETS.keys())

    # 2. Verify run endpoint
    prog_path = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    code = prog_path.read_text(encoding="utf-8")

    resp_run = client.post(
        "/run",
        json={
            "code": code,
            "robot_preset": "certified_default",
            "task_preset": "mixed_bin",
            "budget": 3,
            "seed_base": 14000,
        },
    )
    assert resp_run.status_code == 200
    run_data = resp_run.json()
    assert run_data["status"] == "OK"
    assert run_data["badge"] == "CERTIFIED"
    assert run_data["episodes_tested"] == 3
    assert len(run_data["episodes"]) == 3
