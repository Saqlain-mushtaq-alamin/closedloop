"""Certificate math (H6 LOCKED): Clopper-Pearson, corrected judge bound, ceiling.

Pure functions; all randomness via an explicit seed. Mirrors plan Appendix A
as fixed Oct 28 (per-bucket FPR worst-bucket ceiling, (K*M) error split).
"""

from __future__ import annotations

import numpy as np
from scipy.stats import beta


def cp_upper(k: int, n: int, d: float) -> float:
    """One-sided Clopper-Pearson upper bound at confidence 1 - d."""
    return 1.0 if k == n else float(beta.ppf(1 - d, k + 1, n - k))


def cp_lower(k: int, n: int, d: float) -> float:
    """One-sided Clopper-Pearson lower bound at confidence 1 - d."""
    return 0.0 if k == 0 else float(beta.ppf(d, k, n - k + 1))


def corrected_lower(
    k_pass: int,
    n_cell: int,
    k_a: int,
    n_a: int,
    k_b: int,
    n_b: int,
    d_a: float,
    d_b: float,
    d_cell: float,
) -> float:
    """Lower bound on true success p for a noisy judge.

    k_a / n_a: judge passes on labelled TRUE successes (TPR data).
    k_b / n_b: judge passes on labelled TRUE failures (FPR data).
    Refuses (0.0) when the judge statistics cannot support a certificate.
    Derived for this project; coverage-tested, not from the literature.
    """
    q_lo = cp_lower(k_pass, n_cell, d_cell)
    a_hi = cp_upper(k_a, n_a, d_a)
    b_hi = cp_upper(k_b, n_b, d_b)
    if q_lo <= b_hi or a_hi <= b_hi:
        return 0.0
    return min(1.0, (q_lo - b_hi) / (a_hi - b_hi))


def ceiling(
    a: float,
    b: float,
    n_succ_cal: int,
    n_fail_cal: int,
    n_cell: int,
    K: int,
    delta: float = 0.05,
    p: float = 1.0,
    B: int = 1,
    M: int = 1,
    trials: int = 2000,
    seed: int = 0,
) -> float:
    """Median certified bound for a program with true success p.

    Failure labels are split across B buckets (n_fail_cal // B each); the
    worst (largest) per-bucket FPR upper bound is used, matching the
    certification rule. Pooling all labels at d_b overstates the ceiling
    whenever B > 1.
    """
    rng = np.random.default_rng(seed)
    d_a, d_b, d_cell = 0.1 * delta, 0.1 * delta / B, 0.8 * delta / (K * M)
    n_b = n_fail_cal // B
    q = p * a + (1 - p) * b
    out = []
    for _ in range(trials):
        b_hi = max(
            cp_upper(int(rng.binomial(n_b, b)), n_b, d_b) for _ in range(B)
        )
        q_lo = cp_lower(int(rng.binomial(n_cell, q)), n_cell, d_cell)
        a_hi = cp_upper(int(rng.binomial(n_succ_cal, a)), n_succ_cal, d_a)
        out.append(
            0.0
            if q_lo <= b_hi or a_hi <= b_hi
            else min(1.0, (q_lo - b_hi) / (a_hi - b_hi))
        )
    return float(np.median(out))
