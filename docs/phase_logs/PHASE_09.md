# Phase 09 Plan — Shift test H4

1. Write tests first in `tests/test_shift.py` (`test_shift_config_frozen`, `test_shift_disjoint_seeds`, `test_h4_shift_refusal`, `test_shift_detectable_stats`) and verify they fail for the right reasons.
2. Freeze `configs/shift.yaml` defining shifted distribution $D'$ (wider pose $[-0.20, 0.20]$, heavier mass $[6.0, 14.0]$ kg, lower friction $[0.05, 0.40]$) and sample sizes ($n_{\text{pilot}}=30$, $n_{\text{shift}}=300$), logging pre-run config hash (V11) and recording explicit T2 cut in `docs/DECISIONS.md`.
3. Implement `experiments/run_shift.py` and shift analysis in `closedloop/certify/shift.py`, enforcing single-use seeds in certification stream $[2000000, 2999999]$ disjoint from Phase 08 via `CertificationLedger` (H9, V4).
4. Run pilot ($n=30$, V15) and full shift experiment ($n=300$), evaluating the Phase 08 certified program `bec73dec45a88431` on $D'$, computing empirical pass rates and recertified Clopper-Pearson bounds, and generating shift figure data from raw logs (H10, H11).
5. Update `Makefile` with Phase 09 gate, run `make gate PHASE=09`, paste full command output into `docs/phase_logs/PHASE_09.md`, verify all locked hashes and controls, and stop.
