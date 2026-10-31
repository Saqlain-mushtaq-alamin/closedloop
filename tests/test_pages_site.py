"""Tests for GitHub Pages static site deployment, paths, and verifiable evidence (Phase 10e).

Asserts:
- test_site_paths: sub-path crawler visits index and all assets, asserting HTTP 200 and valid content-type.
- test_first_load_size: initial payload (index.html, console.js, data.js, repair_theatre_data.js) <= 2 MB.
- test_no_external_hosts: zero external network dependencies or hosts in dashboard.
- test_evidence_hash_manifest: sha256 values in provenance manifest match committed episodes.jsonl files.
- test_workflow_valid: .github/workflows/pages.yml parses valid YAML with minimal permissions and official actions.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_site import check_site, get_first_load_size, get_total_dashboard_size


def test_site_paths() -> None:
    """Sub-path crawl verifies that every page and asset returns HTTP 200 without broken relative links."""
    res = check_site(repo_root=ROOT)
    assert res["status"] == "PASS"
    assert res["checked_urls_count"] >= 50, f"Expected at least 50 checked URLs, got {res['checked_urls_count']}"


def test_first_load_size() -> None:
    """First-load resources (HTML + core JS data) must be under 2 MB; total dashboard under 25 MB."""
    dash_dir = ROOT / "dashboard"
    first_load = get_first_load_size(dash_dir)
    assert first_load <= 2 * 1024 * 1024, f"First load size {first_load / 1024:.1f} KB exceeds 2 MB limit"

    total_size = get_total_dashboard_size(dash_dir)
    assert total_size <= 25 * 1024 * 1024, f"Total dashboard size {total_size / (1024*1024):.2f} MB exceeds 25 MB limit"


def test_no_external_hosts() -> None:
    """Dashboard must be 100% offline-compatible: zero external HTTP/HTTPS host dependencies."""
    dash_dir = ROOT / "dashboard"
    external_url_pattern = re.compile(r'https?://(?:(?!127\.0\.0\.1|localhost)[a-zA-Z0-9.-]+)')

    for fpath in dash_dir.rglob("*"):
        if fpath.suffix in [".html", ".js", ".css", ".json"]:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            # Exclude schema definitions or doc strings if any
            matches = external_url_pattern.findall(text)
            assert not matches, f"External host found in {fpath.name}: {matches}"


def test_evidence_hash_manifest() -> None:
    """Every run_id listed in DATA.provenance matches the actual SHA-256 of the committed episodes.jsonl on disk."""
    data_json_path = ROOT / "dashboard" / "data.json"
    assert data_json_path.exists(), "dashboard/data.json must exist"

    data = json.loads(data_json_path.read_text(encoding="utf-8"))
    provenance = data.get("provenance", {})
    assert len(provenance) >= 5, f"Expected at least 5 provenance records, got {len(provenance)}"

    for run_id, meta in provenance.items():
        ep_file = ROOT / "runs" / run_id / "episodes.jsonl"
        assert ep_file.exists(), f"Committed log missing for provenance run {run_id}: {ep_file}"

        actual_sha = hashlib.sha256(ep_file.read_bytes()).hexdigest()
        expected_sha = meta.get("episodes_sha256")
        assert (
            actual_sha == expected_sha
        ), f"Cryptographic provenance mismatch for {run_id}: actual {actual_sha} != manifest {expected_sha}"


def test_workflow_valid() -> None:
    """Deployment workflow must be valid YAML with minimal permissions and official actions."""
    wf_path = ROOT / ".github" / "workflows" / "pages.yml"
    assert wf_path.exists(), ".github/workflows/pages.yml must exist"

    content = wf_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    # Check triggers
    triggers = parsed.get("on") or parsed.get(True, {})
    assert "push" in triggers, "Workflow missing 'push' trigger"
    assert "workflow_dispatch" in triggers, "Workflow missing 'workflow_dispatch' trigger"
    assert "main" in triggers["push"].get("branches", []), "Push trigger must target 'main' branch"

    # Check minimal permissions
    perms = parsed.get("permissions", {})
    assert perms.get("contents") == "read", "Permission 'contents' must be 'read'"
    assert perms.get("pages") == "write", "Permission 'pages' must be 'write'"
    assert perms.get("id-token") == "write", "Permission 'id-token' must be 'write'"
    # No extra broad permissions
    forbidden_perms = {"pull-requests", "issues", "actions", "security-events"}
    assert not forbidden_perms.intersection(perms.keys()), f"Forbidden excessive permissions: {perms}"

    # Check steps and official actions
    jobs = parsed.get("jobs", {})
    assert "build" in jobs and "deploy" in jobs, "Workflow must contain 'build' and 'deploy' jobs"

    build_steps = jobs["build"].get("steps", [])
    uses_list = [s.get("uses", "") for s in build_steps]

    assert any(u.startswith("actions/checkout@v4") for u in uses_list), "Missing actions/checkout@v4"
    assert any(u.startswith("actions/configure-pages@v5") for u in uses_list), "Missing actions/configure-pages@v5"
    assert any(u.startswith("actions/upload-pages-artifact@v3") for u in uses_list), "Missing actions/upload-pages-artifact@v3"

    # Verify upload path is 'dashboard'
    upload_step = next(s for s in build_steps if "actions/upload-pages-artifact" in s.get("uses", ""))
    assert upload_step.get("with", {}).get("path") == "dashboard", "Upload path must be 'dashboard'"

    deploy_steps = jobs["deploy"].get("steps", [])
    deploy_uses = [s.get("uses", "") for s in deploy_steps]
    assert any(u.startswith("actions/deploy-pages@v4") for u in deploy_uses), "Missing actions/deploy-pages@v4"
