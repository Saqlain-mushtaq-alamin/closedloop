"""Repair engine: evaluates repair candidates under the 3-stage acceptance rule (Plan §10).

Acceptance rule:
1. Passes the minimal counterexample.
2. Passes the regression set (all earlier counterexamples plus nominal scenarios).
3. Survives a short falsifier re-run with a fixed small budget.

Rejection causes rollback to the previous accepted program version.
Tracks repair rate, damage rate (V7), and acceptance rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from closedloop.falsify.minimizer import is_failing


@dataclass
class DamageAccounting:
    """Tracks repair attempts, regression damage, and acceptance (Plan §10, V7)."""

    total_attempts: int = 0
    fixed_count: int = 0
    damage_count: int = 0
    accepted_count: int = 0

    def record_attempt(
        self,
        *,
        fixed_counterexample: bool,
        damaged_regression: bool,
        accepted: bool,
    ) -> None:
        self.total_attempts += 1
        if fixed_counterexample:
            self.fixed_count += 1
        if damaged_regression:
            self.damage_count += 1
        if accepted:
            self.accepted_count += 1

    @property
    def repair_rate(self) -> float:
        return self.fixed_count / self.total_attempts if self.total_attempts > 0 else 0.0

    @property
    def damage_rate(self) -> float:
        return self.damage_count / self.total_attempts if self.total_attempts > 0 else 0.0

    @property
    def acceptance_rate(self) -> float:
        return self.accepted_count / self.total_attempts if self.total_attempts > 0 else 0.0


@dataclass
class RepairCandidate:
    """Candidate program proposal submitted for acceptance evaluation."""

    code: str
    rationale: str
    program_id: str
    version: int
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class RepairEvaluator:
    """Manages acceptance checks, regression set accumulation, and damage accounting (V7)."""

    def __init__(
        self,
        falsifier_budget: int = 10,
        seed: int = 15000,
        accounting: DamageAccounting | None = None,
    ) -> None:
        self.falsifier_budget = falsifier_budget
        self.seed = seed
        self.accounting = accounting if accounting is not None else DamageAccounting()
        self.regression_set: list[dict[str, Any]] = []

    def add_to_regression_set(self, scenario: dict[str, Any]) -> None:
        self.regression_set.append(dict(scenario))

    def evaluate_candidate(
        self,
        candidate_eval_fn: Callable[[dict[str, Any]], Any],
        counterexample: dict[str, Any],
        falsifier_fn: Callable[[Callable[[dict[str, Any]], Any]], dict[str, Any] | None] | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        # Stage 1: Check counterexample fix
        ce_res = candidate_eval_fn(counterexample)
        fixed_ce = not is_failing(ce_res)

        # Stage 2: Check regression damage against all accumulated scenarios
        damaged_reg = False
        failed_reg_id = None
        failed_reg_res = None
        for sc in self.regression_set:
            reg_res = candidate_eval_fn(sc)
            if is_failing(reg_res):
                damaged_reg = True
                if failed_reg_id is None:
                    failed_reg_id = sc.get("id", str(sc.get("seed", sc.get("mass", "unknown"))))
                    failed_reg_res = reg_res

        # Stage 3: Short falsifier rerun (run across all candidates to maintain fixed verification budget)
        rerun_fail = None
        if falsifier_fn is not None:
            rerun_fail = falsifier_fn(candidate_eval_fn)

        accepted = fixed_ce and (not damaged_reg) and (rerun_fail is None)

        self.accounting.record_attempt(
            fixed_counterexample=fixed_ce,
            damaged_regression=damaged_reg,
            accepted=accepted,
        )

        if accepted:
            self.add_to_regression_set(counterexample)
            reason = "accepted"
            details = {"stage": 3}
        elif not fixed_ce:
            margin = (
                ce_res.get("margin", -1.0)
                if isinstance(ce_res, dict)
                else getattr(ce_res, "margin", -1.0)
            )
            reason = "Failed counterexample"
            details = {"stage": 1, "margin": float(margin), "scenario": dict(counterexample), "result": ce_res}
        elif damaged_reg:
            reason = f"Regression on earlier scenario: {failed_reg_id}"
            details = {"stage": 2, "failed_regression_id": failed_reg_id, "result": failed_reg_res}
        else:
            reason = "Failed short falsifier rerun"
            details = {"stage": 3, "failing_scenario": dict(rerun_fail) if rerun_fail else {}}

        return accepted, reason, details


def verify_repair_acceptance(
    *,
    candidate_eval_fn: Callable[[dict[str, Any]], Any],
    counterexample: dict[str, Any],
    regression_set: list[dict[str, Any]],
    falsifier_fn: Callable[[Callable[[dict[str, Any]], Any]], dict[str, Any] | None] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Evaluate candidate repair against the 3-stage acceptance rule (Plan §10).

    Returns:
        (accepted: bool, reason: str, details: dict)
    """
    # Stage 1: Candidate must pass the minimal counterexample
    ce_res = candidate_eval_fn(counterexample)
    if is_failing(ce_res):
        margin = (
            ce_res.get("margin", -1.0)
            if isinstance(ce_res, dict)
            else getattr(ce_res, "margin", -1.0)
        )
        return (
            False,
            "Failed counterexample",
            {"stage": 1, "margin": float(margin), "scenario": dict(counterexample)},
        )

    # Stage 2: Candidate must pass the regression set (all earlier scenarios)
    for reg_sc in regression_set:
        reg_res = candidate_eval_fn(reg_sc)
        if is_failing(reg_res):
            sc_id = reg_sc.get("id", str(reg_sc.get("seed", reg_sc.get("mass", "unknown"))))
            return (
                False,
                f"Regression on earlier scenario: {sc_id}",
                {
                    "stage": 2,
                    "failed_regression_id": sc_id,
                    "scenario": dict(reg_sc),
                    "result": reg_res,
                },
            )

    # Stage 3: Candidate must survive a short falsifier re-run
    if falsifier_fn is not None:
        failing_nearby = falsifier_fn(candidate_eval_fn)
        if failing_nearby is not None:
            return (
                False,
                "Failed short falsifier rerun",
                {"stage": 3, "failing_scenario": dict(failing_nearby)},
            )

    return True, "accepted", {"stage": 3}


