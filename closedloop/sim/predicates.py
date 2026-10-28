"""Dual success predicates + signed margin for T1 (plan Sec 9).

Predicate 1: cube center within radius r of the pad and stable for T steps.
Predicate 2 (independent): cube in contact with the pad and nearly still.
Margin is the minimum over all components; negative means failure.
Rule (V8): success = both predicates agree True; any disagreement = failure.
"""

from __future__ import annotations

import math


def horizontal_dist(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Planar distance between two xyz positions."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def evaluate(
    final_pos: tuple[float, float, float],
    tail_positions: list[tuple[float, float, float]],
    target: tuple[float, float, float],
    radius: float,
    stab_tol: float,
    contact_gap: float,
    bottom_clearance: float,
    speed: float,
    speed_tol: float,
) -> tuple[bool, bool, float]:
    """Return (pred1, pred2, margin) from measured end-of-episode quantities."""
    d_radius = radius - horizontal_dist(final_pos, target)
    dev = max(horizontal_dist(p, final_pos) for p in tail_positions)
    d_stab = stab_tol - dev
    pred1 = d_radius > 0.0 and d_stab > 0.0
    d_height = contact_gap - bottom_clearance
    d_speed = speed_tol - speed
    pred2 = d_height > 0.0 and d_speed > 0.0
    margin = min(d_radius, d_stab, d_height, d_speed)
    return pred1, pred2, margin
