"""Certification module for ClosedLoop (Plan §11, Phase 08).

Implements:
- Exact Clopper-Pearson state certification (cp_lower).
- Corrected camera judge certification (corrected_lower).
- Error budget allocation summing to delta=0.05.
- Headline single certificate and 4x4 mass x friction heatmaps.
- Safe seed claiming via CertificationLedger (Rule H9).
- Price of footage area loss calculation from logs only (Rule H11).
- Cost pre-flight metering and headroom check (Rule H5).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from closedloop.data.sampler import CertificationLedger, sample, LeakageError, sample_certification


class BudgetPreflightError(RuntimeError):
    """Raised when projected certification cost exceeds remaining budget headroom."""


@dataclass(frozen=True)
class CertificationConfig:
    """Frozen configuration parameters for Phase 08 certification."""
    delta: float = 0.05
    K: int = 16
    B: int = 4
    M: int = 1
    runs_per_cell: int = 150
    headline_runs: int = 59
    target_headline_p: float = 0.95
    target_state_cell_p: float = 0.90
    target_camera_cell_p: float = 0.85
    seed_base: int = 2000000


def compute_error_budgets(
    delta: float = 0.05,
    K: int = 16,
    B: int = 4,
    M: int = 1,
    joint: bool = False,
) -> dict[str, Any]:
    """Compute exact error budget splits for state and camera certification.

    By default (Plan §11 / Phase 08 spec):
    - State mode family: d_cell = delta / (K * M). Sum over K*M cells = delta.
    - Camera mode family:
        d_a = 0.1 * delta
        d_b = (0.1 * delta) / B  (per bucket)
        d_cell = (0.8 * delta) / (K * M)
        Check: d_a + B * d_b + (K * M) * d_cell == delta.
    - Headline single certificate: evaluated on full distribution D with undivided delta.

    If joint=True (simultaneous confidence across headline + state + camera certificates):
        Allocates delta across all claimed certificate families such that their sum <= delta.
    """
    if joint:
        # 3 families: headline, state heatmap, camera heatmap
        family_delta = delta / 3.0
        state_d_cell = family_delta / (K * M)
        cam_d_a = 0.1 * family_delta
        cam_d_b = (0.1 * family_delta) / B
        cam_d_cell = (0.8 * family_delta) / (K * M)
        d_head = family_delta
    else:
        state_d_cell = delta / (K * M)
        cam_d_a = 0.1 * delta
        cam_d_b = (0.1 * delta) / B
        cam_d_cell = (0.8 * delta) / (K * M)
        d_head = delta

    return {
        "delta": float(delta),
        "K": int(K),
        "B": int(B),
        "M": int(M),
        "joint": bool(joint),
        "state": {
            "d_cell": float(state_d_cell),
            "d_headline": float(d_head),
            "family_sum": float(state_d_cell * K * M),
        },
        "camera": {
            "d_a": float(cam_d_a),
            "d_b": float(cam_d_b),
            "d_cell": float(cam_d_cell),
            "d_headline": float(0.8 * d_head),
            "family_sum": float(cam_d_a + B * cam_d_b + (K * M) * cam_d_cell),
        },
        "total_claimed_delta": float(
            d_head + (state_d_cell * K * M) + (cam_d_a + B * cam_d_b + (K * M) * cam_d_cell)
        ),
    }



def certify_state_cell(
    k_pass: int,
    n_cell: int,
    d_cell: float,
    target_p: float = 0.90,
) -> dict[str, Any]:
    """Compute one-sided Clopper-Pearson lower bound for a single state cell."""
    from closedloop.certify import stats
    bound = stats.cp_lower(k_pass, n_cell, d_cell)
    return {
        "mode": "state",
        "k_pass": int(k_pass),
        "n_cell": int(n_cell),
        "d_cell": float(d_cell),
        "bound": float(bound),
        "target_p": float(target_p),
        "certified": bool(bound >= target_p),
    }


def certify_camera_cell(
    k_pass: int,
    n_cell: int,
    k_a: int,
    n_a: int,
    k_b: int,
    n_b: int,
    d_a: float,
    d_b: float,
    d_cell: float,
    target_p: float = 0.85,
) -> dict[str, Any]:
    """Compute corrected lower bound for a noisy vision judge on a single camera cell."""
    from closedloop.certify import stats
    bound = stats.corrected_lower(
        k_pass=k_pass,
        n_cell=n_cell,
        k_a=k_a,
        n_a=n_a,
        k_b=k_b,
        n_b=n_b,
        d_a=d_a,
        d_b=d_b,
        d_cell=d_cell,
    )
    return {
        "mode": "camera",
        "k_pass": int(k_pass),
        "n_cell": int(n_cell),
        "k_a": int(k_a),
        "n_a": int(n_a),
        "k_b": int(k_b),
        "n_b": int(n_b),
        "d_a": float(d_a),
        "d_b": float(d_b),
        "d_cell": float(d_cell),
        "bound": float(bound),
        "target_p": float(target_p),
        "certified": bool(bound >= target_p),
    }


def certify_headline(
    k_pass: int,
    n_total: int,
    delta: float = 0.05,
    mode: str = "state",
    target_p: float = 0.95,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compute headline single certificate over the full distribution D."""
    from closedloop.certify import stats
    if mode == "state":
        bound = stats.cp_lower(k_pass, n_total, delta)
    elif mode == "camera":
        k_a = kwargs["k_a"]
        n_a = kwargs["n_a"]
        k_b = kwargs["k_b"]
        n_b = kwargs["n_b"]
        B = kwargs.get("B", 4)
        d_a = 0.1 * delta
        d_b = (0.1 * delta) / B
        d_head = 0.8 * delta
        bound = stats.corrected_lower(
            k_pass=k_pass,
            n_cell=n_total,
            k_a=k_a,
            n_a=n_a,
            k_b=k_b,
            n_b=n_b,
            d_a=d_a,
            d_b=d_b,
            d_cell=d_head,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return {
        "mode": mode,
        "k_pass": int(k_pass),
        "n_total": int(n_total),
        "n_cell": int(n_total),
        "delta": float(delta),
        "bound": float(bound),
        "target_p": float(target_p),
        "certified": bool(bound >= target_p),
    }


def recompute_cell_bound(
    mode: str,
    result_dict: dict[str, Any],
    d_cell: float,
    **kwargs: Any,
) -> float:
    """Independently recompute certified cell lower bound using SciPy exact formulas (V10)."""
    k_pass = int(result_dict["k_pass"])
    n_cell = int(result_dict.get("n_cell", result_dict.get("n_total", 0)))

    if mode == "state":
        if k_pass == 0:
            return 0.0
        from scipy.stats import binomtest
        ci = binomtest(k_pass, n_cell, alternative="greater").proportion_ci(
            confidence_level=1.0 - d_cell, method="exact"
        )
        return float(ci.low)

    if mode == "camera":
        from scipy.stats import beta
        k_a = int(kwargs.get("k_a", result_dict.get("k_a", 300)))
        n_a = int(kwargs.get("n_a", result_dict.get("n_a", 300)))
        k_b = int(kwargs.get("k_b", result_dict.get("k_b", 0)))
        n_b = int(kwargs.get("n_b", result_dict.get("n_b", 100)))
        d_a = float(kwargs.get("d_a", result_dict.get("d_a", 0.005)))
        d_b = float(kwargs.get("d_b", result_dict.get("d_b", 0.00125)))

        q_lo = float(beta.ppf(d_cell, k_pass, n_cell - k_pass + 1)) if k_pass > 0 else 0.0
        a_hi = 1.0 if k_a == n_a else float(beta.ppf(1 - d_a, k_a + 1, n_a - k_a))
        b_hi = 1.0 if k_b == n_b else float(beta.ppf(1 - d_b, k_b + 1, n_b - k_b))

        if q_lo <= b_hi or a_hi <= b_hi:
            return 0.0
        return float(min(1.0, (q_lo - b_hi) / (a_hi - b_hi)))

    raise ValueError(f"Unknown mode: {mode}")


def preflight_cert_cost(
    pilot_cost_usd: float,
    pilot_episodes: int,
    total_planned_episodes: int,
    remaining_budget_usd: float,
) -> dict[str, Any]:
    """Verify that projected full certification cost does not exceed remaining budget (Rule H5)."""
    if pilot_episodes <= 0:
        raise ValueError("pilot_episodes must be positive")
    cost_per_ep = float(pilot_cost_usd) / float(pilot_episodes)
    projected = float(cost_per_ep * total_planned_episodes)

    if projected >= remaining_budget_usd:
        raise BudgetPreflightError(
            f"Projected cost ${projected:.4f} >= remaining budget headroom ${remaining_budget_usd:.4f}. "
            "Execution blocked to prevent mid-run budget cap abort."
        )

    return {
        "can_proceed": True,
        "cost_per_ep_usd": float(cost_per_ep),
        "projected_cost_usd": float(projected),
        "remaining_budget_usd": float(remaining_budget_usd),
        "headroom_remaining_usd": float(remaining_budget_usd - projected),
    }


def compute_price_plot_data(
    episodes_path: Path | str,
    K: int = 16,
    target_state_p: float = 0.90,
    target_camera_p: float = 0.85,
    delta: float = 0.05,
    k_a: int = 300,
    n_a: int = 300,
    k_b: int = 2,
    n_b: int = 100,
) -> dict[str, Any]:
    """Compute certified area fraction and price-of-footage plot data solely from logs (Rule H11)."""
    p_path = Path(episodes_path)
    if not p_path.exists():
        raise FileNotFoundError(f"Episodes file not found: {p_path}")

    from closedloop.certify import stats
    budgets = compute_error_budgets(delta=delta, K=K, B=4, M=1)
    d_cell_state = budgets["state"]["d_cell"]
    d_a = budgets["camera"]["d_a"]
    d_b = budgets["camera"]["d_b"]
    d_cell_cam = budgets["camera"]["d_cell"]

    # Group episodes by cell
    cell_data: dict[str, dict[str, Any]] = {}
    episodes_count = 0

    with open(p_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            cell_id = rec.get("cell_id") or rec.get("trace_path")
            if not cell_id:
                raise ValueError(f"Episode record missing cell identifier (Rule H13): {rec}")
            if str(cell_id) == "headline" or str(cell_id).startswith("headline"):
                continue
            if not str(cell_id).startswith("cell_"):
                raise ValueError(f"Unrecognized cell_id {cell_id!r} in episode log (Rule H13)")
            episodes_count += 1
            if cell_id not in cell_data:
                cell_data[cell_id] = {
                    "state_successes": 0,
                    "camera_successes": 0,
                    "total": 0,
                }
            ts = bool(rec.get("truth_success", False))
            if "judge_pass" not in rec or rec["judge_pass"] is None:
                raise ValueError(f"Episode record {rec.get('episode_id')} missing judge_pass (Rule H8/H13)")
            jp = bool(rec["judge_pass"])
            if ts:
                cell_data[cell_id]["state_successes"] += 1
            if jp:
                cell_data[cell_id]["camera_successes"] += 1
            cell_data[cell_id]["total"] += 1

    cells_state_certified = 0
    cells_camera_certified = 0
    cell_results: dict[str, Any] = {}

    for c_id, stats_dict in sorted(cell_data.items()):
        n_c = stats_dict["total"]
        k_s = stats_dict["state_successes"]
        k_c = stats_dict["camera_successes"]

        s_bound = stats.cp_lower(k_s, n_c, d_cell_state) if n_c > 0 else 0.0
        c_bound = stats.corrected_lower(k_c, n_c, k_a, n_a, k_b, n_b, d_a, d_b, d_cell_cam) if n_c > 0 else 0.0

        is_state_cert = s_bound >= target_state_p
        is_cam_cert = c_bound >= target_camera_p

        if is_state_cert:
            cells_state_certified += 1
        if is_cam_cert:
            cells_camera_certified += 1

        cell_results[c_id] = {
            "n_episodes": n_c,
            "state_successes": k_s,
            "camera_successes": k_c,
            "state_bound": round(float(s_bound), 4),
            "camera_bound": round(float(c_bound), 4),
            "state_certified": bool(is_state_cert),
            "camera_certified": bool(is_cam_cert),
        }

    state_area_frac = float(cells_state_certified / K) if K > 0 else 0.0
    camera_area_frac = float(cells_camera_certified / K) if K > 0 else 0.0
    price_loss = float(max(0.0, state_area_frac - camera_area_frac))

    return {
        "episodes_analyzed": int(episodes_count),
        "cells_evaluated": len(cell_data),
        "K": int(K),
        "cells_state_certified": int(cells_state_certified),
        "cells_camera_certified": int(cells_camera_certified),
        "state_area_fraction": round(state_area_frac, 4),
        "camera_area_fraction": round(camera_area_frac, 4),
        "price_of_footage_area_loss": round(price_loss, 4),
        "cell_details": cell_results,
    }


def get_cell_bounds(
    cell_idx: int,
    mass_range: tuple[float, float] = (1.0, 11.5),
    fric_range: tuple[float, float] = (0.1, 1.0),
    x_range: tuple[float, float] = (-0.15, 0.15),
    y_range: tuple[float, float] = (-0.15, 0.15),
    yaw_range: tuple[float, float] = (-0.5, 0.5),
    bounds: dict[str, Any] | None = None,
) -> dict[str, tuple[float, float]]:
    """Compute parameter bounds for a given cell index in the 4x4 (mass x friction) grid."""
    if bounds:
        if "mass" in bounds:
            mass_range = tuple(bounds["mass"])
        if "friction" in bounds:
            fric_range = tuple(bounds["friction"])
        if "x" in bounds:
            x_range = tuple(bounds["x"])
        if "y" in bounds:
            y_range = tuple(bounds["y"])
        if "yaw" in bounds:
            yaw_range = tuple(bounds["yaw"])

    i_mass = cell_idx // 4
    j_fric = cell_idx % 4

    mass_step = (mass_range[1] - mass_range[0]) / 4.0
    fric_step = (fric_range[1] - fric_range[0]) / 4.0

    m_low = mass_range[0] + i_mass * mass_step
    m_high = mass_range[0] + (i_mass + 1) * mass_step

    f_low = fric_range[0] + j_fric * fric_step
    f_high = fric_range[0] + (j_fric + 1) * fric_step

    return {
        "x": x_range,
        "y": y_range,
        "yaw": yaw_range,
        "mass": (float(m_low), float(m_high)),
        "friction": (float(f_low), float(f_high)),
    }


def generate_cell_scenarios(
    program_id: str,
    n: int,
    seed: int,
    ledger: CertificationLedger,
    bounds: dict[str, tuple[float, float]] | None = None,
) -> list[dict[str, float | int]]:
    """Draw n certification scenarios within bounds, enforcing single-use per program (Rule H9)."""
    planned_seeds = [seed + i for i in range(n)]
    ledger.claim(program_id, planned_seeds)
    return sample("certification", n, seed, bounds=bounds)

