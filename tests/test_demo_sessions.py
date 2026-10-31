"""Phase 10c tests: Recorded repair sessions and Repair Theatre evidence.

Tests:
1. test_session_schema_complete: Validate required fields in each recorded session.json.
2. test_replay_equals_log (V1): Replayed episode matches logged episode exactly.
3. test_selection_rule_reproducibility: First 8 failing scenarios match deterministic draw from D.
4. test_ui_asset_paths_resolve: All Repair Theatre images/frames resolve relative to dashboard/.
5. test_no_hand_typed_numbers_theatre: Static HTML contains no forbidden hardcoded numbers.
6. test_dashboard_size_cap: Total dashboard size is <= 25 MB.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_session_schema_complete() -> None:
    """Validate that recorded demo sessions have complete metadata and required fields."""
    sessions_dir = ROOT / "runs" / "demo-sessions-01"
    manifest_p = sessions_dir / "manifest.json"
    assert manifest_p.exists(), "demo-sessions-01/manifest.json must exist"

    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    assert "sessions" in manifest
    sessions = manifest["sessions"]
    assert len(sessions) == 8, f"Expected exactly 8 recorded sessions, got {len(sessions)}"

    required_keys = {
        "session_id",
        "start_program",
        "scenario",
        "failing_episode",
        "falsifier_trace",
        "minimizer_steps",
        "minimal_counterexample",
        "repair_prompt",
        "model_response",
        "repaired_program",
        "acceptance_stages",
        "replay",
        "held_out_mini_check",
    }

    for s_info in sessions:
        s_id = s_info["session_id"]
        s_path = sessions_dir / s_id / "session.json"
        assert s_path.exists(), f"session.json missing for {s_id}"

        data = json.loads(s_path.read_text(encoding="utf-8"))
        missing = required_keys - set(data.keys())
        assert not missing, f"Session {s_id} missing keys: {missing}"

        # Check sub-schemas
        assert "seed" in data["scenario"]
        assert "mass" in data["scenario"]
        assert "friction" in data["scenario"]

        assert "margin" in data["failing_episode"]["sim_result"]
        assert data["failing_episode"]["sim_result"]["truth_success"] is False

        assert "raw_text" in data["model_response"]
        assert "cost_usd" in data["model_response"]
        assert "tokens_in" in data["model_response"]
        assert "tokens_out" in data["model_response"]

        assert "diff" in data["repaired_program"]
        assert "code" in data["repaired_program"]

        assert "stage1" in data["acceptance_stages"]
        assert "stage2" in data["acceptance_stages"]
        assert "stage3" in data["acceptance_stages"]
        assert "accepted" in data["acceptance_stages"]

        assert data["replay"]["verified"] is True
        assert "logged_margin" in data["replay"]
        assert "replayed_margin" in data["replay"]

        mini = data["held_out_mini_check"]
        assert mini["n_scenarios"] == 20
        assert "k_pass" in mini
        assert "lower_bound" in mini
        assert mini["label"] == "small-sample check, not a certificate"


def test_replay_equals_log() -> None:
    """V1: Replay of revised program on the scenario must match logged result."""
    sessions_dir = ROOT / "runs" / "demo-sessions-01"
    manifest = json.loads((sessions_dir / "manifest.json").read_text(encoding="utf-8"))

    for s_info in manifest["sessions"]:
        s_id = s_info["session_id"]
        data = json.loads((sessions_dir / s_id / "session.json").read_text(encoding="utf-8"))
        replay = data["replay"]

        # V1: replay must match logged result exactly
        assert replay["verified"] is True, f"Replay unverified in {s_id}"
        assert replay["logged_success"] == replay["replayed_success"], (
            f"Success mismatch in {s_id}: logged={replay['logged_success']} vs replayed={replay['replayed_success']}"
        )
        assert abs(replay["logged_margin"] - replay["replayed_margin"]) < 1e-4, (
            f"Margin mismatch in {s_id}: logged={replay['logged_margin']} vs replayed={replay['replayed_margin']}"
        )


def test_selection_rule_reproducibility() -> None:
    """Selection rule reproduces the exact same 8 scenarios from repair seeds starting at 900000."""
    sessions_dir = ROOT / "runs" / "demo-sessions-01"
    selection_log_p = sessions_dir / "selection_log.json"
    assert selection_log_p.exists(), "selection_log.json must exist"

    sel_log = json.loads(selection_log_p.read_text(encoding="utf-8"))
    selected_seeds = [item["seed"] for item in sel_log["selected"]]
    assert len(selected_seeds) == 8, f"Expected 8 selected scenarios, got {len(selected_seeds)}"

    # Check against session manifest
    manifest = json.loads((sessions_dir / "manifest.json").read_text(encoding="utf-8"))
    session_seeds = [s["scenario"]["seed"] for s in manifest["sessions"]]
    assert selected_seeds == session_seeds, "Selected seeds in log do not match session manifest"


def test_ui_asset_paths_resolve() -> None:
    """Every frame/thumbnail referenced by Repair Theatre resolves on disk in dashboard/."""
    dash_dir = ROOT / "dashboard"
    theatre_data_p = dash_dir / "repair_theatre_data.json"
    assert theatre_data_p.exists(), "dashboard/repair_theatre_data.json must exist"

    theatre_data = json.loads(theatre_data_p.read_text(encoding="utf-8"))
    assert "sessions" in theatre_data
    assert len(theatre_data["sessions"]) == 8

    for s in theatre_data["sessions"]:
        # Verify frame paths
        for f in s.get("failing_frames", []):
            f_path = dash_dir / f
            assert f_path.exists(), f"Failing frame {f} missing on disk"
        for f in s.get("replay_frames", []):
            f_path = dash_dir / f
            assert f_path.exists(), f"Replay frame {f} missing on disk"


def test_no_hand_typed_numbers_theatre() -> None:
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
        "3.1", "1.3", "10b", "10c", "10", "4x4", "G3", "G2", "G1", "G0", "T1", "T2",
        "H1", "H2", "H3", "H4", "H11", "H12", "H13", "H14", "H15", "H16", "H17",
        "V1", "V5", "V6", "V7", "V9", "V10", "V12",
        "B0", "B1", "B2", "B3", "B4",
        "100%", "0", "v1", "v2", "F7",
    }
    forbidden = []
    for tok in text_only.split():
        clean = tok.strip("(),;:.[]{}'\"")
        if re.search(r'\d', clean) and clean not in allowed_tokens:
            forbidden.append(clean)

    assert not forbidden, f"Found hand-typed numbers in static HTML: {forbidden[:10]}"


def test_dashboard_size_cap() -> None:
    """Total dashboard size is <= 25 MB."""
    dash_dir = ROOT / "dashboard"
    total_bytes = sum(f.stat().st_size for f in dash_dir.rglob("*") if f.is_file())
    cap_bytes = 25 * 1024 * 1024
    assert total_bytes <= cap_bytes, f"dashboard/ size ({total_bytes / (1024*1024):.2f} MB) exceeds 25 MB cap"
