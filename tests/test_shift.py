"""Tests for Phase 09: Shift Test H4 (Plan §12, PHASE_09_shift_h4.md).

Tests:
1. test_shift_config_frozen (V11): Verifies D and D' bounds, sample sizes, and config freeze hash.
2. test_shift_disjoint_seeds (V4): Verifies fresh certification seeds with zero reuse against P08.
3. test_shift_detectable_stats: Verifies sampler produces statistically distinct scenarios between D and D'.
4. test_h4_shift_refusal: Verifies D' recertified bound is lower than D bound or refuses target (Plan H4).
5. test_shift_figure_data (Rule H11): Verifies figure data generation from raw log records.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest
import yaml

from closedloop.data.sampler import (
    CertificationLedger,
    LeakageError,
    sample,
    STREAM_RANGES,
)

ROOT = Path(__file__).resolve().parent.parent


def test_shift_config_frozen() -> None:
    """V11: D' and sample sizes defined and frozen in config before run."""
    cfg_path = ROOT / "configs" / "shift.yaml"
    assert cfg_path.exists(), "configs/shift.yaml must exist"

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert cfg.get("experiment") == "shift"
    assert "bounds_d" in cfg, "Reference distribution D bounds missing"
    assert "bounds_d_prime" in cfg, "Shifted distribution D' bounds missing"

    # Verify D' is wider/heavier, lower friction per Plan §12 and Phase 09 spec
    d = cfg["bounds_d"]
    dp = cfg["bounds_d_prime"]

    # Wider pose
    assert dp["x"][1] - dp["x"][0] > d["x"][1] - d["x"][0], "D' x range must be wider"
    assert dp["y"][1] - dp["y"][0] > d["y"][1] - d["y"][0], "D' y range must be wider"

    # Heavier mass
    assert dp["mass"][0] > d["mass"][0], "D' mass min must be heavier"
    assert dp["mass"][1] > d["mass"][1], "D' mass max must be heavier"

    # Lower friction
    assert dp["friction"][1] < d["friction"][1], "D' friction max must be lower"

    # Sample sizes and seeds defined
    assert "sample_sizes" in cfg
    assert cfg["sample_sizes"]["pilot_runs"] >= 20
    assert cfg["sample_sizes"]["full_runs"] >= 100
    assert "seeds" in cfg
    assert cfg["seeds"]["pilot_seed_base"] >= 2000000
    assert cfg["seeds"]["full_seed_base"] >= 2000000

    # Config hash utility works
    from closedloop.data import manifest as run_manifest
    pricing_file = ROOT / "configs" / "pricing.yaml"
    tasks_file = ROOT / "configs" / "tasks.yaml"
    c_hash = run_manifest.config_hash([cfg_path, pricing_file, tasks_file])
    assert len(c_hash) == 16


def test_shift_disjoint_seeds() -> None:
    """V4: D' evaluation uses fresh seeds in certification stream, strictly no reuse.

    Builds the Phase 08 seed set from an independent source (configs/cert.yaml planned ranges),
    not the mutable ledger.
    """
    shift_cfg_path = ROOT / "configs" / "shift.yaml"
    cert_cfg_path = ROOT / "configs" / "cert.yaml"
    if not shift_cfg_path.exists():
        pytest.fail("configs/shift.yaml missing")
    if not cert_cfg_path.exists():
        pytest.fail("configs/cert.yaml missing")

    shift_cfg = yaml.safe_load(shift_cfg_path.read_text(encoding="utf-8"))
    pilot_base = int(shift_cfg["seeds"]["pilot_seed_base"])
    full_base = int(shift_cfg["seeds"]["full_seed_base"])
    n_pilot = int(shift_cfg["sample_sizes"]["pilot_runs"])
    n_full = int(shift_cfg["sample_sizes"]["full_runs"])

    pilot_set = set(range(pilot_base, pilot_base + n_pilot))
    full_set = set(range(full_base, full_base + n_full))
    shift_seeds = pilot_set | full_set

    # All seeds must be in certification stream [2000000, 2999999] (Rule H9)
    lo, hi = STREAM_RANGES["certification"]
    for s in shift_seeds:
        assert lo <= s <= hi, f"Seed {s} outside certification range [{lo}, {hi}]"

    # Pilot and full seeds must be mutually disjoint
    assert pilot_set.isdisjoint(full_set), "Pilot and full seeds must not overlap"

    # Build Phase 08 seed set from configs/cert.yaml independent planned ranges
    cert_cfg = yaml.safe_load(cert_cfg_path.read_text(encoding="utf-8"))
    p08_cell_base = int(cert_cfg["seeds"]["cell_seed_base"])
    p08_cell_count = int(cert_cfg["sample_sizes"]["runs_per_cell"]) * int(cert_cfg.get("K", 16))
    p08_headline_base = int(cert_cfg["seeds"]["headline_seed_base"])
    p08_headline_count = int(cert_cfg["sample_sizes"]["headline_runs"])
    p08_pilot_base = int(cert_cfg["seeds"]["pilot_seed_base"])
    p08_pilot_count = int(cert_cfg["sample_sizes"]["pilot_runs_per_cell"])

    p08_cell_set = set(range(p08_cell_base, p08_cell_base + p08_cell_count))
    p08_headline_set = set(range(p08_headline_base, p08_headline_base + p08_headline_count))
    p08_pilot_set = set(range(p08_pilot_base, p08_pilot_base + p08_pilot_count))
    p08_seeds = p08_cell_set | p08_headline_set | p08_pilot_set

    # Vacuity guards: assert P08 set is non-empty and its size equals planned count from config
    planned_p08_count = p08_cell_count + p08_headline_count + p08_pilot_count
    assert len(p08_seeds) > 0, "Phase 08 planned seed set must not be empty"
    assert len(p08_seeds) == planned_p08_count, (
        f"Phase 08 planned seed count {len(p08_seeds)} != {planned_p08_count}"
    )

    # Shift set must be completely disjoint from the Phase 08 set
    assert shift_seeds.isdisjoint(p08_seeds), (
        f"Shift seeds overlap with Phase 08 planned seeds: {shift_seeds.intersection(p08_seeds)}"
    )


