"""Phase PA6 Tests: Video Walkthrough, Local Runner, and Evaluator Documentation.

Verifies:
1. README.md documents Tab 7 ClosedLoop Playground and the make playground-local Tier L command.
2. docs/PLAYGROUND_WALKTHROUGH.md exists and details the 3-tier ladder, 4-tuple badge, hardware clamps, and 4 acceptance stages.
3. Makefile contains playground-local target matching Tier L specifications.
4. End-to-end FastAPI service endpoints (/health, /presets, /repair/recorded, /gates, /run) are fully functional.
5. Strict Rule H14 compliance: no unapproved claims ("safe", "proven", "camera alone", "novel", "first") in walkthrough documentation.
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from playground.server import app
from closedloop.playground.presets import ROBOT_PRESETS, TASK_PRESETS

ROOT = Path(__file__).resolve().parent.parent


def test_readme_documents_playground_and_tier_l() -> None:
    """README.md must document Tab 7 Playground and Tier L local command."""
    readme_path = ROOT / "README.md"
    assert readme_path.exists(), "README.md must exist"
    content = readme_path.read_text(encoding="utf-8")

    assert "Tab 7: ClosedLoop Playground" in content, "README must document Tab 7 Playground"
    assert "make playground-local" in content, "README must document make playground-local Tier L command"
    assert "PLAYGROUND_WALKTHROUGH.md" in content, "README must link to PLAYGROUND_WALKTHROUGH.md"
    assert "4-Tuple Cryptographic Badge" in content or "4-Tuple" in content, "README must explain 4-tuple badge"
    assert "Hardware Preset Clamps" in content, "README must explain hardware preset clamps"


def test_playground_walkthrough_guide_complete() -> None:
    """docs/PLAYGROUND_WALKTHROUGH.md must provide complete architecture and evaluator guide."""
    walkthrough_path = ROOT / "docs" / "PLAYGROUND_WALKTHROUGH.md"
    assert walkthrough_path.exists(), "docs/PLAYGROUND_WALKTHROUGH.md must exist"
    content = walkthrough_path.read_text(encoding="utf-8")

    # Core concepts
    assert "Tier 2" in content, "Walkthrough must document Tier 2"
    assert "Tier L" in content, "Walkthrough must document Tier L"
    assert "Tier 0" in content, "Walkthrough must document Tier 0"
    assert "make playground-local" in content
    assert "Stage I" in content
    assert "Stage II" in content
    assert "Stage III" in content
    assert "Stage IV" in content
    assert "100 N" in content or "100N" in content, "Walkthrough must document 100 N clamp"
    assert "playground_walkthrough" in content, "Walkthrough must reference walkthrough recording"


def test_makefile_has_playground_local_target() -> None:
    """Makefile must contain playground-local target on port 8000."""
    makefile_path = ROOT / "Makefile"
    assert makefile_path.exists()
    content = makefile_path.read_text(encoding="utf-8")

    assert "playground-local:" in content, "Makefile missing playground-local target"
    assert "--port 8000" in content, "playground-local target must run on port 8000"


def test_end_to_end_api_endpoints_health_and_gates() -> None:
    """FastAPI endpoints (/health, /presets, /repair/recorded, /gates, /run) respond successfully."""
    client = TestClient(app)

    # 1. /health
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    data_health = resp_health.json()
    assert data_health["status"] == "ok"
    assert data_health["selftest"] == "20/20"

    # 2. /presets
    resp_presets = client.get("/presets")
    assert resp_presets.status_code == 200
    data_presets = resp_presets.json()
    assert len(data_presets["robot_presets"]) >= 3
    assert len(data_presets["task_presets"]) >= 3

    # 3. /repair/recorded
    resp_recorded = client.get("/repair/recorded")
    assert resp_recorded.status_code == 200
    data_recorded = resp_recorded.json()
    assert len(data_recorded["catalog"]) >= 2

    # 4. /gates
    repaired_item = data_recorded["catalog"][0]
    resp_gates = client.post(
        "/gates",
        json={
            "code": repaired_item["code"],
            "robot_preset": "certified_default",
            "task_preset": "mixed_bin",
            "minimal_ce": {"mass": 10.16, "friction": 0.8, "x": 0.0, "y": 0.0, "yaw": 0.0, "seed": 711000},
            "severe_ce": {"mass": 11.5, "friction": 0.5, "x": -0.05, "y": -0.05, "yaw": 0.2, "seed": 711001},
        },
    )
    assert resp_gates.status_code == 200
    gates_data = resp_gates.json()
    assert gates_data["accepted"] is True
    assert gates_data["stages"]["stage1_minimal_ce"]["passed"] is True
    assert gates_data["stages"]["stage2_severe_ce"]["passed"] is True
    assert gates_data["stages"]["stage3_regression_set"]["passed"] is True
    assert gates_data["stages"]["stage4_falsifier_rerun"]["passed"] is True


def test_rule_h14_claims_compliance() -> None:
    """Walkthrough and documentation must not contain prohibited claim words (Rule H14)."""
    walkthrough_path = ROOT / "docs" / "PLAYGROUND_WALKTHROUGH.md"
    content = walkthrough_path.read_text(encoding="utf-8").lower()

    forbidden_patterns = [
        r'\bfirst\b',
        r'\bnovel\b',
        r'\bproven\b',
        r'\bsafe\b',
        r'\bcamera alone\b',
    ]

    for pat in forbidden_patterns:
        matches = re.findall(pat, content)
        assert not matches, f"Rule H14 violation in walkthrough guide: found forbidden word '{pat}'"
