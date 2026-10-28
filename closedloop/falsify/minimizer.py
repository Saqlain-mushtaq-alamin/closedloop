"""Counterexample minimizer: shrinks failing scenarios toward nominal (Plan §8, §10).

Monotonically moves parameters toward nominal values one at a time while
preserving the failure. The returned scenario is guaranteed to still fail
and have distance-to-nominal <= input distance.
"""

from __future__ import annotations

from typing import Any, Callable

# Default nominal values for Tier 2 T1 (all nominals strictly within distribution D)
DEFAULT_NOMINAL: dict[str, float] = {
    "x": 0.0,
    "y": 0.0,
    "yaw": 0.0,
    "mass": 1.0,
    "friction": 0.8,
}


def distance_to_nominal(scenario: dict[str, Any], nominal: dict[str, float]) -> float:
    """Sum of coordinate-wise absolute distances to nominal values."""
    dist = 0.0
    for k, nom_val in nominal.items():
        if k in scenario and isinstance(scenario[k], (int, float)):
            dist += abs(float(scenario[k]) - float(nom_val))
    return float(dist)


def is_failing(result: Any) -> bool:
    """Determine whether an evaluation outcome represents a failure.

    Rule (V8): success requires both predicates agree True and margin > 0.
    Failure occurs if either predicate is False or margin < 0.
    Missing fields raise ValueError to prevent silent defaulting (H11).
    """
    if isinstance(result, bool):
        return not result
    if isinstance(result, dict):
        if "truth_success" not in result or "margin" not in result:
            raise ValueError(f"malformed evaluation result missing required fields: {result}")
        p1 = bool(result["truth_success"])
        p2 = bool(result.get("truth_success_alt", p1))
        margin = float(result["margin"])
        return (not p1) or (not p2) or (margin < 0.0)
    if hasattr(result, "truth_success"):
        p1 = bool(result.truth_success)
        p2 = bool(getattr(result, "truth_success_alt", p1))
        margin = float(getattr(result, "margin", 0.0))
        return (not p1) or (not p2) or (margin < 0.0)
    raise TypeError(f"cannot extract failure from outcome of type {type(result)}")


def minimize(
    scenario: dict[str, Any],
    eval_fn: Callable[[dict[str, Any]], Any],
    nominal: dict[str, float] | None = None,
    *,
    bisection_steps: int = 6,
    param_keys: list[str] | None = None,
    bounds: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Shrink a failing scenario toward nominal values while preserving failure.

    Args:
        scenario: Initial failing scenario dictionary.
        eval_fn: Callable returning boolean, dict, or EpisodeResult/SimResult.
        nominal: Target nominal parameter values (defaults to Tier 2 nominal).
        bisection_steps: Number of binary search steps for continuous parameters.
        param_keys: Explicit parameter order to minimize.
        bounds: Optional distribution D bounds to verify parameters stay inside D.

    Returns:
        A new scenario dict that is guaranteed to still fail and whose
        distance to nominal is <= input scenario's distance to nominal.
    """
    nom = nominal if nominal is not None else DEFAULT_NOMINAL

    # Verify input actually fails
    init_res = eval_fn(scenario)
    if not is_failing(init_res):
        raise ValueError("Initial scenario does not fail; cannot minimize passing scenario")

    current = dict(scenario)
    if param_keys is not None:
        keys = [k for k in param_keys if k in nom and k in current and isinstance(current[k], (int, float))]
    else:
        keys = [k for k in nom if k in current and isinstance(current[k], (int, float))]

    # Step 1: Direct substitution with nominal (removes irrelevant parameters)
    for k in keys:
        if abs(float(current[k]) - float(nom[k])) < 1e-9:
            continue
        candidate = dict(current)
        candidate[k] = nom[k]
        if bounds and k in bounds:
            lo, hi = bounds[k]
            candidate[k] = max(lo, min(hi, float(candidate[k])))
        res = eval_fn(candidate)
        if is_failing(res):
            current[k] = candidate[k]

    # Step 2: Continuous bisection for parameters that cannot be set directly to nominal
    for k in keys:
        if abs(float(current[k]) - float(nom[k])) < 1e-9:
            continue

        failing_val = float(current[k])
        passing_val = float(nom[k])

        for _ in range(bisection_steps):
            mid_val = 0.5 * (failing_val + passing_val)
            candidate = dict(current)
            candidate[k] = mid_val
            if bounds and k in bounds:
                lo, hi = bounds[k]
                candidate[k] = max(lo, min(hi, float(candidate[k])))
            res = eval_fn(candidate)
            if is_failing(res):
                # Mid value still fails, so we can shrink closer to nominal
                failing_val = candidate[k]
                current[k] = candidate[k]
            else:
                # Mid value passes, so the boundary lies between mid and failing
                passing_val = candidate[k]

    # Final sanity check: ensure output still fails
    final_res = eval_fn(current)
    if not is_failing(final_res):
        # Fallback to original failing scenario if anything went wrong
        return dict(scenario)

    return current
