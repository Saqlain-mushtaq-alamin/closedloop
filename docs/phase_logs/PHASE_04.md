# Phase 04 plan (5 lines)
1. Tests first: `tests/test_baselines.py` asserting `test_positive_control` (V3), `test_h1_gap_report`, `test_budget_parity_unit` (V6), and `test_frozen_manifest` (V11).
2. Difficulty tuning on repair seeds: evaluate B0 pilot and tune scenario bounds (pose/mass/friction) so B0 success lands in the 30–80% band (Gate G1).
3. Core statistics and gap computation: implement paired bootstrap 95% CI (10,000 resamples) and budget parity accounting.
4. Experiment runner `experiments/run_baselines.py`: execute paired B0 (one-shot) and B1 (random feedback) trajectories under frozen `configs/exp_h1.yaml`.
5. Run V15 pilot gating full run (>=20 trajectories/arm), log to `runs/<run_id>/episodes.jsonl` + manifest, verify all checks and run `make gate PHASE=04`.