def test_shift_vs_logged_p08_seeds() -> None:
    """Read the real episodes.jsonl of Phase 08 certification run(s) and of shift-full-01;
    assert both are non-empty and disjoint.
    """
    p08_file = ROOT / "runs" / "cert-full-01" / "episodes.jsonl"
    shift_file = ROOT / "runs" / "shift-full-01" / "episodes.jsonl"

    if not p08_file.exists():
        pytest.skip("runs/cert-full-01/episodes.jsonl does not exist")
    if not shift_file.exists():
        pytest.skip("runs/shift-full-01/episodes.jsonl does not exist")

    p08_logged_seeds: set[int] = set()
    with p08_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                p08_logged_seeds.add(int(json.loads(line.strip())["seed"]))

    # Include pilot if present
    p08_pilot_file = ROOT / "runs" / "cert-pilot-01" / "episodes.jsonl"
    if p08_pilot_file.exists():
        with p08_pilot_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    p08_logged_seeds.add(int(json.loads(line.strip())["seed"]))

    shift_logged_seeds: set[int] = set()
    with shift_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                shift_logged_seeds.add(int(json.loads(line.strip())["seed"]))

    # Assert both are non-empty and disjoint
    assert len(p08_logged_seeds) > 0, "P08 logged seeds must be non-empty"
    assert len(shift_logged_seeds) > 0, "Shift logged seeds must be non-empty"
    assert p08_logged_seeds.isdisjoint(shift_logged_seeds), (
        f"Logged shift seeds overlap with logged P08 seeds: {p08_logged_seeds.intersection(shift_logged_seeds)}"
    )


def test_ledger_rejects_reclaim(tmp_path: Path) -> None:
    """Use a TEMP ledger file (pytest tmp_path), claim seeds for a program,
    then try to claim an overlapping set; assert the ledger raises.
    """
    temp_ledger = tmp_path / "temp_ledger.json"
    ledger = CertificationLedger(path=temp_ledger)
    prog_id = "test_prog_reclaim_check"

    # Valid claim
    ledger.claim(prog_id, [2500000, 2500001, 2500002])

    # Overlapping claim must raise LeakageError
    with pytest.raises(LeakageError):
        ledger.claim(prog_id, [2500002, 2500003])


def test_shift_seeds_in_ledger_after_run() -> None:
    """If runs/shift-full-01 exists, assert every shift seed is recorded in the real ledger."""
    shift_run_dir = ROOT / "runs" / "shift-full-01"
    if not shift_run_dir.exists():
        pytest.skip("runs/shift-full-01 does not exist yet")

    ledger_path = ROOT / "runs" / ".certification_ledger.json"
    assert ledger_path.exists(), "runs/.certification_ledger.json must exist"

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    shift_cfg = yaml.safe_load((ROOT / "configs" / "shift.yaml").read_text(encoding="utf-8"))
    prog_id = shift_cfg["program_id"]

    assert prog_id in data, f"Program {prog_id} not recorded in ledger"
    claimed = set(data[prog_id])

    full_base = int(shift_cfg["seeds"]["full_seed_base"])
    n_full = int(shift_cfg["sample_sizes"]["full_runs"])
    full_seeds = set(range(full_base, full_base + n_full))

    assert full_seeds.issubset(claimed), (
        f"Not all full shift seeds found in ledger: missing {full_seeds - claimed}"
    )


