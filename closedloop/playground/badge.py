"""Certificate Registry and Badge Evaluation Logic (Plan §6.3, §13 PA1).

Enforces the core correctness rule:
A certificate binds to (program hash, robot preset, task bounds, sim code hash).
Never hash alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_CERTIFICATES: list[dict[str, Any]] = [
    {
        "cert_id": "cert-full-01",
        "run_id": "cert-full-01",
        "program_id": "bec73dec45a88431",
        "program_sha256": "bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55",
        "robot_preset": "certified_default",
        "task_preset": "mixed_bin",
        "task_bounds": {
            "mass": [1.0, 11.5],
            "friction": [0.1, 1.0],
            "x": [-0.15, 0.15],
            "y": [-0.15, 0.15],
            "yaw": [-0.5, 0.5],
        },
        "delta": 0.05,
        "target_p_cell": 0.90,
        "sim_code_sha256": "bf28d7d8a1480d480349869c6c0d775861ed5000a86cf44eeae478a1a4ac34c3",
        "evidence_platform": "win_amd64",
        "config_hash": "fa1421c3101bc93a",
    },
    {
        "cert_id": "cert2-full-01",
        "run_id": "cert2-full-01",
        "program_id": "5f74f7762ee1f378",
        "program_sha256": "5f74f7762ee1f378b2d71f6938a288fa12aa51a0ee93ee33a2639944cd66aaa1",
        "robot_preset": "certified_default",
        "task_preset": "mixed_bin",
        "task_bounds": {
            "mass": [1.0, 11.5],
            "friction": [0.1, 1.0],
            "x": [-0.15, 0.15],
            "y": [-0.15, 0.15],
            "yaw": [-0.5, 0.5],
        },
        "delta": 0.05,
        "target_p_cell": 0.90,
        "sim_code_sha256": "bf28d7d8a1480d480349869c6c0d775861ed5000a86cf44eeae478a1a4ac34c3",
        "evidence_platform": "win_amd64",
        "config_hash": "c07fb1f819a557a6",
    },
]


def load_registry(data_json_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load certificate registry from dashboard/data.json or fallback to defaults."""
    path = Path(data_json_path) if data_json_path is not None else ROOT / "dashboard" / "data.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "certificates" in data and isinstance(data["certificates"], list) and len(data["certificates"]) > 0:
                return data["certificates"]
        except Exception:
            pass
    return list(DEFAULT_CERTIFICATES)


