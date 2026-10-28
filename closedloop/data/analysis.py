"""Statistical analysis and experimental verification (V6, H1, paired bootstrap).

Implements:
- paired_bootstrap_ci: paired difference bootstrap 95% CI (10k resamples)
- compute_h1_gap: generalization gap (loop vs held-out) with paired CI
- check_budget_parity: V6 unit check enforcing <= 5% difference in arm budgets
"""

from __future__ import annotations

from typing import Sequence
import numpy as np


class BudgetParityError(RuntimeError):
    """Raised when arm budgets violate the <= 5% parity rule (V6)."""


def paired_bootstrap_ci(
    data_a: Sequence[float],
    data_b: Sequence[float],
    n_resamples: int = 10000,
    ci: float = 0.95,
    seed: int = 0,
) -> dict[str, float | list[float]]:
    """Compute paired difference mean and percentile bootstrap CI (pure numpy).

    Args:
        data_a: Trajectory scores for arm / condition A.
        data_b: Trajectory scores for arm / condition B (paired with A).
        n_resamples: Number of bootstrap resamples (default 10,000 per plan Sec 12).
        ci: Confidence level (default 0.95 for 95% CI).
        seed: Random seed for deterministic reproducibility.

    Returns:
        Dict with diff (mean(A) - mean(B)), ci_lower, ci_upper, and bootstrap_samples.
    """
    arr_a = np.asarray(data_a, dtype=float)
    arr_b = np.asarray(data_b, dtype=float)
    if len(arr_a) != len(arr_b):
        raise ValueError(f"paired data length mismatch: {len(arr_a)} vs {len(arr_b)}")
    n = len(arr_a)
    if n == 0:
        raise ValueError("cannot compute bootstrap CI on empty data")

    diffs = arr_a - arr_b
    mean_diff = float(np.mean(diffs))

    rng = np.random.default_rng(seed)
    # Generate bootstrap index matrix (n_resamples, n)
    indices = rng.integers(0, n, size=(n_resamples, n))
    bootstrap_means = np.mean(diffs[indices], axis=1)

    alpha = (1.0 - ci) / 2.0
    ci_lower = float(np.percentile(bootstrap_means, alpha * 100.0))
    ci_upper = float(np.percentile(bootstrap_means, (1.0 - alpha) * 100.0))

    return {
        "diff": mean_diff,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "bootstrap_samples": bootstrap_means.tolist(),
    }


def compute_h1_gap(
    loop_scores: Sequence[float],
    held_out_scores: Sequence[float],
    n_resamples: int = 10000,
    ci: float = 0.95,
    seed: int = 0,
) -> dict[str, float | list[float]]:
    """Compute H1 generalization gap: gap = loop - held-out with paired bootstrap CI.

    Plan Sec 2 / Sec 12:
    Programs that pass the loop's own scenario succeed noticeably less on held-out.
    gap = loop_success - held_out_success.
    """
    mean_loop = float(np.mean(loop_scores)) if len(loop_scores) > 0 else 0.0
    mean_held_out = float(np.mean(held_out_scores)) if len(held_out_scores) > 0 else 0.0
    res = paired_bootstrap_ci(
        loop_scores, held_out_scores, n_resamples=n_resamples, ci=ci, seed=seed
    )
    return {
        "mean_loop": mean_loop,
        "mean_held_out": mean_held_out,
        "gap": float(res["diff"]),
        "ci_lower": float(res["ci_lower"]),
        "ci_upper": float(res["ci_upper"]),
        "bootstrap_samples": res["bootstrap_samples"],
    }


def check_budget_parity(
    arm_budgets: dict[str, dict[str, int | float]],
    max_rel_diff: float = 0.05,
) -> None:
    """Enforce V6 budget parity: episodes and tokens across arms must be within 5%.

    Args:
        arm_budgets: Mapping of arm_name -> {"episodes": int, "tokens": int}
        max_rel_diff: Allowed relative difference (default 0.05 = 5%).

    Raises:
        BudgetParityError if any metric differs by more than max_rel_diff.
    """
    if len(arm_budgets) < 2:
        return

    for metric in ("episodes", "tokens"):
        values = [float(b.get(metric, 0)) for b in arm_budgets.values()]
        max_val = max(values)
        min_val = min(values)
        if max_val > 0:
            rel_diff = (max_val - min_val) / max_val
            if rel_diff > max_rel_diff:
                raise BudgetParityError(
                    f"{metric} difference {rel_diff:.2%} exceeds allowed {max_rel_diff:.2%} "
                    f"across arms: {arm_budgets}"
                )
