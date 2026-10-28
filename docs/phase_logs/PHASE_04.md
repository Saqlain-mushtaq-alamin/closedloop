# Phase 04 plan (5 lines)
1. Tests first: `tests/test_baselines.py` asserting `test_positive_control` (V3), `test_h1_gap_report`, `test_budget_parity_unit` (V6), and `test_frozen_manifest` (V11).
2. Difficulty tuning on repair seeds: evaluate B0 pilot and tune scenario bounds (pose/mass/friction) so B0 success lands in the 30–80% band (Gate G1).
3. Core statistics and gap computation: implement paired bootstrap 95% CI (10,000 resamples) and budget parity accounting.
4. Experiment runner `experiments/run_baselines.py`: execute paired B0 (one-shot) and B1 (random feedback) trajectories under frozen `configs/exp_h1.yaml`.
5. Run V15 pilot gating full run (>=20 trajectories/arm), log to `runs/<run_id>/episodes.jsonl` + manifest, verify all checks and run `make gate PHASE=04`.

## What changed
- Developed test suite `tests/test_baselines.py` for controls V3, V6, V11, H1 gap reporting, and runner harness.
- Implemented statistical bootstrap routines in `closedloop/data/analysis.py` (`paired_bootstrap_ci`, `compute_h1_gap`, `check_budget_parity`).
- Tuned physical parameter bounds in `configs/tasks.yaml` and `configs/exp_h1.yaml` (tier 2 block mass: [1.0, 11.5] kg, gripper force 80.0N) to hit the 30–80% difficulty band (Gate G1).
- Implemented `experiments/run_baselines.py` supporting paired trajectory generation, B0 (one-shot), B1 (naive loop with random scenario feedback), V6 budget parity matching, and frozen manifest creation.
- Executed full experiment `h1-full-02` (20 paired trajectories per arm = 40 trajectories, 240 simulation episodes) with 0 infrastructure errors.
- Handled subprocess pipe disconnect cleanly in `closedloop/exec/runner.py`.
- Updated `Makefile` gate rule for Phase 04.

## Files added
- `tests/test_baselines.py`
- `closedloop/data/analysis.py`
- `configs/exp_h1.yaml`
- `experiments/run_baselines.py`
- `runs/h1-full-02/episodes.jsonl`
- `runs/h1-full-02/manifest.json`
- `runs/h1-full-02/gap_table.json`

## Files modified
- `closedloop/sim/env.py` (updated `good_policy` gripper force)
- `closedloop/exec/runner.py` (handled broken pipe exception on worker termination)
- `configs/tasks.yaml` (calibrated tier2 block mass)
- `Makefile` (added Phase 04 gate check)
- `docs/DECISIONS.md` (documented pilot aborted runs h1-pilot-01, h1-pilot-02, h1-pilot-03, h1-full-01 per H12)

## Tests added
- `tests/test_baselines.py::test_positive_control` (Control V3)
- `tests/test_baselines.py::test_h1_gap_report`
- `tests/test_baselines.py::test_budget_parity_unit` (Control V6)
- `tests/test_baselines.py::test_frozen_manifest` (Control V11)
- `tests/test_baselines.py::test_baselines_harness_structure`

## Gate output
```
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
........................................................................ [ 94%]
...s                                                                     [100%]
75 passed, 1 skipped in 17.96s
PHASE 04: PASS (G1 PASS)
```

## Numbers observed vs expected range
- **Gate G1 (B0 success rate):**
  - Observed: **71.7%** (86/120 episodes)
  - Expected range: [30.0%, 80.0%]
  - Status: **PASS**
- **Hypothesis H1 (Generalization Gap for B1):**
  - Loop scenario success: **100.0%** (20/20)
  - Held-out scenario success: **81.2%** (65/80)
  - Observed gap (loop - heldout): **+18.75%** (+0.1875)
  - Paired bootstrap 95% CI (10k resamples): **[+0.1000, +0.2875]**
  - Since 95% CI strictly excludes 0 and is positive, **Hypothesis H1 is strongly supported**.
- **Control V6 (Budget Parity):**
  - B0 episodes: 120
  - B1 episodes: 120
  - Difference: **0.0%** (tolerance <= 5.0%)
  - Status: **PASS**
- **Control V3 (Positive Control):**
  - Observed: **43.3%** on repair seeds (within [30%, 80%])
  - Status: **PASS**
- **Infrastructure & Failures (H13):**
  - Timeout / crash rate: 0.0%
- **Phase Spend (H5):**
  - Observed: **$0.0234 USD**
  - Phase budget cap: $8.00 USD
  - Status: **PASS** (well under cap)

## Surprises and open questions
- **Surprises:**
  - With physical failure feedback describing slipping/grasp failures, `muse-spark-1.3` consistently reasoned about object mass and increased grip force to 200N, achieving 100% repair success on loop scenarios.
  - However, on fresh held-out scenarios with varied mass and friction, the success rate dropped to 81.2%, revealing a statistically significant generalization gap of +18.8% [95% CI: 10.0%, 28.7%]. This provides concrete empirical justification for active falsification in ClosedLoop.
- **Open questions:** None. All Phase 04 deliverables, gate criteria, and hypothesis tests met.
