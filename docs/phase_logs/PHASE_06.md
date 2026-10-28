# Phase 06 plan (5 lines)
1. Write tests first in `tests/test_repair.py` covering acceptance verification (`test_repair_acceptance`), A/A null control (`test_aa_null` V5), budget parity (`test_budget_parity` V6), and paired difference bootstrap CIs (`test_h2_paired_diff`, `test_h3_paired_diff`).
2. Implement `closedloop/repair/repair.py`: 3-stage acceptance rule (passes minimal counterexample, passes accumulated regression set, survives short falsifier re-run) with damage tracking (V7).
3. Implement filmstrip rendering and vision prompt builder in `closedloop/repair/filmstrip.py` for Arm B3 (4-6 frames at event boundaries) and text prompt builder for Arm B2.
4. Create frozen `configs/exp_h2h3.yaml` enforcing equal budget limits (rounds, episodes, token cap per trajectory) and experiment runner `experiments/run_repair_h2h3.py`.
5. Execute A/A pilot (V5/V6 verification) gating full run (>=20 trajectories/arm), generate paired bootstrap 95% CIs for H2/H3, and run `make gate PHASE=06`.
