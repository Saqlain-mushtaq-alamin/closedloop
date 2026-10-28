"""Counterexample minimizer: shrinks failing scenarios toward nominal (Plan §8, §10).

Monotonically moves parameters toward nominal values one at a time while
preserving the failure. The returned scenario is guaranteed to still fail
and have distance-to-nominal <= input distance.
"""

from __future__ import annotations

from typing import Any, Callable

DEFAULT_NOMINAL: dict[str, float] = {
    "x": 0.0,
    "y": 0.0,
    "yaw": 0.0,
    "mass": 0.1,
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
    Failure occurs if either predicate is False or margin <= 0.
    """
    if isinstance(result, bool):
        # Truth value: True means success, False means failure
        return not result
    if isinstance(result, dict):
        p1 = bool(result.get("truth_success", True))
        p2 = bool(result.get("truth_success_alt", p1))
        margin = float(result.get("margin", 0.0))
        # Failure if either predicate is false or margin is negative
        return (not p1) or (not p2) or (margin <= 0.0)
    if hasattr(result, "truth_success"):
        p1 = bool(result.truth_success)
        p2 = bool(getattr(result, "truth_success_alt", p1))
        margin = float(getattr(result, "margin", 0.0))
        return (not p1) or (not p2) or (margin <= 0.0)
    raise TypeError(f"cannot extract failure from outcome of type {type(result)}")


def minimize(
    scenario: dict[str, Any],
    eval_fn: Callable[[dict[str, Any]], Any],
    nominal: dict[str, float] | None = None,
    *,
    bisection_steps: int = 6,
    param_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Shrink a failing scenario toward nominal values while preserving failure.

    Args:
        scenario: Initial failing scenario dictionary.
        eval_fn: Callable returning boolean, dict, or EpisodeResult/SimResult.
        nominal: Target nominal parameter values (defaults to T1 nominal).
        bisection_steps: Number of binary search steps for continuous parameters.
        param_keys: Explicit parameter order to minimize (optional).

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
    keys = (
        param_keys
        if param_keys is not None
        else [k for k in nom if k in current and isinstance(current[k], (int, float))]
    )

    # Step 1: Direct substitution with nominal (removes irrelevant parameters)
    for k in keys:
        if abs(float(current[k]) - float(nom[k])) < 1e-9:
            continue
        candidate = dict(current)
        candidate[k] = nom[k]
        res = eval_fn(candidate)
        if is_failing(res):
            current[k] = nom[k]

    # Step 2: Continuous bisection for parameters that cannot be set to nominal
    for k in keys:
        if abs(float(current[k]) - float(nom[k])) < 1e-9:
            continue

        failing_val = float(current[k])
        passing_val = float(nom[k])

        for _ in range(bisection_steps):
            mid_val = 0.5 * (failing_val + passing_val)
            candidate = dict(current)
            candidate[k] = mid_val
            res = eval_fn(candidate)
            if is_failing(res):
                # Mid value still fails, so we can shrink closer to nominal
                failing_val = mid_val
                current[k] = mid_val
            else:
                # Mid value passes, so the boundary lies between mid and failing
                passing_val = mid_val

    # Final sanity check: ensure output still fails
    final_res = eval_fn(current)
    if not is_failing(final_res):
        # Fallback to original failing scenario if anything went wrong
        return dict(scenario)

    return current
