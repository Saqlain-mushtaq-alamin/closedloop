"""Phase 08 unit tests for certification.

Asserts:
- test_cert_seed_once (V4): each cert seed once/program; persistent ledger prevents reuse across runs.
- test_error_budget_sum: allocations sum to delta=0.05 exact for both family and joint models.
- test_cert_recompute: independent SciPy binomtest recompute matches reported bound within 1e-9.
- test_price_plot_data: area vs labels computed from logs only (H11), sensitive to judge mutations.
- test_cost_preflight: projected full cert cost vs remaining cap blocks launch if >= headroom.
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


def test_cert_seed_once(tmp_path: Path) -> None:
    """Each cert seed used once per program (V4 / H9); persistent ledger blocks reuse across instances."""
    ledger_file = tmp_path / "ledger.json"
    ledger1 = CertificationLedger(path=ledger_file)
    prog_id = "test_prog_abc"
    seeds = [2000000, 2000001, 2000002]
    ledger1.claim(prog_id, seeds)

    # In-memory check: re-claiming same seed raises LeakageError
    with pytest.raises(LeakageError):
        ledger1.claim(prog_id, [2000002, 2000003])

    # Cross-instance persistence check (simulates second runner call):
    ledger2 = CertificationLedger(path=ledger_file)
    with pytest.raises(LeakageError):
        ledger2.claim(prog_id, [2000001])

    # Different program can claim its own certification seeds
    ledger2.claim("other_prog_xyz", [2000001])

    # Out of range seeds (<2000000 or >2999999) must raise LeakageError
    with pytest.raises(LeakageError):
        ledger2.claim(prog_id, [1999999])
    with pytest.raises(LeakageError):
        ledger2.claim(prog_id, [3000000])


def test_error_budget_sum() -> None:
    """Error budget allocations must sum to delta=0.05 exact (Plan §11)."""
    delta = 0.05
    K = 16
    B = 4
    M = 1

    # 1. Family-wise error budgets (Plan §11 / Phase 08 spec)
    budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M, joint=False)
    state_d_cell = budgets["state"]["d_cell"]
    assert math.isclose(budgets["state"]["family_sum"], delta, rel_tol=1e-12)
    assert math.isclose(state_d_cell * K * M, delta, rel_tol=1e-12)

    cam = budgets["camera"]
    d_a = cam["d_a"]
    d_b = cam["d_b"]
    d_cell = cam["d_cell"]
    assert math.isclose(cam["family_sum"], delta, rel_tol=1e-12)
    assert math.isclose(d_a + B * d_b + (K * M) * d_cell, delta, rel_tol=1e-12)
    assert math.isclose(d_a, 0.005, rel_tol=1e-12)
    assert math.isclose(d_b, 0.00125, rel_tol=1e-12)
    assert math.isclose(d_cell, 0.0025, rel_tol=1e-12)
    assert math.isclose(budgets["state"]["d_headline"], delta, rel_tol=1e-12)

    # 2. Joint simultaneous budget (simultaneous confidence across headline + state + camera certificates)
    joint_budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M, joint=True)
    total_claimed = joint_budgets["total_claimed_delta"]
    assert total_claimed <= delta + 1e-12
    assert math.isclose(total_claimed, delta, rel_tol=1e-12)


def test_cert_recompute() -> None:
    """Independent SciPy binomtest recompute matches reported bound within 1e-9 (V10)."""
    delta = 0.05
    K = 16
    B = 4
    M = 1

    budgets = compute_error_budgets(delta=delta, K=K, B=B, M=M)

    # 1. State cell recomputation: exact binomtest
    k_state = 148
    n_state = 150
    d_cell_state = budgets["state"]["d_cell"]

    reported_state = certify_state_cell(k_pass=k_state, n_cell=n_state, d_cell=d_cell_state)
    # Independent reference directly from binomtest:
    b_res = binomtest(k_state, n_state, alternative="greater")
    ci = b_res.proportion_ci(confidence_level=1.0 - d_cell_state, method="exact")
    assert math.isclose(reported_state["bound"], ci.low, abs_tol=1e-9)

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

    # Independent SciPy binomtest + beta calculation
    q_lo = float(binomtest(k_cam, n_cam, alternative="greater").proportion_ci(
        confidence_level=1.0 - d_cell_cam, method="exact"
    ).low)
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
    """Certified area vs labels data generated strictly from logs (H11), sensitive to judge mutations."""
    episodes_file = tmp_path / "episodes.jsonl"
    records = []

    # Cells 0..7: 150 passes -> certified (target 0.90 state, 0.85 camera)
    for cell_idx in range(8):
        c_id = f"cell_{cell_idx:02d}"
        for ep_idx in range(150):
            records.append({
                "episode_id": f"cert-{c_id}-ep{ep_idx:03d}",
                "stream": "certification",
                "cell_id": c_id,
                "trace_path": c_id,
                "seed": 2000000 + cell_idx * 150 + ep_idx,
                "truth_success": True,
                "truth_success_alt": True,
                "margin": 0.05,
                "judge_pass": True,
            })

    # Cells 8..15: 150 failures -> uncertified
    for cell_idx in range(8, 16):
        c_id = f"cell_{cell_idx:02d}"
        for ep_idx in range(150):
            records.append({
                "episode_id": f"cert-{c_id}-ep{ep_idx:03d}",
                "stream": "certification",
                "cell_id": c_id,
                "trace_path": c_id,
                "seed": 2000000 + cell_idx * 150 + ep_idx,
                "truth_success": False,
                "truth_success_alt": False,
                "margin": -0.05,
                "judge_pass": False,
            })

    episodes_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    plot_data = compute_price_plot_data(
        episodes_path=episodes_file,
        K=16,
        target_state_p=0.90,
        target_camera_p=0.85,
        delta=0.05,
    )

    # With perfect camera agreement on cells 00-07, state=0.5000, camera=0.5000, loss=0.0000
    assert math.isclose(plot_data["state_area_fraction"], 0.5000, abs_tol=1e-4)
    assert math.isclose(plot_data["camera_area_fraction"], 0.5000, abs_tol=1e-4)
    assert math.isclose(plot_data["price_of_footage_area_loss"], 0.0000, abs_tol=1e-4)
    assert plot_data["cells_state_certified"] == 8
    assert plot_data["cells_camera_certified"] == 8

    # Now mutate: flip judge in cell 00 to false (causing cell 00 camera bound to drop below 0.85)
    mutated_file = tmp_path / "mutated_episodes.jsonl"
    mutated_records = [dict(r) for r in records]
    for r in mutated_records:
        if r["cell_id"] == "cell_00":
            r["judge_pass"] = False

    mutated_file.write_text("\n".join(json.dumps(r) for r in mutated_records) + "\n", encoding="utf-8")
    mutated_plot = compute_price_plot_data(
        episodes_path=mutated_file,
        K=16,
        target_state_p=0.90,
        target_camera_p=0.85,
        delta=0.05,
    )

    # Non-tautological: mutating judge causes camera area to drop and price loss to rise
    assert math.isclose(mutated_plot["state_area_fraction"], 0.5000, abs_tol=1e-4)
    assert math.isclose(mutated_plot["camera_area_fraction"], 7 / 16, abs_tol=1e-4)
    assert math.isclose(mutated_plot["price_of_footage_area_loss"], 1 / 16, abs_tol=1e-4)
    assert mutated_plot["cells_camera_certified"] == 7

    # Failure accounting: missing cell_id or missing judge_pass raises ValueError (Rule H13)
    corrupted_file = tmp_path / "corrupted.jsonl"
    corrupted_file.write_text(json.dumps({"episode_id": "bad", "stream": "certification"}) + "\n")
    with pytest.raises(ValueError):
        compute_price_plot_data(corrupted_file)


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
