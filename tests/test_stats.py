"""Phase 01 unit tests for closedloop.certify.stats (written first)."""

import math

import pytest
from scipy.stats import binomtest

from closedloop.certify import stats


def zero_failure_n(p: float, delta: float, limit: int = 2000) -> int:
    """Smallest n with all-success lower bound >= p (found via stats, not by hand)."""
    for n in range(1, limit):
        if stats.cp_lower(n, n, delta) >= p:
            return n
    raise AssertionError("no n found")


def test_cp_known_values() -> None:
    """Zero-failure run counts from plan Sec 4 table."""
    assert zero_failure_n(0.90, 0.05) == 29
    assert zero_failure_n(0.95, 0.05) == 59
    assert zero_failure_n(0.99, 0.05) == 299
    assert zero_failure_n(0.90, 0.05 / 16) == 55
    assert zero_failure_n(0.95, 0.05 / 16) == 113


def test_cp_edges() -> None:
    """k=0 gives 0.0 lower; k=n gives 1.0 upper; bounds stay in [0, 1]."""
    assert stats.cp_lower(0, 50, 0.05) == 0.0
    assert stats.cp_upper(50, 50, 0.05) == 1.0
    for k in (0, 1, 25, 49, 50):
        assert 0.0 <= stats.cp_lower(k, 50, 0.05) <= 1.0
        assert 0.0 <= stats.cp_upper(k, 50, 0.05) <= 1.0


def test_cp_monotone() -> None:
    """More successes never lower the bound; wider delta never raises it."""
    for n in (20, 100):
        los = [stats.cp_lower(k, n, 0.05) for k in range(n + 1)]
        assert all(b <= a for a, b in zip(los[1:], los))
        assert stats.cp_lower(15, n, 0.05) <= stats.cp_lower(15, n, 0.10)


def test_cp_vs_scipy() -> None:
    """V10: agree with the INDEPENDENT binomtest exact CI (never stats.beta).

    Convention (probed 2026-10-28, 12-decimal agreement): a one-sided 95%
    lower bound equals the low end of the TWO-SIDED 90% exact interval, not
    the two-sided 95% one.
    """
    assert "beta" not in open(__file__).read().split("binomtest")[0][-500:]
    mismatches = 0
    for n in (10, 29, 100):
        for k in (0, 1, n // 2, n - 1, n):
            got = stats.cp_lower(k, n, 0.05)
            exp = binomtest(k, n).proportion_ci(
                confidence_level=0.90, method="exact"
            ).low
            if not math.isclose(got, exp, rel_tol=0, abs_tol=1e-9):
                mismatches += 1
    assert mismatches == 0


def test_corrected_guards() -> None:
    """Degenerate judge statistics refuse to certify (return 0.0)."""
    sane = stats.corrected_lower(
        90, 100, 290, 300, 30, 300, 0.005, 0.00125, 0.0025
    )
    assert 0.0 < sane <= 1.0
    # q_L <= b_U: judge passes mostly on failures -> refuse
    assert (
        stats.corrected_lower(5, 100, 290, 300, 60, 300, 0.005, 0.00125, 0.0025)
        == 0.0
    )
    # a_U <= b_U: judge worse than useless -> refuse
    assert (
        stats.corrected_lower(90, 100, 10, 300, 290, 300, 0.005, 0.00125, 0.0025)
        == 0.0
    )


def test_corrected_sane() -> None:
    """Good judge + good program gives a bound in (0, 1]; perfect run ~ high."""
    bound = stats.corrected_lower(
        150, 150, 300, 300, 0, 300, 0.005, 0.00125, 0.0025
    )
    assert 0.0 < bound <= 1.0


def test_ceiling_monotone() -> None:
    """Ceiling rises with more cell runs and more calibration labels."""
    kw = dict(a=0.95, b=0.02, K=16, trials=400, seed=7)
    assert stats.ceiling(n_succ_cal=300, n_fail_cal=300, n_cell=100, **kw) <= (
        stats.ceiling(n_succ_cal=300, n_fail_cal=300, n_cell=200, **kw)
    )
    assert stats.ceiling(n_succ_cal=100, n_fail_cal=100, n_cell=150, **kw) <= (
        stats.ceiling(n_succ_cal=300, n_fail_cal=300, n_cell=150, **kw)
    )


def test_ceiling_bucket_split() -> None:
    """B=4 bucket-split ceiling must not exceed the pooled-label shortcut."""
    split = stats.ceiling(
        a=0.95, b=0.05, n_succ_cal=300, n_fail_cal=300, n_cell=150,
        K=16, B=4, trials=500, seed=11,
    )
    assert 0.0 <= split <= 1.0
    pooled_bias_demo = stats.ceiling(
        a=0.95, b=0.05, n_succ_cal=300, n_fail_cal=300 * 4, n_cell=150,
        K=16, B=1, trials=500, seed=11,
    )
    assert split <= pooled_bias_demo + 1e-9


if __name__ == "__main__":
    pytest.main([__file__])
