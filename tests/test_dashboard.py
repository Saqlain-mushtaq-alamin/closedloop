"""Phase 10 tests: Dashboard and precomputed assets (Gate G3, Plan §13).

Asserts:
- test_regeneration_determinism (V12): regenerate twice -> byte-identical asset outputs.
- test_asset_provenance (H11): every asset maps to valid run_id, config hash, and content sha256.
- test_dashboard_offline: dashboard opens offline with zero external network / API dependencies.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_asset_provenance() -> None:
    """H11: Every asset maps to a source run_id and frozen config hash."""
    manifest_path = ROOT / "assets" / "manifest.json"
    assert manifest_path.exists(), "assets/manifest.json must exist"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "assets" in manifest, "Manifest must contain 'assets' dictionary"
    assets = manifest["assets"]
    assert len(assets) >= 5, f"Expected at least 5 core assets, got {len(assets)}"

    # Required asset categories
    required_types = {
        "heatmap_state",
        "heatmap_camera",
        "price_plot",
        "shift_figure",
        "filmstrip_sam",
    }
    found_types = {a.get("type") for a in assets.values()}
    for req in required_types:
        assert req in found_types, f"Required asset type '{req}' missing from manifest"

    for asset_name, meta in assets.items():
        rel_path = meta.get("path")
        assert rel_path, f"Asset {asset_name} missing 'path'"
        asset_file = ROOT / rel_path
        assert asset_file.exists(), f"Asset file does not exist: {asset_file}"

        # Provenance checks
        run_id = meta.get("run_id")
        assert run_id, f"Asset {asset_name} missing 'run_id'"
        run_manifest_file = ROOT / "runs" / run_id / "manifest.json"
        assert (
            run_manifest_file.exists()
        ), f"Source run manifest does not exist: {run_manifest_file}"

        run_manifest = json.loads(run_manifest_file.read_text(encoding="utf-8"))
        expected_cfg_hash = run_manifest.get("config_hash")
        assert (
            meta.get("config_hash") == expected_cfg_hash
        ), f"Config hash mismatch for asset {asset_name}"

        # SHA-256 integrity check
        actual_sha = hashlib.sha256(asset_file.read_bytes()).hexdigest()
        assert (
            meta.get("sha256") == actual_sha
        ), f"Content sha256 mismatch for asset {asset_name}"


def test_regeneration_determinism(tmp_path: Path) -> None:
    """V12: Generating assets twice produces byte-identical outputs."""
    from closedloop.report.generate_assets import generate_all_assets

    target_dir1 = tmp_path / "gen1"
    target_dir2 = tmp_path / "gen2"

    manifest1 = generate_all_assets(output_dir=target_dir1)
    manifest2 = generate_all_assets(output_dir=target_dir2)

    assert set(manifest1["assets"].keys()) == set(manifest2["assets"].keys())

    for k in manifest1["assets"]:
        sha1 = manifest1["assets"][k]["sha256"]
        sha2 = manifest2["assets"][k]["sha256"]
        assert sha1 == sha2, f"Asset '{k}' not deterministic across runs: {sha1} != {sha2}"

        # Compare actual file bytes
        p1 = target_dir1 / Path(manifest1["assets"][k]["path"]).name
        p2 = target_dir2 / Path(manifest2["assets"][k]["path"]).name
        assert p1.read_bytes() == p2.read_bytes(), f"Byte mismatch for {k}"


def test_dashboard_offline() -> None:
    """Dashboard loads 100% offline: zero external HTTP/HTTPS scripts, fonts, or stylesheets."""
    dashboard_html = ROOT / "dashboard" / "index.html"
    assert dashboard_html.exists(), "dashboard/index.html must exist"

    html_content = dashboard_html.read_text(encoding="utf-8")

    # Reject external script sources (e.g. cdnjs, unpkg, googleapis)
    external_scripts = re.findall(
        r'<script[^>]+src=["\'](https?://[^"\']+)["\']', html_content, re.IGNORECASE
    )
    assert not external_scripts, f"External scripts forbidden in offline dashboard: {external_scripts}"

    # Reject external stylesheets
    external_styles = re.findall(
        r'<link[^>]+href=["\'](https?://[^"\']+)["\']', html_content, re.IGNORECASE
    )
    assert not external_styles, f"External stylesheets forbidden: {external_styles}"

    # Assert required views from Plan §13 are present
    assert "heatmap" in html_content.lower(), "Dashboard missing Heatmap view"
    assert "filmstrip" in html_content.lower(), "Dashboard missing Filmstrip view"
    assert "price" in html_content.lower() or "calibration" in html_content.lower(), "Dashboard missing Price-of-footage view"
    assert "shift" in html_content.lower(), "Dashboard missing Shift test view"
    assert "run_id" in html_content or "provenance" in html_content.lower(), "Dashboard missing Provenance section"
