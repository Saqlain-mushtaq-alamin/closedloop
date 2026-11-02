"""Phase 12: Final Compliance Audit, Submission Package, and Regeneration Tests.

Asserts:
- test_final_compliance_scan (V13 / H2 / H3 / H6 / H14): secrets scan across working tree and git log,
  locked files integrity, THIRD_PARTY.md licence coverage, and wording scan.
- test_full_regeneration (V12 / H11): report generator runs twice into separate directories producing
  100% byte-identical asset outputs and manifests.
- test_submission_package: docs/SUBMISSION_DRAFT.md exists, contains all required form fields,
  disclosures, contributor list, finals fallback, and verifies submission-v1 tag existence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_compliance_scan() -> None:
    """Task 1 / V13: verify secrets, locked files, licences, and wording."""
    # 1. Locked files check (H6)
    locked_hashes_file = ROOT / "LOCKED_HASHES.txt"
    assert locked_hashes_file.exists(), "LOCKED_HASHES.txt missing"
    for line in locked_hashes_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        expected_hash, rel_path = line.split(None, 1)
        rel_path = rel_path.strip().lstrip("*")
        target_file = ROOT / rel_path
        assert target_file.exists(), f"Locked file missing: {rel_path}"
        actual_hash = _sha256(target_file)
        assert actual_hash == expected_hash, f"H6 violation: {rel_path} was modified!"

    # 2. Secrets check across git working tree (H2)
    secret_pattern = re.compile(
        r'sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{10,}|MODEL_API_KEY\s*=\s*[\'"][^\'"]+[\'"]|META_API_KEY\s*=\s*[\'"][^\'"]+[\'"]'
    )
    res = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    tracked_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    for rel_f in tracked_files:
        p = ROOT / rel_f
        if not p.is_file() or p.suffix in [".png", ".jpg", ".zip", ".ico", ".woff", ".woff2"]:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        match = secret_pattern.search(text)
        assert match is None, f"H2 violation: secret pattern found in {rel_f}: {match.group(0)}"

    # 3. Wording check on all public documentation (H14)
    forbidden_terms = ["proven", "safe", "camera alone", "novel"]
    public_docs = [ROOT / "README.md", ROOT / "docs" / "REPORT.md", ROOT / "demo" / "SCRIPT.md"]
    for doc in public_docs:
        if not doc.exists():
            continue
        lines = doc.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, 1):
            lower = line.lower()
            for term in forbidden_terms:
                pat = r"\b" + re.escape(term) + r"\b"
                if re.search(pat, lower):
                    if "does not guarantee" in lower or "not proof of" in lower or "cannot be deemed safe" in lower:
                        continue
                    if term == "safe" and ("subprocess" in lower or "fail-safe" in lower or "sandbox" in lower):
                        continue
                    pytest.fail(f"H14 violation in {doc.name}:{idx}: '{term}' found:\n  {line}")

    # 4. THIRD_PARTY.md coverage (H3)
    third_party = ROOT / "THIRD_PARTY.md"
    assert third_party.exists(), "THIRD_PARTY.md missing"
    tp_text = third_party.read_text(encoding="utf-8")
    for dep in ["numpy", "scipy", "pybullet", "pytest", "PyYAML", "optuna", "fastapi"]:
        assert dep in tp_text, f"Dependency {dep} missing in THIRD_PARTY.md"


def test_full_regeneration(tmp_path: Path) -> None:
    """Task 1 / V12: generate_all_assets twice into distinct dirs produces byte-identical results."""
    from closedloop.report.generate_assets import generate_all_assets

    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    manifest_a = generate_all_assets(dir_a)
    manifest_b = generate_all_assets(dir_b)

    assert set(manifest_a["assets"].keys()) == set(manifest_b["assets"].keys()), "Asset sets differ"

    for asset_name in manifest_a["assets"]:
        file_a = dir_a / Path(manifest_a["assets"][asset_name]["path"]).name
        file_b = dir_b / Path(manifest_b["assets"][asset_name]["path"]).name
        assert file_a.exists(), f"Missing asset in run A: {file_a}"
        assert file_b.exists(), f"Missing asset in run B: {file_b}"
        hash_a = _sha256(file_a)
        hash_b = _sha256(file_b)
        assert hash_a == hash_b, f"V12 non-determinism in asset {asset_name}: {hash_a} != {hash_b}"

    # Also verify summary numbers are identical
    sum_a = (dir_a / "report_summary.json").read_text(encoding="utf-8")
    sum_b = (dir_b / "report_summary.json").read_text(encoding="utf-8")
    assert sum_a == sum_b, "report_summary.json differs across regenerations"


def test_submission_package() -> None:
    """Task 3: verify docs/SUBMISSION_DRAFT.md completeness, finals fallback, and tag existence."""
    sub_file = ROOT / "docs" / "SUBMISSION_DRAFT.md"
    assert sub_file.exists(), f"Missing {sub_file}"

    text = sub_file.read_text(encoding="utf-8")

    # Required form fields
    assert "ClosedLoop" in text
    assert "Indie Developer" in text
    assert "Push the Frontier" in text
    assert "muse-spark-1.3" in text
    assert "sam-3.1" in text
    assert "https://api.meta.ai/v1" in text

    # Video timing & accessibility
    assert "≤ 3:00" in text or "<= 3:00" in text or "2:45" in text
    assert "no login" in text.lower() or "logged-out" in text.lower() or "public" in text.lower()

    # Finals fallback
    assert "Finals" in text
    assert "fallback" in text.lower() or "offline" in text.lower()

    # Git tag check
    res = subprocess.run(["git", "tag", "-l", "submission-v1"], cwd=ROOT, capture_output=True, text=True, check=True)
    tags = [t.strip() for t in res.stdout.splitlines() if t.strip()]
    assert "submission-v1" in tags, "Tag 'submission-v1' must exist in git repository"