def test_shift_detectable_stats() -> None:
    """Gate requirement: STOP if shift not detectable in scenario stats (sampler bug)."""
    cfg_path = ROOT / "configs" / "shift.yaml"
    if not cfg_path.exists():
        pytest.fail("configs/shift.yaml missing")

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    bounds_d = {k: tuple(v) for k, v in cfg["bounds_d"].items()}
    bounds_dp = {k: tuple(v) for k, v in cfg["bounds_d_prime"].items()}

    n = 200
    # Use temporary test seeds in certification stream
    scenarios_d = sample("certification", n=n, seed=2900000, bounds=bounds_d)
    scenarios_dp = sample("certification", n=n, seed=2901000, bounds=bounds_dp)

    masses_d = np.array([s["mass"] for s in scenarios_d])
    masses_dp = np.array([s["mass"] for s in scenarios_dp])
    frictions_d = np.array([s["friction"] for s in scenarios_d])
    frictions_dp = np.array([s["friction"] for s in scenarios_dp])

    # Mass shift must be significantly positive (mean shift >= 2.0 kg)
    mass_diff = float(np.mean(masses_dp) - np.mean(masses_d))
    assert mass_diff >= 2.0, f"Mass shift not detected: {mass_diff:.3f} kg < 2.0 kg"

    # Friction shift must be significantly negative (mean shift <= -0.15)
    fric_diff = float(np.mean(frictions_dp) - np.mean(frictions_d))
    assert fric_diff <= -0.15, f"Friction shift not detected: {fric_diff:.3f} > -0.15"

    # Distribution shift must be detectable via two-sample Kolmogorov-Smirnov test
    from scipy.stats import ks_2samp
    ks_mass = ks_2samp(masses_d, masses_dp)
    ks_fric = ks_2samp(frictions_d, frictions_dp)
    assert ks_mass.pvalue < 1e-6, "Mass distribution shift not statistically significant"
    assert ks_fric.pvalue < 1e-6, "Friction distribution shift not statistically significant"


def test_h4_shift_refusal() -> None:
    """H4: D' recertified bound < D bound or refusal (below target)."""
    from closedloop.certify import stats
    from closedloop.certify.shift import compare_shift_bounds

    # Scenario: Program has high success on D, but fails on heavier D'
    # Certified region on D: 150/150, delta=0.003125 -> p_L = 0.9623 >= 0.90
    d_pass = 150
    d_total = 150
    d_bound = stats.cp_lower(d_pass, d_total, 0.003125)
    assert d_bound >= 0.90

    # On D' with heavy mass slip: e.g. 30/150 pass
    dp_pass = 30
    dp_total = 150
    dp_bound = stats.cp_lower(dp_pass, dp_total, 0.003125)

    comp = compare_shift_bounds(
        d_bound=d_bound,
        dp_pass=dp_pass,
        dp_total=dp_total,
        delta=0.003125,
        target_p=0.90,
    )
    assert comp["bound_dropped"] is True
    assert comp["dp_bound"] < comp["d_bound"]
    assert comp["certified_on_dp"] is False
    assert comp["refusal"] is True


def test_shift_figure_data_schema(tmp_path: Path) -> None:
    """Rule H11: Shift figure data is computed strictly from logs."""
    from closedloop.certify.shift import generate_shift_figure_data

    # Create dummy episodes.jsonl with D and D' runs
    ep_file = tmp_path / "episodes.jsonl"
    episodes = [
        {"episode_id": f"d_{i}", "distribution": "D", "truth_success": i < 80}
        for i in range(100)
    ] + [
        {"episode_id": f"dp_{i}", "distribution": "D_prime", "truth_success": i < 20}
        for i in range(100)
    ]
    with ep_file.open("w", encoding="utf-8") as f:
        for ep in episodes:
            f.write(json.dumps(ep) + "\n")

    fig_data = generate_shift_figure_data(
        episodes_path=ep_file,
        d_bound=0.70,
        delta=0.05,
        target_p=0.90,
    )
    assert "d_empirical_pass_rate" in fig_data
    assert "dp_empirical_pass_rate" in fig_data
    assert "dp_recertified_bound" in fig_data
    assert "d_bound" in fig_data
    assert fig_data["dp_empirical_pass_rate"] == pytest.approx(0.20, abs=1e-3)
    assert fig_data["d_empirical_pass_rate"] == pytest.approx(0.80, abs=1e-3)
    assert fig_data["dp_recertified_bound"] < fig_data["d_bound"]
