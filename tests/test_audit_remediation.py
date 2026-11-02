"""Tests for Phase 12b Audit Remediation (Rules H9, H10, H11, H12).

Tests:
1. test_no_duplicate_seed_program_pairs: Valid certification runs have zero duplicate (seed, program_id) pairs.
2. test_planned_equals_logged: Valid runs have logged episode count == manifest episodes_planned.
3. test_invalid_runs_excluded: Quarantined runs in runs/INVALID_RUNS.json are excluded from tooling.
4. test_certification_driver_refuses_existing_run_dir: Certification driver guards against reuse/overwrites.
5. test_docs_numbers_match_report_summary: Numbers published in docs match assets/report_summary.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))



def get_invalid_runs() -> set[str]:
    inv_file = ROOT / "runs" / "INVALID_RUNS.json"
    if not inv_file.exists():
        return set()
    data = json.loads(inv_file.read_text(encoding="utf-8"))
    return set(data.keys())


def test_invalid_runs_quarantine_file_exists():
    inv_file = ROOT / "runs" / "INVALID_RUNS.json"
    assert inv_file.exists(), "runs/INVALID_RUNS.json must exist"
    data = json.loads(inv_file.read_text(encoding="utf-8"))
    assert "cert2-full-01" in data
    assert "judge-g2-01" in data
    assert "cert-pilot-01-fabricated" in data
    assert "h2h3-full-02" in data


def test_no_duplicate_seed_program_pairs():
    """Valid certification runs must have strictly unique (seed, program_id) pairs."""
    invalid = get_invalid_runs()
    runs_dir = ROOT / "runs"

    # 1. Confirm cert2-full-01 had duplicates (the audit finding)
    c2_episodes = runs_dir / "cert2-full-01" / "episodes.jsonl"
    if c2_episodes.exists():
        c2_pairs = []
        for line in c2_episodes.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ep = json.loads(line)
                c2_pairs.append((ep.get("seed"), ep.get("program_id")))
        assert len(c2_pairs) == 4918
        assert len(set(c2_pairs)) == 2459, "cert2-full-01 must have duplicate seed-program pairs"

    # 2. Check all valid certification runs
    for p in runs_dir.iterdir():
        if not p.is_dir() or p.name in invalid or p.name.startswith("."):
            continue
        ep_file = p / "episodes.jsonl"
        mf_file = p / "manifest.json"
        if not ep_file.exists() or not mf_file.exists():
            continue
        
        # Check if run contains certification stream
        seen_pairs: set[tuple[int, str]] = set()
        for line_idx, line in enumerate(ep_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            ep = json.loads(line)
            if ep.get("stream") == "certification":
                pair = (ep["seed"], ep.get("program_id", ""))
                assert pair not in seen_pairs, (
                    f"Duplicate certification (seed, program_id) pair {pair} in valid run {p.name} at line {line_idx}"
                )
                seen_pairs.add(pair)


def test_planned_equals_logged():
    """All valid runs must satisfy logged episode count == manifest episodes_planned."""
    invalid = get_invalid_runs()
    runs_dir = ROOT / "runs"

    for p in sorted(runs_dir.iterdir()):
        if not p.is_dir() or p.name in invalid or p.name.startswith("."):
            continue
        mf_file = p / "manifest.json"
        ep_file = p / "episodes.jsonl"
        if not mf_file.exists() or not ep_file.exists():
            continue

        mf = json.loads(mf_file.read_text(encoding="utf-8"))
        planned = mf.get("episodes_planned")
        if planned is None:
            continue
        logged = sum(1 for line in ep_file.read_text(encoding="utf-8").splitlines() if line.strip())
        assert logged == planned, (
            f"Run {p.name} has planned={planned} but logged={logged} (must be equal for valid runs)"
        )


def test_invalid_runs_excluded():
    """Verify that build_ui_data and verify_evidence exclude quarantined invalid runs."""
    from closedloop.report.build_ui_data import build_ui_data
    from scripts.verify_evidence import verify_evidence

    # build_ui_data must not include cert2-full-01 in source_runs
    ui_data = build_ui_data()
    prov = ui_data.get("provenance", {})
    assert "cert2-full-01" not in prov, "cert2-full-01 must be excluded from build_ui_data"

    # verify_evidence must pass and not verify cert2-full-01 without valid status
    matched, total = verify_evidence()
    assert matched == total
    assert matched > 0


def test_certification_driver_refuses_existing_run_dir(tmp_path):
    """Certification driver must refuse existing run dir, non-empty log, or reset ledger."""
    from experiments.run_cert import run_certification

    # Test 1: existing run dir
    dummy_dir = ROOT / "runs" / "test-dummy-guard-run"
    dummy_dir.mkdir(parents=True, exist_ok=True)
    try:
        with pytest.raises(FileExistsError):
            run_certification("test-dummy-guard-run", cert_config_path="configs/cert.yaml")
    finally:
        if dummy_dir.exists():
            dummy_dir.rmdir()


def test_docs_numbers_match_report_summary():
    """Published documents must match values in assets/report_summary.json."""
    summary_path = ROOT / "assets" / "report_summary.json"
    assert summary_path.exists(), "assets/report_summary.json must exist"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # 1. Check docs/REPORT.md repair acceptance rates
    report_text = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    b1_rate = summary["repair_acceptance_rates"]["B1"]
    b2_rate = summary["repair_acceptance_rates"]["B2"]
    b3_rate = summary["repair_acceptance_rates"]["B3"]

    # Table in REPORT.md must show these exact values
    assert f"{b1_rate:.2f}" in report_text or f"{b1_rate:.3f}" in report_text, f"B1 rate {b1_rate} missing from REPORT.md"
    assert f"{b2_rate:.2f}" in report_text or f"{b2_rate:.3f}" in report_text, f"B2 rate {b2_rate} missing from REPORT.md"
    assert f"{b3_rate:.2f}" in report_text or f"{b3_rate:.3f}" in report_text, f"B3 rate {b3_rate} missing from REPORT.md"

    # Damage rate in REPORT.md must be 0.05 (from repair_results.json), not 0.00%
    assert "0.05" in report_text, "Damage rate 0.05 must be quoted in REPORT.md"
    assert "0.00%" not in report_text, "Damage rate 0.00% is incorrect and must not appear in REPORT.md"

    # 2. Check headline numbers in README.md
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    sh_in = summary["shift_in_bound"]
    sh_out = summary["shift_out_bound"]
    assert f"{sh_in:.4f}" in readme_text, f"Shift in bound {sh_in:.4f} missing from README.md"
    assert f"{sh_out:.4f}" in readme_text, f"Shift out bound {sh_out:.4f} missing from README.md"

    # 3. Check SUBMISSION_DRAFT.md numbers
    sub_text = (ROOT / "docs" / "SUBMISSION_DRAFT.md").read_text(encoding="utf-8")
    assert f"{sh_in:.4f}" in sub_text, f"Shift in bound {sh_in:.4f} missing from SUBMISSION_DRAFT.md"
    assert f"{sh_out:.4f}" in sub_text, f"Shift out bound {sh_out:.4f} missing from SUBMISSION_DRAFT.md"


def test_banned_claim_wording():
    """Verify Rule H14 claim wording across all tracked text files and user documents."""
    import subprocess

    try:
        tracked_files = subprocess.check_output(
            ["git", "ls-files"], cwd=str(ROOT), text=True
        ).splitlines()
    except Exception:
        tracked_files = ["README.md", "docs/REPORT.md", "docs/SUBMISSION_DRAFT.md", "demo/SCRIPT.md"]

    text_exts = {".md", ".html", ".js", ".json", ".py", ".yaml", ".yml"}
    exempt_files = {"AGENTS.md", "tests/test_audit_remediation.py", "scripts/reproduce_audit.py", "docs/phase_logs/PHASE_12b.md"}

    # Rule H14 checks
    pat_cert_safe = re.compile(r"\b(certified\s+safe|safe\s+certified|certified\s+safe\s+region)\b", re.IGNORECASE)
    
    # Check all tracked text files for 'certified safe'
    for f_path in tracked_files:
        if f_path in exempt_files or not any(f_path.endswith(ext) for ext in text_exts):
            continue
        full_p = ROOT / f_path
        if not full_p.exists():
            continue
        content = full_p.read_text(encoding="utf-8", errors="ignore")
        match = pat_cert_safe.search(content)
        assert match is None, f"Found banned phrase '{match.group()}' in {f_path}"

    # Check user-facing docs specifically for novel, proven, camera alone, safe region
    user_docs = ["README.md", "docs/REPORT.md", "docs/SUBMISSION_DRAFT.md", "demo/SCRIPT.md", "dashboard/console.js", "dashboard/index.html"]
    banned_in_docs = [
        (re.compile(r"\bnovel\b", re.IGNORECASE), "novel"),
        (re.compile(r"\bproven\b", re.IGNORECASE), "proven"),
        (re.compile(r"\bcamera\s+alone\b", re.IGNORECASE), "camera alone"),
        (re.compile(r"\bsafe\s+region\b", re.IGNORECASE), "safe region"),
    ]

    for doc in user_docs:
        doc_p = ROOT / doc
        if not doc_p.exists():
            continue
        text = doc_p.read_text(encoding="utf-8", errors="ignore")
        for pat, word in banned_in_docs:
            m = pat.search(text)
            assert m is None, f"Found banned word/phrase '{word}' in {doc}: '{m.group() if m else ''}'"

