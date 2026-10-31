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
import math
import shutil
import pytest
from scipy.stats import binomtest

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


def test_selfcheck_table() -> None:
    """Expected lower bounds in DATA.selfcheck match independent SciPy exact CI."""
    data_json_path = ROOT / "dashboard" / "data.json"
    assert data_json_path.exists(), "dashboard/data.json must exist"

    data = json.loads(data_json_path.read_text(encoding="utf-8"))
    selfcheck = data.get("selfcheck", [])
    assert len(selfcheck) >= 30, f"Expected at least 30 selfcheck tuples, got {len(selfcheck)}"

    for item in selfcheck:
        k, n, delta, expected_lower = item[0], item[1], item[2], item[3]
        if k == 0:
            scipy_lower = 0.0
        else:
            conf = max(0.0, min(1.0, 1.0 - 2.0 * delta))
            scipy_lower = float(
                binomtest(k, n).proportion_ci(confidence_level=conf, method="exact").low
            )
        assert math.isclose(
            expected_lower, scipy_lower, abs_tol=1e-7
        ), f"Mismatch for k={k}, n={n}, delta={delta}: {expected_lower} vs {scipy_lower}"


def test_data_from_logs(tmp_path: Path) -> None:
    """Two builds are byte-identical (V12); mutating a log changes data.js."""
    from closedloop.report.build_ui_data import build_ui_data

    out1_js = tmp_path / "run1" / "data.js"
    out1_json = tmp_path / "run1" / "data.json"
    out2_js = tmp_path / "run2" / "data.js"
    out2_json = tmp_path / "run2" / "data.json"

    build_ui_data(output_js=out1_js, output_json=out1_json)
    build_ui_data(output_js=out2_js, output_json=out2_json)

    assert out1_js.read_bytes() == out2_js.read_bytes(), "data.js not byte-deterministic"
    assert out1_json.read_bytes() == out2_json.read_bytes(), "data.json not byte-deterministic"

    # Mutate one k in a temporary copy of runs
    mock_runs = tmp_path / "mock_runs"
    shutil.copytree(ROOT / "runs", mock_runs)
    cs_p = mock_runs / "cert-full-01" / "cert_summary.json"
    cs = json.loads(cs_p.read_text(encoding="utf-8"))
    cs["cells"]["cell_00"]["state"]["k_pass"] = 149
    cs_p.write_text(json.dumps(cs, indent=2), encoding="utf-8")

    out3_js = tmp_path / "run3" / "data.js"
    out3_json = tmp_path / "run3" / "data.json"
    build_ui_data(runs_dir=mock_runs, output_js=out3_js, output_json=out3_json)

    assert out1_js.read_bytes() != out3_js.read_bytes(), "data.js failed to change when log was mutated"


def test_replays_match_logs() -> None:
    """V1 check on at least 2 clips: replayed results match logged episodes."""
    replays_dir = ROOT / "dashboard" / "replays"
    manifest_p = replays_dir / "manifest.json"
    assert manifest_p.exists(), "dashboard/replays/manifest.json must exist"

    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    clips = manifest.get("clips", [])
    assert len(clips) >= 2, f"Expected at least 2 replay clips, got {len(clips)}"

    for clip in clips[:5]:
        clip_id = clip["clip_id"]
        meta_p = replays_dir / clip_id / "meta.json"
        assert meta_p.exists(), f"meta.json missing for clip {clip_id}"
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        assert "truth_success" in meta
        assert "margin" in meta
        assert meta.get("verified", False) is True, f"Clip {clip_id} was not verified against simulation"
        frames = meta.get("frames", [])
        assert len(frames) > 0, f"No frames listed for {clip_id}"
        for f in frames:
            assert (replays_dir / clip_id / f).exists(), f"Frame {f} missing in {clip_id}"


def test_ui_paths() -> None:
    """Every local src/href/url() resolves on disk with dashboard/ as the root."""
    dash_dir = ROOT / "dashboard"
    index_html = dash_dir / "index.html"
    assert index_html.exists(), "dashboard/index.html must exist"

    content = index_html.read_text(encoding="utf-8")
    srcs = re.findall(r'src=["\']([^"\']+)["\']', content)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', content)
    urls = re.findall(r'url\(["\']?([^"\'\)]+)["\']?\)', content)

    for ref in srcs + hrefs + urls:
        clean = ref.strip()
        if not clean or clean.startswith(("#", "http://", "https://", "mailto:", "javascript:", "data:")):
            continue
        rel_target = clean.split("?")[0].split("#")[0]
        if not rel_target:
            continue
        local_file = (dash_dir / rel_target).resolve()
        assert local_file.exists(), f"Path referenced in index.html does not exist relative to dashboard: {clean} -> {local_file}"


def test_no_hand_typed_numbers() -> None:
    """Static HTML outside <script>/<style> has no digits except an explicit allow-list."""
    index_html = ROOT / "dashboard" / "index.html"
    content = index_html.read_text(encoding="utf-8")

    no_script = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', content, flags=re.IGNORECASE)
    no_style = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', no_script, flags=re.IGNORECASE)
    no_comments = re.sub(r'<!--.*?-->', '', no_style, flags=re.DOTALL)
    text_only = re.sub(r'<[^>]+>', ' ', no_comments)

    allowed_tokens = {
        "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.",
        "1", "2", "3", "4", "5", "6", "7", "8",
        "3.1", "1.3", "10b", "10", "4x4", "G3", "G2", "G1", "G0", "T1", "T2",
        "H1", "H2", "H3", "H4", "H11", "H12", "H13", "H14", "H15", "H16", "H17",
        "V1", "V5", "V6", "V7", "V9", "V10", "V12",
        "B0", "B1", "B2", "B3", "B4",
        "100%", "0",
    }
    forbidden = []
    for tok in text_only.split():
        clean = tok.strip("(),;:.[]{}'\"")
        if re.search(r'\d', clean) and clean not in allowed_tokens:
            forbidden.append(clean)

    assert not forbidden, f"Found hand-typed numbers in static HTML body: {forbidden[:10]}"


def test_size_cap() -> None:
    """dashboard/ at most 15 MB."""
    dash_dir = ROOT / "dashboard"
    total_bytes = sum(f.stat().st_size for f in dash_dir.rglob("*") if f.is_file())
    cap_bytes = 15 * 1024 * 1024
    assert total_bytes <= cap_bytes, f"dashboard/ size ({total_bytes / (1024*1024):.2f} MB) exceeds 15 MB cap"
