"""Phase 08 unit tests for certification (written first).

Asserts:
- test_cert_seed_once (V4): each cert seed once/program; reuse raises LeakageError
- test_error_budget_sum: allocations sum to delta=0.05 exact
- test_cert_recompute: independent SciPy recompute matches reported bound within 1e-9
- test_price_plot_data: area vs labels computed from logs only (H11)
- test_cost_preflight: projected full cert cost vs remaining cap blocks launch if >= headroom
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import pytest
from scipy.stats import beta, binomtest

from closedloop.data.sampler import CertificationLedger, LeakageError
from closedloop.certify.certify import (
    compute_error_budgets,
    certify_state_cell,
    certify_camera_cell,
    certify_headline,
    recompute_cell_bound,
    compute_price_plot_data,
    preflight_cert_cost,
    BudgetPreflightError,
    CertificationConfig,
)


def test_cert_seed_once() -> None:
    """Each cert seed used once per program (V4 / H9); reuse raises LeakageError."""
    ledger = CertificationLedger()
    prog_id = "test_prog_abc"
    seeds = [2000000, 2000001, 2000002]
    ledger.claim(prog_id, seeds)

    # Re-claiming any seed for the same program must raise LeakageError
    with pytest.raises(LeakageError):
        ledger.claim(prog_id, [2000002, 2000003])

    # Out of range seeds (<2000000 or >2999999) must raise LeakageError
    with pytest.raises(LeakageError):
        ledger.claim(prog_id, [1999999])
    with pytest.raises(LeakageError):
        ledger.claim(prog_id, [3000000])


def test_error_budget_sum() -> None:
    """Error budget allocations must sum to delta=0.05 exact (Plan §11)."""
    delta = 0.05
    K = 16
    B = 4
    M = 1

    budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M)

    # State mode budget: delta / (K * M)
    state_d_cell = budgets["state"]["d_cell"]
    assert math.isclose(state_d_cell * K * M, delta, rel_tol=1e-12)

    # Camera mode budget:
    # d_a = 0.1 * delta
    # d_b = 0.1 * delta / B (per bucket)
    # d_cell = 0.8 * delta / (K * M)
    # Total = d_a + B * d_b + (K * M) * d_cell == delta
    cam = budgets["camera"]
    d_a = cam["d_a"]
    d_b = cam["d_b"]
    d_cell = cam["d_cell"]
    total_camera_error = d_a + B * d_b + (K * M) * d_cell
    assert math.isclose(total_camera_error, delta, rel_tol=1e-12)
    assert math.isclose(d_a, 0.005, rel_tol=1e-12)
    assert math.isclose(d_b, 0.00125, rel_tol=1e-12)
    assert math.isclose(d_cell, 0.0025, rel_tol=1e-12)


def test_cert_recompute() -> None:
    """Independent SciPy recompute matches reported bound within 1e-9 (V10)."""
    delta = 0.05
    K = 16
    B = 4
    M = 1

    budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M)

    # 1. State cell recomputation: exact binomtest / beta.ppf
    k_state = 148
    n_state = 150
    d_cell_state = budgets["state"]["d_cell"]

    reported_state = certify_state_cell(k_pass=k_state, n_cell=n_state, d_cell=d_cell_state)
    scipy_exact = float(beta.ppf(d_cell_state, k_state, n_state - k_state + 1))
    assert math.isclose(reported_state["bound"], scipy_exact, abs_tol=1e-9)

    # Independent check via recompute_cell_bound
    recomputed_state = recompute_cell_bound(mode="state", result_dict=reported_state, d_cell=d_cell_state)
    assert math.isclose(recomputed_state, reported_state["bound"], abs_tol=1e-9)

    # 2. Camera cell recomputation: exact corrected bound
    k_cam = 145
    n_cam = 150
    k_a = 300
    n_a = 300
    k_b = 2
    n_b = 100
    d_a = budgets["camera"]["d_a"]
    d_b = budgets["camera"]["d_b"]
    d_cell_cam = budgets["camera"]["d_cell"]

    reported_cam = certify_camera_cell(
        k_pass=k_cam,
        n_cell=n_cam,
        k_a=k_a,
        n_a=n_a,
        k_b=k_b,
        n_b=n_b,
        d_a=d_a,
        d_b=d_b,
        d_cell=d_cell_cam,
    )

    q_lo = float(beta.ppf(d_cell_cam, k_cam, n_cam - k_cam + 1))
    a_hi = 1.0 if k_a == n_a else float(beta.ppf(1 - d_a, k_a + 1, n_a - k_a))
    b_hi = 1.0 if k_b == n_b else float(beta.ppf(1 - d_b, k_b + 1, n_b - k_b))
    expected_cam_bound = min(1.0, (q_lo - b_hi) / (a_hi - b_hi))
    assert math.isclose(reported_cam["bound"], expected_cam_bound, abs_tol=1e-9)

    recomputed_cam = recompute_cell_bound(
        mode="camera",
        result_dict=reported_cam,
        d_cell=d_cell_cam,
        k_a=k_a,
        n_a=n_a,
        k_b=k_b,
        n_b=n_b,
        d_a=d_a,
        d_b=d_b,
    )
    assert math.isclose(recomputed_cam, reported_cam["bound"], abs_tol=1e-9)


def test_price_plot_data(tmp_path: Path) -> None:
    """Certified area vs labels data generated strictly from logs (H11)."""
    # Create synthetic episodes.jsonl log with 16 cells * 10 episodes
    episodes_file = tmp_path / "episodes.jsonl"
    records = []
    for cell_idx in range(16):
        for ep_idx in range(10):
            records.append({
                "episode_id": f"cert-cell{cell_idx:02d}-ep{ep_idx:02d}",
                "stream": "certification",
                "cell_id": f"cell_{cell_idx:02d}",
                "seed": 2000000 + cell_idx * 10 + ep_idx,
                "truth_success": True,
                "truth_success_alt": True,
                "margin": 0.05,
                "judge_pass": True,
            })
    episodes_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    plot_data = compute_price_plot_data(
        episodes_path=episodes_file,
        K=16,
        target_state_p=0.90,
        target_camera_p=0.85,
        delta=0.05,
    )

    assert "state_area_fraction" in plot_data
    assert "camera_area_fraction" in plot_data
    assert "price_of_footage_area_loss" in plot_data
    assert "episodes_analyzed" in plot_data
    assert plot_data["episodes_analyzed"] == 160
    # Camera certified area cannot exceed state certified area (Plan / Phase 08)
    assert plot_data["camera_area_fraction"] <= plot_data["state_area_fraction"] + 1e-9
    assert plot_data["price_of_footage_area_loss"] >= -1e-9


def test_cost_preflight() -> None:
    """Projected cert cost vs remaining budget blocks launch if >= headroom (H5)."""
    # Remaining headroom is $4.00
    remaining_budget = 4.00

    # Case 1: Pilot metering shows $0.001 per episode, 150 episodes planned -> $0.15 cost.
    # Safe to proceed.
    res_safe = preflight_cert_cost(
        pilot_cost_usd=0.015,
        pilot_episodes=15,
        total_planned_episodes=150,
        remaining_budget_usd=remaining_budget,
    )
    assert res_safe["can_proceed"] is True
    assert math.isclose(res_safe["projected_cost_usd"], 0.15, abs_tol=1e-5)

    # Case 2: Pilot shows expensive calls: $0.50 for 10 episodes -> $5.00 for 100 episodes.
    # Exceeds $4.00 headroom -> must raise BudgetPreflightError.
    with pytest.raises(BudgetPreflightError):
        preflight_cert_cost(
            pilot_cost_usd=0.50,
            pilot_episodes=10,
            total_planned_episodes=100,
            remaining_budget_usd=remaining_budget,
        )
