"""Crawl and verify the static dashboard under a sub-path (Phase 10e).

Simulates GitHub Pages serving the repository under a sub-path:
    http://127.0.0.1:<port>/<repo_name>/dashboard/

Asserts:
- Every page and asset returns HTTP 200
- Correct Content-Type headers
- No root-absolute paths (e.g. '/assets/...')
- No external hosts
- First load size <= 2 MB
- Total dashboard size <= 25 MB
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPO_NAME = ROOT.name


class QuietSimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler that suppresses request logging."""

    def log_message(self, format: str, *args: Any) -> None:
        pass


def get_first_load_size(dash_dir: Path) -> int:
    """Return total bytes of core initial load files."""
    files = ["index.html", "console.js", "data.js", "repair_theatre_data.js"]
    total = 0
    for fname in files:
        f = dash_dir / fname
        if f.exists():
            total += f.stat().st_size
    return total


def get_total_dashboard_size(dash_dir: Path) -> int:
    """Return total bytes of all files in dashboard/."""
    return sum(f.stat().st_size for f in dash_dir.rglob("*") if f.is_file())


def check_site(
    repo_root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
) -> dict[str, Any]:
    """Start local server at repo parent and crawl all dashboard paths."""
    root = repo_root or ROOT
    repo_name = root.name
    dash_dir = root / "dashboard"
    parent_dir = root.parent

    # 1. Size checks
    first_load_bytes = get_first_load_size(dash_dir)
    total_dash_bytes = get_total_dashboard_size(dash_dir)

    if first_load_bytes > 2 * 1024 * 1024:
        raise ValueError(
            f"First load size {first_load_bytes / 1024 / 1024:.2f} MB exceeds 2 MB limit"
        )
    if total_dash_bytes > 25 * 1024 * 1024:
        raise ValueError(
            f"Total dashboard size {total_dash_bytes / 1024 / 1024:.2f} MB exceeds 25 MB limit"
        )

    # 2. Start ephemeral HTTP server serving parent directory
    handler = functools.partial(QuietSimpleHTTPRequestHandler, directory=str(parent_dir))
    server = socketserver.TCPServer((host, port), handler)
    assigned_port = server.server_address[1]

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://{host}:{assigned_port}/{repo_name}/dashboard"

    visited_urls: set[str] = set()
    errors: list[str] = []
    checked_count = 0

    try:
        # Fetch index.html
        index_url = f"{base_url}/index.html"
        req = urllib.request.Request(index_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="ignore")

        if status != 200:
            errors.append(f"GET {index_url} returned status {status}")
        visited_urls.add(index_url)
        checked_count += 1

        # Check for root-absolute paths in index.html
        root_abs = re.findall(r'(?:src|href|url)\s*[:=]\s*["\'](/[^"\']+)["\']', body)
        for ra in root_abs:
            if not ra.startswith(f"/{repo_name}/"):
                errors.append(f"Root-absolute path in index.html: {ra}")

        # Check external hosts in index.html
        ext_hosts = re.findall(r'https?://(?:(?!127\.0\.0\.1|localhost)[a-zA-Z0-9.-]+)', body)
        for eh in ext_hosts:
            errors.append(f"External host in index.html: {eh}")

        # Collect paths to check
        paths_to_check: set[str] = set()

        # Scripts, links, images in index.html
        for match in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', body):
            m = match.strip()
            if m.startswith(("#", "mailto:", "javascript:", "data:")):
                continue
            if re.match(r"^https?://", m):
                errors.append(f"External link in index.html: {m}")
                continue
            paths_to_check.add(m)

        # Asset paths from data.json
        data_json_path = dash_dir / "data.json"
        if data_json_path.exists():
            data = json.loads(data_json_path.read_text(encoding="utf-8"))
            # Replays clips
            for clip in data.get("replays", {}).get("clips", []):
                for f in clip.get("frames", []):
                    paths_to_check.add(f"replays/{clip['clip_id']}/{f}")

        # Asset paths from repair_theatre_data.json
        theatre_json_path = dash_dir / "repair_theatre_data.json"
        if theatre_json_path.exists():
            tdata = json.loads(theatre_json_path.read_text(encoding="utf-8"))
            for sess in tdata.get("sessions", []):
                for f in sess.get("replay_frames", []):
                    paths_to_check.add(f)

        # Test fetching every relative asset through the sub-path server
        for rel_path in sorted(paths_to_check):
            clean_rel = rel_path.split("?")[0].split("#")[0]
            if not clean_rel:
                continue

            # Verify it is not root-absolute
            if clean_rel.startswith("/"):
                errors.append(f"Asset path is root-absolute: {clean_rel}")
                continue

            full_asset_url = f"{base_url}/{clean_rel}"
            if full_asset_url in visited_urls:
                continue

            try:
                asset_req = urllib.request.Request(full_asset_url)
                with urllib.request.urlopen(asset_req, timeout=10) as a_resp:
                    a_status = a_resp.status
                    a_ctype = a_resp.headers.get("Content-Type", "")
                    if a_status != 200:
                        errors.append(f"GET {full_asset_url} status {a_status}")
                    # Basic Content-Type check
                    if clean_rel.endswith(".html") and "text/html" not in a_ctype:
                        errors.append(f"Unexpected content type for {clean_rel}: {a_ctype}")
                    elif clean_rel.endswith(".js") and not any(t in a_ctype for t in ["javascript", "text/plain"]):
                        errors.append(f"Unexpected content type for {clean_rel}: {a_ctype}")
                    elif clean_rel.endswith(".json") and not any(t in a_ctype for t in ["json", "text/plain"]):
                        errors.append(f"Unexpected content type for {clean_rel}: {a_ctype}")
                    elif clean_rel.endswith(".png") and "image/png" not in a_ctype:
                        errors.append(f"Unexpected content type for {clean_rel}: {a_ctype}")
            except Exception as exc:
                errors.append(f"Failed to fetch {full_asset_url}: {exc}")

            visited_urls.add(full_asset_url)
            checked_count += 1

    finally:
        server.shutdown()
        server.server_close()

    if errors:
        raise AssertionError(f"Site check failed with {len(errors)} error(s):\n" + "\n".join(errors))

    result = {
        "status": "PASS",
        "base_url": base_url,
        "checked_urls_count": checked_count,
        "first_load_bytes": first_load_bytes,
        "total_dashboard_bytes": total_dash_bytes,
    }
    return result


def main() -> None:
    print(f"Checking static dashboard under sub-path: /{REPO_NAME}/dashboard/ ...")
    res = check_site()
    print(f"PASS: Verified {res['checked_urls_count']} URLs via local sub-path server.")
    print(f"First-load size: {res['first_load_bytes'] / 1024:.1f} KB (<= 2 MB)")
    print(f"Total size: {res['total_dashboard_bytes'] / (1024*1024):.2f} MB (<= 25 MB)")


if __name__ == "__main__":
    main()
