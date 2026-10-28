"""Phase 04 baselines B0/B1 and H1 generalization gap tests (written first).

Covers:
- test_positive_control (V3): hand-written good program in tuned band
- test_h1_gap_report: gap = loop - held-out, paired bootstrap 95% CI (10k)
- test_budget_parity_unit (V6): arm budgets compared, within 5% or FAIL
- test_frozen_manifest (V11): manifest hash = frozen hash, n fixed
"""

import json
from pathlib import Path
import pytest
import numpy as np

from closedloop.data.analysis import (
    BudgetParityError,
    check_budget_parity,
    compute_h1_gap,
    paired_bootstrap_ci,
)
from closedloop.data.manifest import build_manifest, config_hash, write_manifest
from closedloop.data.sampler import sample
from closedloop.sim.env import T1Env, good_policy

ROOT = Path(__file__).resolve().parent.parent

TUNED_BOUNDS = {
    "x": (-0.15, 0.15),
    "y": (-0.15, 0.15),
    "yaw": (-0.5, 0.5),
    "mass": (1.0, 11.5),
    "friction": (0.1, 1.0),
}


def test_positive_control() -> None:
    """V3: hand-written good program succeeds within the tuned difficulty band."""
    scenarios = sample("repair", 30, 200, bounds=TUNED_BOUNDS)
    env = T1Env()
    try:
        results = [
            env.run_episode(good_policy, sc, sc["seed"])
            for sc in scenarios
        ]
    finally:
        env.close()

    successes = sum(1 for r in results if r.truth_success)
    rate = successes / len(results)
    print(f"\nPositive control (good_policy) rate on tuned band: {successes}/{len(results)} = {rate:.3f}")
    # Plan Sec 9 / Gate G1 requires difficulty in the 30% - 80% band
    assert 0.30 <= rate <= 0.80, f"good_policy rate {rate:.3f} outside 30-80% band"


def test_h1_gap_report() -> None:
    """H1: gap = loop - held-out with paired bootstrap 95% CI (10k resamples)."""
    # Create paired trajectory data: 20 trajectories
    # Trajectories where loop success is high and held-out is lower (positive gap)
    rng = np.random.default_rng(42)
    loop_scores = [1.0] * 18 + [0.0] * 2  # 90%
    held_out_scores = [0.6] * 18 + [0.2] * 2  # 56%

    res = compute_h1_gap(loop_scores, held_out_scores, n_resamples=10000, seed=123)
    assert "mean_loop" in res
    assert "mean_held_out" in res
    assert "gap" in res
    assert "ci_lower" in res
    assert "ci_upper" in res

    assert res["gap"] == pytest.approx(0.90 - 0.56, abs=1e-4)
    assert res["ci_lower"] <= res["gap"] <= res["ci_upper"]
    assert len(res["bootstrap_samples"]) == 10000

    # Also verify that a negative or zero gap reports valid CI
    flat_res = compute_h1_gap([0.5] * 20, [0.5] * 20, n_resamples=10000, seed=123)
    assert flat_res["gap"] == pytest.approx(0.0)
    assert flat_res["ci_lower"] <= 0.0 <= flat_res["ci_upper"]


def test_budget_parity_unit() -> None:
    """V6: arm budgets compared; within 5% passes, >5% difference FAILS."""
    # Balanced budgets: within 5%
    balanced_arms = {
        "B0": {"episodes": 100, "tokens": 50000},
        "B1": {"episodes": 102, "tokens": 51000},
    }
    # Should pass without error
    check_budget_parity(balanced_arms, max_rel_diff=0.05)

    # Episode imbalance > 5%
    unbalanced_episodes = {
        "B0": {"episodes": 100, "tokens": 50000},
        "B1": {"episodes": 110, "tokens": 50000},
    }
    with pytest.raises(BudgetParityError, match="episodes.*exceeds"):
        check_budget_parity(unbalanced_episodes, max_rel_diff=0.05)

    # Token imbalance > 5%
    unbalanced_tokens = {
        "B0": {"episodes": 100, "tokens": 50000},
        "B1": {"episodes": 100, "tokens": 55000},
    }
    with pytest.raises(BudgetParityError, match="tokens.*exceeds"):
        check_budget_parity(unbalanced_tokens, max_rel_diff=0.05)


