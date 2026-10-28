# Phase 01 plan (5 lines)
1. Tests first: `tests/test_stats.py` (known values, monotonicity, guards) + `tests/test_coverage.py` (V10) failing on empty module.
2. `closedloop/certify/stats.py`: pure `cp_lower/cp_upper/corrected_lower/ceiling` per fixed Appendix A (worst-bucket ceiling, `(K*M)` split).
3. `scripts/ceiling.py` CLI; record ceiling at a=0.95/b=0.02/300+300/n=150/K=16 for G2 risk flag.
4. Coverage proof: thousands of synthetic trials, state + corrected bound, plus `binomtest` exact-CI agreement (never `scipy.stats.beta` in tests).
5. Lock `LOCKED_HASHES.txt` (`stats.py`, both test files), verify `check_locked.sh`, `make gate PHASE=01` (or gate steps if `make` still missing).

## Gate output (2026-10-28; `make` still missing — gate steps run directly)
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
14 passed in 4.18s
PHASE 01: PASS
Numbers observed vs expected: known values 29/59/299 + 55/113 exact;
binomtest agreement 0 mismatches (after fixing my own oracle: one-sided 95%
= two-sided 90% low end, proved to 12 decimals); state coverage 0.9633
(>=0.95); corrected coverage 0.9993 (>=0.95, conservative as expected);
ceiling(a=0.95,b=0.02,300+300,n=150,K=16,B=4) = 0.8815 — above 0.85, no G2-risk
flag (modest headroom for the 0.85 camera target).
Open questions: (1) invoked file/plan paths differ in case from the phase
prompt (`PHASE_01_statistics_locked.md`, `planning/ClosedLoop_Plan.md` — used
the real files); (2) repo-local git identity set to the human's stated values
because the global config is empty in this shell.
Surprises: none in the math; `make` binary still absent (human to install).
