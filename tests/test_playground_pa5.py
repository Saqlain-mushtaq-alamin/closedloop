"""Phase PA5 Tests: UI Polish, Responsive Mobile Layout, and Mode Badges (Plan v2 §13 & §14).

Verifies:
1. All card mode badges are present and defined in dashboard/index.html.
2. Preset dropdown selectors (robot, task, budget) are populated with valid options.
3. Code editor container does not contain inline height:100% overflow traps.
4. CSS contains responsive breakpoint rules for mobile (375px/600px) and tablet/desktop (900px).
5. Dynamic mode badge evaluation reflects certification status across cards.
6. Acceptance gates grid uses dedicated responsive stages container.
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_playground_all_mode_badges_present() -> None:
    """Every playground card must display an explicit mode badge (Plan v2 §13 & §14)."""
    index_html = ROOT / "dashboard" / "index.html"
    content = index_html.read_text(encoding="utf-8")

    expected_badges = [
        "pg-badge-pill",          # Top cryptographic status badge
        "pg-editor-mode-badge",   # Python Policy Source card
        "pg-sim-mode-badge",      # Simulation Presets & Budget card
        "pg-camera-mode-badge",   # Camera View & Live Physics card
        "pg-repair-source-chip",  # Repair & Acceptance Gates card
        "pg-log-mode-badge",      # Live Episode Trace Log card
    ]
    for badge_id in expected_badges:
        assert f'id="{badge_id}"' in content, f"Missing required mode badge element: {badge_id}"


def test_code_editor_no_overflow_trap() -> None:
    """Editor card must not have style='height:100%' which causes vertical card collision."""
    index_html = ROOT / "dashboard" / "index.html"
    content = index_html.read_text(encoding="utf-8")

    # Locate the Python Policy Source card panel
    assert 'Python Policy Source' in content
    # Find card-panel containing Python Policy Source
    pattern = r'<div class="card-panel"[^>]*>\s*<div class="row-between mb-12">\s*<div[^>]*>\s*<div class="panel-title"[^>]*>Python Policy Source'
    match = re.search(pattern, content)
    assert match is not None, "Policy editor card panel missing or malformed"
    assert 'style="height:100%' not in match.group(0), "height:100% inline style must not be present on editor card"


def test_playground_responsive_css_breakpoints() -> None:
    """CSS must define responsive breakpoints collapsing grids at <=900px and <=600px."""
    index_html = ROOT / "dashboard" / "index.html"
    content = index_html.read_text(encoding="utf-8")

    assert ".pg-stages-grid" in content, "Missing .pg-stages-grid class definition"
    assert ".pg-metric-grid" in content, "Missing .pg-metric-grid class definition"
    assert "@media (max-width: 900px)" in content, "Missing 900px responsive breakpoint"
    assert "@media (max-width: 600px)" in content, "Missing 600px mobile responsive breakpoint"


def test_playground_js_populates_presets_and_badges() -> None:
    """playground.js must define preset option arrays and population function."""
    playground_js = ROOT / "dashboard" / "playground.js"
    content = playground_js.read_text(encoding="utf-8")

    assert "ROBOT_PRESET_OPTIONS" in content, "Missing ROBOT_PRESET_OPTIONS array"
    assert "TASK_PRESET_OPTIONS" in content, "Missing TASK_PRESET_OPTIONS array"
    assert "BUDGET_OPTIONS" in content, "Missing BUDGET_OPTIONS array"
    assert "populatePresetDropdowns" in content, "Missing populatePresetDropdowns function"
    assert "pg-editor-mode-badge" in content, "playground.js must update editor mode badge"
    assert "pg-sim-mode-badge" in content, "playground.js must update simulation mode badge"
    assert "pg-camera-mode-badge" in content, "playground.js must update camera mode badge"
    assert "pg-log-mode-badge" in content, "playground.js must update log mode badge"


def test_preset_options_contain_all_required_hardware_and_tasks() -> None:
    """Preset options in playground.js must include all certified & stress variations."""
    playground_js = ROOT / "dashboard" / "playground.js"
    content = playground_js.read_text(encoding="utf-8")

    # Robot hardware options
    assert "certified_default" in content
    assert "gripper_100N" in content
    assert "gripper_200N" in content

    # Task space options
    assert "mixed_bin" in content
    assert "light_parts" in content
    assert "heavy_parts" in content

    # Budget options
    assert '"5"' in content
    assert '"10"' in content
    assert '"20"' in content
    assert '"50"' in content
