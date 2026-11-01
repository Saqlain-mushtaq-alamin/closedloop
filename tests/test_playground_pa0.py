"""Phase PA0 Feasibility Tests (Plan §13 PA0).

Asserts:
- /health endpoint returns valid envelope schema and sim_code_sha256.
- /selftest replays 20 certified episodes with truth equal on 20/20 and margin diff <= 1e-6 on >= 19/20.
- Simulation throughput exceeds the >= 3 episodes/second sustained target.
- playground/requirements-linux.txt pins pybullet 3.2.7 and excludes unused bloat.
- playground/Dockerfile adheres to non-root execution and security controls.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playground.server import app, compute_sim_code_sha256

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_sim_code_sha256_deterministic() -> None:
    """sim_code_sha256 is deterministic across calls."""
    h1 = compute_sim_code_sha256()
    h2 = compute_sim_code_sha256()
    assert h1 == h2
    assert len(h1) == 64
    assert h1 == "bf28d7d8a1480d480349869c6c0d775861ed5000a86cf44eeae478a1a4ac34c3"


def test_server_health_endpoint(client: TestClient) -> None:
    """GET /health returns required platform and status information."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "disabled")
    assert "enabled" in data
    assert "queue" in data
    assert "tier2" in data
    assert data["pybullet"] == "3.2.7"
    assert data["sim_code_sha256"] == compute_sim_code_sha256()
    assert "platform" in data


def test_server_selftest_reproduction(client: TestClient) -> None:
    """GET /selftest replays 20 certified episodes and verifies 20/20 truth and margin."""
    resp = client.get("/selftest")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "PASS"
    assert data["episodes_tested"] == 20
    # Gate condition: truth equal on 20/20
    assert data["truth_matches"] == 20, f"Truth matches was {data['truth_matches']}/20, expected 20/20"
    # Gate condition: margin difference <= 1e-6 on at least 19/20
    assert data["margin_matches"] >= 19, f"Margin matches was {data['margin_matches']}/20, expected >= 19/20"
    assert data["max_margin_diff"] <= 1e-6
    # Throughput target: >= 3 episodes/sec
    assert data["episodes_per_sec"] >= 3.0, f"Throughput {data['episodes_per_sec']} eps/sec below 3.0 cap"


def test_linux_requirements_file() -> None:
    """requirements-linux.txt is minimal and contains pybullet 3.2.7."""
    req_path = ROOT / "playground" / "requirements-linux.txt"
    assert req_path.exists(), "playground/requirements-linux.txt must exist"
    content = req_path.read_text(encoding="utf-8")

    assert "pybullet==3.2.7" in content
    assert "fastapi" in content
    assert "uvicorn" in content

    # Should NOT contain heavyweight non-playground packages
    assert "optuna" not in content
    assert "alembic" not in content
    assert "sqlalchemy" not in content.lower()


def test_dockerfile_security_and_non_root() -> None:
    """Dockerfile specifies non-root user and contains no secrets."""
    df_path = ROOT / "playground" / "Dockerfile"
    assert df_path.exists(), "playground/Dockerfile must exist"
    content = df_path.read_text(encoding="utf-8")

    assert "USER appuser" in content or "USER 1000" in content
    assert "EXPOSE 8000" in content
    assert "SK-" not in content.upper()
    assert "API_KEY" not in content
