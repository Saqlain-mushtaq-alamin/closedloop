"""Shift test analysis and bound comparison module (Plan §12, Phase 09).

Evaluates whether statistical guarantees certified under distribution D transfer
to shifted distribution D' (Hypothesis H4: the honesty figure).

Rules enforced:
- Pure functions for statistics (AGENTS.md §4).
- Numbers generated strictly from logs (Rule H11).
- Exact Clopper-Pearson lower bounds via closedloop.certify.stats (Rule H6).
- Independent verification via SciPy binomtest (V10).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binomtest, ks_2samp

from closedloop.certify import stats


def compare_shift_bounds(
    d_bound: float,
    dp_pass: int,
    dp_total: int,
    delta: float = 0.05,
    target_p: float = 0.90,
) -> dict[str, Any]:
    """Compare reference D bound against recertified Clopper-Pearson bound on D'.

    Hypothesis H4 asserts that either:
    1. The recertified lower bound on D' drops strictly below the D bound.
    2. The recertified lower bound refuses to certify against target_p (refusal).
    """
    if dp_total <= 0:
        raise ValueError(f"dp_total must be > 0, got {dp_total}")
    if not (0 <= dp_pass <= dp_total):
        raise ValueError(f"dp_pass {dp_pass} must be in [0, {dp_total}]")

    dp_rate = float(dp_pass) / float(dp_total)
    dp_bound = float(stats.cp_lower(dp_pass, dp_total, delta))

    # Independent SciPy recomputation check (V10)
    if dp_pass == 0:
        scipy_bound = 0.0
    else:
        ci = binomtest(dp_pass, dp_total, alternative="greater").proportion_ci(
            confidence_level=1.0 - delta, method="exact"
        )
        scipy_bound = float(ci.low)
    assert abs(dp_bound - scipy_bound) < 1e-9, (
        f"SciPy recomputation discrepancy: {dp_bound} vs {scipy_bound}"
    )

    bound_dropped = bool(dp_bound < d_bound)
    certified_on_dp = bool(dp_bound >= target_p)
    refusal = not certified_on_dp

    return {
        "d_bound": float(d_bound),
        "dp_pass": int(dp_pass),
        "dp_total": int(dp_total),
        "dp_empirical_pass_rate": float(dp_rate),
        "dp_bound": float(dp_bound),
        "scipy_recomputed_bound": float(scipy_bound),
        "delta": float(delta),
        "target_p": float(target_p),
        "bound_dropped": bound_dropped,
        "bound_difference": float(d_bound - dp_bound),
        "certified_on_dp": certified_on_dp,
        "refusal": refusal,
    }


def compute_scenario_shift_stats(
    scenarios_d: list[dict[str, Any]],
    scenarios_dp: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute statistical and physical shift metrics between D and D' scenarios."""
    metrics: dict[str, Any] = {}
    keys = ["mass", "friction", "x", "y", "yaw"]

    for k in keys:
        vals_d = np.array([float(s[k]) for s in scenarios_d if k in s])
        vals_dp = np.array([float(s[k]) for s in scenarios_dp if k in s])

        if len(vals_d) == 0 or len(vals_dp) == 0:
            continue

        ks_res = ks_2samp(vals_d, vals_dp)
        metrics[k] = {
            "mean_d": float(np.mean(vals_d)),
            "std_d": float(np.std(vals_d)),
            "min_d": float(np.min(vals_d)),
            "max_d": float(np.max(vals_d)),
            "mean_dp": float(np.mean(vals_dp)),
            "std_dp": float(np.std(vals_dp)),
            "min_dp": float(np.min(vals_dp)),
            "max_dp": float(np.max(vals_dp)),
            "mean_diff": float(np.mean(vals_dp) - np.mean(vals_d)),
            "ks_statistic": float(ks_res.statistic),
            "ks_pvalue": float(ks_res.pvalue),
            "statistically_shifted": bool(ks_res.pvalue < 1e-4),
        }

    # High-level gate check: mass shifted up >= 2.0 kg and friction shifted down <= -0.15
    mass_shifted = metrics.get("mass", {}).get("mean_diff", 0.0) >= 2.0
    fric_shifted = metrics.get("friction", {}).get("mean_diff", 0.0) <= -0.15
    shift_detected = bool(mass_shifted and fric_shifted)

    return {
        "shift_detected": shift_detected,
        "mass_shifted": bool(mass_shifted),
        "friction_shifted": bool(fric_shifted),
        "dimensions": metrics,
    }


def generate_shift_figure_data(
    episodes_path: Path | str,
    d_bound: float,
    delta: float = 0.05,
    target_p: float = 0.90,
) -> dict[str, Any]:
    """Generate complete shift figure data strictly from raw append-only logs (Rule H11)."""
    p_path = Path(episodes_path)
    if not p_path.exists():
        raise FileNotFoundError(f"Episodes log file not found: {p_path}")

    d_episodes: list[dict[str, Any]] = []
    dp_episodes: list[dict[str, Any]] = []

    with p_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            dist = rec.get("distribution")
            if dist == "D":
                d_episodes.append(rec)
            elif dist in ("D_prime", "D'"):
                dp_episodes.append(rec)

    n_d = len(d_episodes)
    n_dp = len(dp_episodes)

    if n_dp == 0:
        raise ValueError(f"No D' episodes found in {p_path}")

    # Truth success counts
    k_d = sum(1 for ep in d_episodes if ep.get("truth_success", False))
    k_dp = sum(1 for ep in dp_episodes if ep.get("truth_success", False))

    d_rate = float(k_d) / float(n_d) if n_d > 0 else 0.0
    dp_rate = float(k_dp) / float(n_dp)

    # Compute bounds
    d_recomputed_bound = float(stats.cp_lower(k_d, n_d, delta)) if n_d > 0 else float(d_bound)
    dp_bound = float(stats.cp_lower(k_dp, n_dp, delta))

    comparison = compare_shift_bounds(
        d_bound=d_recomputed_bound,
        dp_pass=k_dp,
        dp_total=n_dp,
        delta=delta,
        target_p=target_p,
    )

    # Extract scenario statistics if scenario dicts logged
    scenarios_d = [ep["scenario"] for ep in d_episodes if "scenario" in ep]
    scenarios_dp = [ep["scenario"] for ep in dp_episodes if "scenario" in ep]
    scenario_stats = (
        compute_scenario_shift_stats(scenarios_d, scenarios_dp)
        if scenarios_d and scenarios_dp
        else {}
    )

    return {
        "n_d": int(n_d),
        "k_d": int(k_d),
        "d_empirical_pass_rate": float(d_rate),
        "d_bound": float(d_bound),
        "d_recomputed_bound": float(d_recomputed_bound),
        "n_dp": int(n_dp),
        "k_dp": int(k_dp),
        "dp_empirical_pass_rate": float(dp_rate),
        "dp_recertified_bound": float(dp_bound),
        "delta": float(delta),
        "target_p": float(target_p),
        "bound_dropped": comparison["bound_dropped"],
        "refusal": comparison["refusal"],
        "certified_on_dp": comparison["certified_on_dp"],
        "bound_difference": comparison["bound_difference"],
        "empirical_gap": float(d_rate - dp_rate),
        "scenario_stats": scenario_stats,
        "figure_plot_data": {
            "categories": ["Reference D", "Shifted D'"],
            "empirical_rates": [float(d_rate), float(dp_rate)],
            "certified_bounds": [float(d_recomputed_bound), float(dp_bound)],
            "target_threshold": float(target_p),
        },
    }
