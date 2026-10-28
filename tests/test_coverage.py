"""Phase 01 V10 coverage tests (written first): bounds hold >= 95% of trials."""

import numpy as np

from closedloop.certify import stats

DELTA = 0.05
TRIALS = 3000
SEED = 20261028


def empirical_coverage(bound_fn, sampler, trials=TRIALS, seed=SEED) -> float:
    """Fraction of synthetic trials where the bound stays below the true p."""
    rng = np.random.default_rng(seed)
    ok = 0
    for _ in range(trials):
        true_p, bound = sampler(rng)
        if bound <= true_p:
            ok += 1
    return ok / trials


def test_coverage_state() -> None:
    """State CP bound below true p at least 1 - delta of the time."""

    def trial(rng):
        true_p = float(rng.uniform(0.5, 1.0))
        k = int(rng.binomial(150, true_p))
        return true_p, stats.cp_lower(k, 150, DELTA)

    cov = empirical_coverage(trial, trial)
    print(f"\nstate coverage: {cov:.4f} over {TRIALS} trials")
    assert cov >= 1 - DELTA


def test_coverage_corrected() -> None:
    """Corrected judge bound below true p at least 1 - delta of the time."""

    def trial(rng):
        true_p = float(rng.uniform(0.7, 1.0))
        a, b = 0.95, 0.03
        q = true_p * a + (1 - true_p) * b
        bound = stats.corrected_lower(
            int(rng.binomial(150, q)), 150,
            int(rng.binomial(300, a)), 300,
            int(rng.binomial(300, b)), 300,
            0.005, 0.00125, 0.0025,
        )
        return true_p, bound

    cov = empirical_coverage(trial, trial)
    print(f"\ncorrected coverage: {cov:.4f} over {TRIALS} trials")
    assert cov >= 1 - DELTA
