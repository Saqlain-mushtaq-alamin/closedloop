"""Falsifier: searches for low-margin failures using Optuna CMA-ES (Plan §8, Phase 05).

Maximizes falsification efficiency by minimizing the margin within the bounds
of distribution D. Seeds are strictly constrained to the repair stream [0, 999999] (V4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import optuna
from optuna.samplers import CmaEsSampler, RandomSampler

from closedloop.data.sampler import STREAM_RANGES, LeakageError
from closedloop.falsify.minimizer import is_failing

# Suppress Optuna info logs during optimization
optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass
class FalsificationResult:
    """Outcome of a falsification search run."""

    best_margin: float
    total_evals: int
    failures: list[dict[str, Any]] = field(default_factory=list)
    best_scenario: dict[str, Any] | None = None
    study: optuna.Study | None = None


def _check_falsifier_seed(seed: int, budget: int) -> None:
    """Ensure seeds lie strictly within the repair stream range (H9, V4)."""
    lo, hi = STREAM_RANGES["repair"]
    if not (lo <= seed <= hi):
        raise LeakageError(f"seed {seed} outside repair stream range [{lo}, {hi}]")
    if not (lo <= seed + budget - 1 <= hi):
        raise LeakageError(
            f"seed range {seed}..{seed + budget - 1} exceeds repair stream limit {hi}"
        )


def falsify(
    eval_fn: Callable[[dict[str, Any]], Any],
    bounds: dict[str, tuple[float, float]],
    *,
    budget: int = 50,
    seed: int = 10000,
    sampler_type: str = "cmaes",
) -> FalsificationResult:
    """Search for failing scenarios by minimizing margin within bounds of D.

    Args:
        eval_fn: Callable taking a scenario dict and returning a result with margin.
        bounds: Parameter bounds dict {name: (low, high)} defining distribution D.
        budget: Maximum number of simulation episodes / evaluations.
        seed: Initial seed (must be within repair stream 0..999999).
        sampler_type: 'cmaes' (default) or 'random' (fallback).

    Returns:
        FalsificationResult with best_margin, total_evals, and sorted failures.
    """
    _check_falsifier_seed(seed, budget)

    if sampler_type.lower() == "cmaes":
        sampler = CmaEsSampler(seed=seed)
    elif sampler_type.lower() == "random":
        sampler = RandomSampler(seed=seed)
    else:
        raise ValueError(f"Unknown sampler_type: {sampler_type!r} (expected 'cmaes' or 'random')")

    study = optuna.create_study(direction="minimize", sampler=sampler)
    failures: list[dict[str, Any]] = []
    trial_scenarios: dict[int, dict[str, Any]] = {}

    def objective(trial: optuna.Trial) -> float:
        scenario: dict[str, Any] = {}
        for param, (low, high) in bounds.items():
            scenario[param] = float(trial.suggest_float(param, low, high))

        scenario["seed"] = seed + trial.number
        trial_scenarios[trial.number] = dict(scenario)

        result = eval_fn(scenario)
        margin = float(
            result.get("margin", 0.0)
            if isinstance(result, dict)
            else getattr(result, "margin", 0.0)
        )

        if is_failing(result):
            failures.append({
                "scenario": dict(scenario),
                "margin": margin,
                "trial_index": trial.number,
                "result": result,
            })

        return margin

    study.optimize(objective, n_trials=budget)

    # Sort failures by margin ascending (most severe failure first)
    failures.sort(key=lambda f: f["margin"])

    best_scenario = (
        trial_scenarios.get(study.best_trial.number)
        if study.best_trial is not None
        else None
    )

    return FalsificationResult(
        best_margin=float(study.best_value),
        total_evals=budget,
        failures=failures,
        best_scenario=best_scenario,
        study=study,
    )