def evaluate_badge(
    code_sha256: str,
    robot_preset: str,
    task_preset: str,
    sim_code_sha256: str,
    certificates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate certificate badge status according to Plan §6.3 rules.

    Returns:
        Dictionary with status ('CERTIFIED' | 'VOID_SETUP' | 'VOID'), badge label, and message.
    """
    certs = certificates if certificates is not None else DEFAULT_CERTIFICATES

    # 1. Exact match on hash, robot, task, and simulator code hash
    for cert in certs:
        if (
            cert.get("program_sha256") == code_sha256
            and cert.get("robot_preset") == robot_preset
            and cert.get("task_preset") == task_preset
            and cert.get("sim_code_sha256") == sim_code_sha256
        ):
            return {
                "status": "CERTIFIED",
                "badge": "CERTIFIED",
                "badge_class": "badge-pill-pass",
                "message": (
                    f"Certified in simulation under distribution D (Run ID: {cert['cert_id']}, "
                    f"evidence platform: {cert.get('evidence_platform', 'win_amd64')})."
                ),
                "cert_id": cert["cert_id"],
                "evidence_platform": cert.get("evidence_platform", "win_amd64"),
            }

    # 2. Program hash matches a certificate, but robot, task, or environment differs
    for cert in certs:
        if cert.get("program_sha256") == code_sha256:
            reasons = []
            if cert.get("robot_preset") != robot_preset:
                reasons.append(f"robot '{robot_preset}' != certified '{cert.get('robot_preset')}'")
            if cert.get("task_preset") != task_preset:
                reasons.append(f"task '{task_preset}' != certified '{cert.get('task_preset')}'")
            if cert.get("sim_code_sha256") != sim_code_sha256:
                reasons.append("simulator code hash differs from evidence run")

            reason_str = ", ".join(reasons)
            return {
                "status": "VOID_SETUP",
                "badge": "VOID FOR THIS SETUP",
                "badge_class": "badge-pill-warn",
                "message": f"This program has a certificate ({cert['cert_id']}), but not for this setup: {reason_str}.",
                "cert_id": cert["cert_id"],
                "evidence_platform": cert.get("evidence_platform", "win_amd64"),
            }

    # 3. No certificate found for this program hash
    return {
        "status": "VOID",
        "badge": "VOID",
        "badge_class": "badge-pill-fail",
        "message": "This code has no certificate. Re-certify.",
        "cert_id": None,
        "evidence_platform": None,
    }


def generate_test_vectors() -> list[dict[str, Any]]:
    """Generate shared test vectors for verifying Python and JS implementations agree."""
    h_v1 = "bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55"
    h_v2 = "5f74f7762ee1f378b2d71f6938a288fa12aa51a0ee93ee33a2639944cd66aaa1"
    sim_h = "bf28d7d8a1480d480349869c6c0d775861ed5000a86cf44eeae478a1a4ac34c3"
    unknown_h = "0000000000000000000000000000000000000000000000000000000000000000"

    vectors = [
        # v1 exact match
        {"code_sha256": h_v1, "robot_preset": "certified_default", "task_preset": "mixed_bin", "sim_code_sha256": sim_h, "expected_status": "CERTIFIED", "expected_badge": "CERTIFIED"},
        # v1 with 100N gripper
        {"code_sha256": h_v1, "robot_preset": "gripper_100N", "task_preset": "mixed_bin", "sim_code_sha256": sim_h, "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # v1 with 200N gripper
        {"code_sha256": h_v1, "robot_preset": "gripper_200N", "task_preset": "mixed_bin", "sim_code_sha256": sim_h, "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # v1 with heavy task
        {"code_sha256": h_v1, "robot_preset": "certified_default", "task_preset": "heavy_parts", "sim_code_sha256": sim_h, "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # v1 with light task
        {"code_sha256": h_v1, "robot_preset": "certified_default", "task_preset": "light_parts", "sim_code_sha256": sim_h, "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # v1 with modified sim hash
        {"code_sha256": h_v1, "robot_preset": "certified_default", "task_preset": "mixed_bin", "sim_code_sha256": "1111111111111111111111111111111111111111111111111111111111111111", "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # v2 exact match
        {"code_sha256": h_v2, "robot_preset": "certified_default", "task_preset": "mixed_bin", "sim_code_sha256": sim_h, "expected_status": "CERTIFIED", "expected_badge": "CERTIFIED"},
        # v2 with 100N gripper
        {"code_sha256": h_v2, "robot_preset": "gripper_100N", "task_preset": "mixed_bin", "sim_code_sha256": sim_h, "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # v2 with heavy task
        {"code_sha256": h_v2, "robot_preset": "certified_default", "task_preset": "heavy_parts", "sim_code_sha256": sim_h, "expected_status": "VOID_SETUP", "expected_badge": "VOID FOR THIS SETUP"},
        # unknown program
        {"code_sha256": unknown_h, "robot_preset": "certified_default", "task_preset": "mixed_bin", "sim_code_sha256": sim_h, "expected_status": "VOID", "expected_badge": "VOID"},
        # unknown program with 100N
        {"code_sha256": unknown_h, "robot_preset": "gripper_100N", "task_preset": "heavy_parts", "sim_code_sha256": sim_h, "expected_status": "VOID", "expected_badge": "VOID"},
    ]
    return vectors
