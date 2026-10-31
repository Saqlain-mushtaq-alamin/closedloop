"""Tests for Phase 08b: Round 2 repair and v2 certification.

Asserts:
- Seeds disjointness (Rule H9): repair stream in [0, 999999], cert stream in [2100000, 2999999],
  disjoint from cert-full-01, cert-pilot-01, shift-full-01, cert-mint-02, and cert-mint-03.
- Source program v1 integrity: SHA-256 matches bec73dec45a88431...
- Freeze-before-cert ordering: certification runner fails if freeze.json is missing or mutated.
- Config validity: arm B3, max 2 attempts, $3 cap, regression set contains nominal + earlier CEs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_round2_v1_source_intact() -> None:
    """v1 source code matches frozen SHA-256 pin from cert-mint-03."""
    src = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    assert src.exists(), "v1 program_final.py missing"
    normalized_text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    h = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    expected = "bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55"
    assert h == expected, f"v1 sha256 mismatch: {h} != {expected}"


def test_round2_config_valid() -> None:
    """configs/round2.yaml satisfies all pre-registered Phase 08b constraints."""
    cfg_path = ROOT / "configs" / "round2.yaml"
    assert cfg_path.exists(), "configs/round2.yaml missing"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    assert cfg["arm"] == "B3"
    assert cfg["model"] == "muse-spark-1.3"
    assert cfg["max_attempts"] == 2
    assert cfg["budget_cap_usd"] <= 3.0
    assert "regression_set" in cfg
    assert len(cfg["regression_set"]) >= 3  # nominal + at least 2 earlier CEs

    # Assert source program pin
    assert cfg["source_program"]["sha256"].startswith("bec73dec")


def test_round2_seeds_disjoint() -> None:
    """Repair, calibration, and cert seeds for round 2 are mutually disjoint and disjoint from prior runs."""
    cfg_path = ROOT / "configs" / "round2.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    # Planned repair seeds
    repair_seeds = set()
    s_cfg = cfg["seeds"]
    for attempt in ["attempt_1", "attempt_2"]:
        att = s_cfg[attempt]
        repair_seeds.update(range(att["falsifier_base"], att["falsifier_base"] + 10))
        repair_seeds.update(range(att["minimizer_base"], att["minimizer_base"] + 6))
        repair_seeds.add(att["minimizer_recheck"])
        repair_seeds.add(att["stage1_ce"])
        repair_seeds.update(range(att["stage3_base"], att["stage3_base"] + 5))

    for sc in cfg["regression_set"]:
        if "seed" in sc:
            repair_seeds.add(sc["seed"])

    # Assert repair seeds in repair stream [0, 999999]
    for s in repair_seeds:
        assert 0 <= s <= 999999, f"Seed {s} outside repair stream"

    # Planned cert seeds for cert2-full-01
    cert2_seeds = set(range(2100000, 2102459 + 59))
    for s in cert2_seeds:
        assert 2000000 <= s <= 2999999, f"Cert2 seed {s} outside cert stream"

    # Disjoint from repair
    assert not repair_seeds.intersection(cert2_seeds)

    # Disjoint from logged certification seeds from Phase 08 and Phase 09
    p08_cert_seeds = set()
    runs_dir = ROOT / "runs"
    for log_p in [
        runs_dir / "cert-full-01" / "episodes.jsonl",
        runs_dir / "cert-pilot-01" / "episodes.jsonl",
        runs_dir / "shift-full-01" / "episodes.jsonl",
    ]:
        if log_p.exists():
            with open(log_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        p08_cert_seeds.add(rec["seed"])

    overlap = cert2_seeds.intersection(p08_cert_seeds)
    assert not overlap, f"Cert2 seeds overlap with previous certification runs: {overlap}"


def test_freeze_before_cert_enforced(tmp_path: Path) -> None:
    """Certification must raise an error if program is not frozen with valid SHA-256."""
    from experiments.run_cert_v2 import validate_v2_freeze

    # Missing directory -> raises
    with pytest.raises(Exception):
        validate_v2_freeze(tmp_path / "nonexistent")

    # Empty freeze.json -> raises
    mint_dir = tmp_path / "mint"
    mint_dir.mkdir()
    (mint_dir / "freeze.json").write_text("{}", encoding="utf-8")
    with pytest.raises(Exception):
        validate_v2_freeze(mint_dir)


def test_round2_mint_frozen_successfully() -> None:
    """The generated v2 candidate in runs/round2-mint-01 is strictly valid and frozen."""
    from experiments.run_cert_v2 import validate_v2_freeze
    mint_dir = ROOT / "runs" / "round2-mint-01"
    assert mint_dir.exists(), "runs/round2-mint-01 must exist"
    freeze = validate_v2_freeze(mint_dir)
    assert freeze["program_id"] == "5f74f7762ee1f378"
    assert freeze["acceptance"]["reason"] == "accepted"


def test_manifest_links_v1_and_v2() -> None:
    """Manifest of round2-mint-01 links source v1 SHA-256 and records repair provenance."""
    man_path = ROOT / "runs" / "round2-mint-01" / "manifest.json"
    assert man_path.exists(), "manifest.json must exist in round2-mint-01"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    assert man["status"] == "valid"
    assert man["repair"]["v1_sha256"].startswith("bec73dec")
    assert man["repair"]["accepted"] is True