def build_repair_prompt(
    current_code: str,
    counterexample: dict[str, Any],
    primitives_doc: str,
    *,
    margin: float | None = None,
    trace_summary: str | None = None,
    filmstrip_description: str | None = None,
) -> str:
    """Assemble repair prompt providing failure feedback and current code."""
    ce_desc = ", ".join(
        f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
        for k, v in counterexample.items()
        if k != "seed"
    )
    parts = [
        "You are repairing a Python robot program that failed in simulation.",
        "",
        "Available Primitives API:",
        primitives_doc,
        "",
        "Current Robot Program:",
        "```python",
        current_code.strip(),
        "```",
        "",
        "Failure Diagnostics:",
        f"- Failing minimal scenario: ({ce_desc})",
    ]
    if margin is not None:
        parts.append(f"- Margin: {margin:.4f} (negative indicates distance to success region)")
    if trace_summary:
        parts.append(f"- Execution trace: {trace_summary}")
    if filmstrip_description:
        parts.append(f"- Visual filmstrip frames: {filmstrip_description}")

    parts.extend([
        "",
        "Instructions:",
        "1. Analyze why the policy failed on the given scenario parameters.",
        "2. Revise policy(env, rng) to successfully handle this scenario while maintaining correct behavior.",
        "3. Ensure gripper force, lift trajectory, and placement stability are physically adequate.",
        "",
        'Reply strictly with JSON object: {"code": "<revised python code>", "rationale": "<explanation of fix>"}.',
    ])
    return "\n".join(parts)