def test_frozen_manifest(tmp_path) -> None:
    """V11: manifest hash = frozen hash, n fixed; outcome-based stopping caught."""
    config_file = tmp_path / "exp_h1.yaml"
    config_file.write_text("model: muse-spark-1.3\nepisodes: 20\n", encoding="utf-8")
    pricing_file = tmp_path / "pricing.yaml"
    pricing_file.write_text("pricing_verified: true\nmuse-spark-1.3: [1.25, 4.25]\n", encoding="utf-8")

    expected_hash = config_hash([config_file, pricing_file])
    manifest = build_manifest(
        run_id="h1-pilot-01",
        git_sha="1234567890abcdef",
        config_hash=expected_hash,
        model="muse-spark-1.3",
        pricing={"muse-spark-1.3": [1.25, 4.25]},
        budget_cap_usd=8.0,
        episodes_planned=20,
        seeds=list(range(1000, 1020)),
        generation={"model": "muse-spark-1.3", "tokens_in": 100, "tokens_out": 200, "cost_usd": 0.001},
        created_at="2026-10-30T00:00:00Z",
    )
    write_manifest(tmp_path, manifest)

    loaded = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert loaded["config_hash"] == expected_hash
    assert loaded["episodes_planned"] == 20
    assert len(loaded["seeds"]) == 20

    # If config file is modified after the run, hash mismatch is detected
    config_file.write_text("model: muse-spark-1.3\nepisodes: 30\n", encoding="utf-8")
    new_hash = config_hash([config_file, pricing_file])
    assert new_hash != loaded["config_hash"]


def test_baselines_harness_structure(tmp_path) -> None:
    """Harness generates valid logs, traces, manifest, and gap table."""
    from experiments.run_baselines import run_baselines
    from closedloop.data.log import read_episodes

    exp_cfg = {
        "experiment": "test_exp",
        "task": "task_T1",
        "model": "muse-spark-1.3",
        "max_output_tokens": 1024,
        "timeout_s": 30,
        "memory_mb": 1024,
        "difficulty": {
            "tier": 2,
            "bounds": {
                "x": [-0.1, 0.1],
                "y": [-0.1, 0.1],
                "yaw": [-0.2, 0.2],
                "mass": [0.05, 5.2],
                "friction": [0.1, 1.0],
            },
        },
        "trajectories": 1,
        "held_out_per_traj": 2,
        "max_repair_rounds": 1,
        "seed": 500,
        "budget_cap_usd": 1.0,
    }
    tasks_cfg = {"task_T1": {"description": "Pick up cube and place on pad."}}
    pricing_cfg = {"muse-spark-1.3": [1.25, 4.25]}

    class FakeBaselineClient:
        def complete(self, model, prompt, max_output_tokens, images_b64=None):
            return {
                "model": model,
                "text": json.dumps({
                    "code": "def policy(env, rng):\n    pass\n",
                    "rationale": "do nothing test policy",
                }),
                "tokens_in": 50,
                "tokens_out": 50,
            }

    res = run_baselines(
        "test-run-01",
        exp_cfg=exp_cfg,
        tasks_cfg=tasks_cfg,
        pricing_cfg=pricing_cfg,
        runs_dir=str(tmp_path),
        pilot=False,
        trajectories_override=1,
        client=FakeBaselineClient(),
    )
    assert res["trajectories"] == 1
    assert "b0" in res and "b1" in res

    run_dir = tmp_path / "test-run-01"
    assert (run_dir / "episodes.jsonl").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "gap_table.json").exists()

    records = read_episodes(run_dir / "episodes.jsonl")
    # 1 traj: B0 has 1 loop + 2 held-out (3 ep); B1 has 1-2 loop + 2 held-out (3-4 ep)
    assert len(records) >= 6
    for r in records:
        assert r.stream == "repair"
        assert r.judge_mode == "state"
        assert (run_dir / r.trace_path).exists()
