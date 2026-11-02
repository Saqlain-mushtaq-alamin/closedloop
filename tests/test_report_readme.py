"""Tests for Phase 11: Demo Script, README, Technical Report, and Compliance.

Validates:
- test_demo_script_timing_and_checklist: 2:45 timed read, 4 beats, precomputed assets, backup checklist
- test_readme_numbers_from_logs (V12 / Rule H11): numbers derived strictly from logs and report generator
- test_wording_scan (V13 / Rule H14): no unqualified first/novel/proven/safe/camera alone
- test_report_limitations: Plan §16 limitations and future work all present in docs/REPORT.md
- test_model_disclosures_and_budget: Meta model IDs, sample API log, error budget (K/B/M), built-during note
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_demo_script_timing_and_checklist() -> None:
    """Task 1: demo/SCRIPT.md exists, timed read <= 2:45, 4 beats, precomputed assets, backup checklist."""
    script_path = ROOT / "demo" / "SCRIPT.md"
    assert script_path.exists(), f"Missing {script_path}"

    text = script_path.read_text(encoding="utf-8")

    # 4 beats present
    assert "Beat 1" in text or "0:00" in text
    assert "Fail and diagnose" in text or "Failure" in text or "minimal counterexample" in text
    assert "Fix" in text or "Repair" in text
    assert "Heatmap" in text
    assert "Footage-price" in text or "Price of footage" in text or "shrinkage" in text

    # Total duration <= 2:45 (165 seconds)
    duration_match = re.search(r"Total (?:Time|Duration):\s*(\d+):(\d+)", text, re.IGNORECASE)
    assert duration_match is not None, "Total duration must be explicitly stated in demo/SCRIPT.md"
    minutes = int(duration_match.group(1))
    seconds = int(duration_match.group(2))
    total_seconds = minutes * 60 + seconds
    assert total_seconds <= 165, f"Demo duration {minutes}:{seconds:02d} ({total_seconds}s) exceeds 2:45 (165s)"
    assert total_seconds >= 150, f"Demo duration {minutes}:{seconds:02d} ({total_seconds}s) is shorter than 2:30"

    # Word count check for timed read (at ~130-150 words per minute, speech text should be 300-420 words)
    # Extract narration blocks: lines starting with 'Narration:' or quote blocks
    narration_lines = [
        line.split("Narration:", 1)[1].strip()
        for line in text.splitlines()
        if "Narration:" in line
    ]
    narration_text = " ".join(narration_lines)
    words = re.findall(r"\b[A-Za-z0-9'-]+\b", narration_text)
    assert len(words) <= 420, f"Narration word count {len(words)} is too long for a 2:45 read (target <= 420)"
    assert len(words) >= 200, f"Narration word count {len(words)} is too sparse"

    # Precomputed assets only, no live API
    assert "precomputed" in text.lower()
    assert "no live api" in text.lower() or "offline" in text.lower()

    # Checklist with two takes + backup recording
    assert "checklist" in text.lower()
    assert "take 1" in text.lower()
    assert "take 2" in text.lower()
    assert "backup" in text.lower()


def test_readme_numbers_from_logs() -> None:
    """Task 2 / V12 / Rule H11: numbers in README.md and docs/REPORT.md originate from logged runs."""
    readme_path = ROOT / "README.md"
    report_path = ROOT / "docs" / "REPORT.md"
    summary_path = ROOT / "assets" / "report_summary.json"

    assert readme_path.exists(), "README.md missing"
    assert report_path.exists(), "docs/REPORT.md missing"
    assert summary_path.exists(), "assets/report_summary.json missing (run make report)"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    readme_text = readme_path.read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")

    # Verify key statistical bounds exist in report summary and match exactly in README / REPORT
    state_bound = f"{summary['state_headline_bound']:.4f}"
    camera_bound = f"{summary['camera_headline_bound']:.4f}"
    certified_cells = f"{summary['certified_cells_count']}/{summary['total_cells_count']}"

    assert state_bound in readme_text or state_bound in report_text, f"State bound {state_bound} not found"
    assert camera_bound in readme_text or camera_bound in report_text, f"Camera bound {camera_bound} not found"
    assert certified_cells in readme_text or certified_cells in report_text, f"Certified cell fraction {certified_cells} not found"

    # Verify shift numbers match logs
    shift_in_bound = f"{summary['shift_in_bound']:.4f}"
    assert shift_in_bound in report_text, f"Shift in-distribution bound {shift_in_bound} missing in report"


def test_wording_scan() -> None:
    """Task 2 / V13 / Rule H14: check wording across all public markdown files."""
    files_to_check = [
        ROOT / "README.md",
        ROOT / "docs" / "REPORT.md",
        ROOT / "demo" / "SCRIPT.md",
    ]

    # Forbidden patterns unless properly qualified:
    # Rule H14: Never write "first", "novel", "proven", "safe" or "camera alone".
    # Allowed alternatives: "rendered camera footage", "certified in simulation under distribution D",
    # and "to my knowledge, I did not find ...".
    forbidden_terms = ["proven", "safe", "camera alone", "novel"]

    for f in files_to_check:
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()

        for idx, line in enumerate(lines, 1):
            lower_line = line.lower()

            # Check forbidden terms
            for term in forbidden_terms:
                pattern = r"\b" + re.escape(term) + r"\b"
                if re.search(pattern, lower_line):
                    # Exceptions allowed only if explicitly stating the disclaimer:
                    # e.g., "safe execution" in technical context or "does not guarantee safety"
                    if "does not guarantee" in lower_line or "not proof of" in lower_line or "cannot be deemed safe" in lower_line:
                        continue
                    if term == "safe" and ("subprocess" in lower_line or "fail-safe" in lower_line or "sandbox" in lower_line):
                        continue
                    pytest.fail(f"Violation of H14 in {f.name}:{idx}: found forbidden word '{term}':\n  {line}")

            # Check "first" - must be qualified with "to my knowledge, I did not find"
            if re.search(r"\bfirst\b", lower_line):
                if "to my knowledge" not in lower_line and "first-order" not in lower_line and "first time" not in lower_line and "write or extend the tests first" not in lower_line and "first" not in ["at first"]:
                    # Check if surrounded by "to my knowledge" within adjacent lines
                    context = " ".join(lines[max(0, idx - 2):min(len(lines), idx + 2)]).lower()
                    if "to my knowledge" not in context:
                        pytest.fail(f"Violation of H14 in {f.name}:{idx}: unqualified 'first':\n  {line}")


def test_report_limitations() -> None:
    """Task 2: docs/REPORT.md contains all Plan §16 limitations and future work items."""
    report_path = ROOT / "docs" / "REPORT.md"
    assert report_path.exists(), f"Missing {report_path}"

    text = report_path.read_text(encoding="utf-8")

    # §16.1 Sim-to-Real gap
    assert "Simulation-to-Reality Gap" in text or "Sim-to-Real" in text
    assert "PyBullet" in text
    assert "pre-deployment screening" in text

    # §16.2 Judge error and non-differential assumption
    assert "Non-Differential" in text or "Judge Error" in text
    assert "calibration" in text.lower()
    assert "bucket" in text.lower()

    # §16.3 Distribution-specific guarantee
    assert "distribution D" in text
    assert "Shift" in text

    # §16.4 Future work
    assert "Future Work" in text
    assert "hardware" in text.lower() or "physical" in text.lower()


def test_model_disclosures_and_budget() -> None:
    """Task 2: README and REPORT contain Meta model IDs, error budget (K/B/M), built-during statement, AI disclosure."""
    readme_path = ROOT / "README.md"
    report_path = ROOT / "docs" / "REPORT.md"

    assert readme_path.exists()
    assert report_path.exists()

    readme_text = readme_path.read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")

    # Built during hackathon statement (H1)
    assert "Oct 26" in readme_text and "Nov 4, 2026" in readme_text
    assert "built during" in readme_text.lower() or "developed during" in readme_text.lower()

    # Meta model IDs (H4)
    assert "muse-spark-1.3" in readme_text
    assert "sam-3.1" in readme_text
    assert "https://api.meta.ai/v1" in readme_text or "Meta Model API" in readme_text

    # AI-assistance disclosure
    assert "AI-agent" in readme_text or "AI-assistance" in readme_text or "Muse Code" in readme_text

    # Error budget K, B, M allocation (Plan §11)
    for doc in [readme_text, report_text]:
        assert "K=16" in doc or "K = 16" in doc
        assert "B=4" in doc or "B = 4" in doc
        assert "M=1" in doc or "M = 1" in doc
        assert "delta = 0.05" in doc or "delta=0.05" in doc or "95%" in doc
