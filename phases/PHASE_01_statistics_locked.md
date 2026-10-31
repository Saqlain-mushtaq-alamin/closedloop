# Phase 01 — Statistics module (LOCKED)

## Goal
Implement and lock the certificate math (Clopper-Pearson, corrected judge bound, ceiling) with coverage proof. Why it matters: every headline number depends on this; it becomes read-only (H6) after this phase.

## Inputs
- Plan §4, §11, Appendix A; P00 repo + `scripts/check_locked.sh`.

## Deliverables
- `closedloop/certify/stats.py`, `tests/test_stats.py`, `tests/test_coverage.py`, `scripts/ceiling.py`, `LOCKED_HASHES.txt`

## Tasks
1. (60m) Tests first: known values (29/59/299 single; 55/113 per-cell), monotonicity, edge k=0/k=n. Done when: tests fail on empty module for the right reason.
2. (90m) `stats.py`: `cp_lower/cp_upper/corrected_lower/ceiling` per fixed Appendix A — `ceiling()` simulates per-bucket FPR (n_fail/B per bucket, worst bucket wins) and per-cell split `0.8*delta/(K*M)`. Done when: unit tests pass.
3. (90m) Coverage + independent SciPy cross-check (thousands synthetic trials). Done when: V10 passes (below).
4. (30m) Lock: hashes into `LOCKED_HASHES.txt`, verify `check_locked.sh`. Done when: script PASS; never edit again (H6).

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_cp_known_values` | zero-failure n for p/delta grid | 29/59/299; 55/113 | off-by-one, wrong tail |
| `test_cp_vs_scipy` (V10) | matches independent `scipy.stats.binomtest(k, n).proportion_ci(method="exact")` (never `scipy.stats.beta`, which the code itself uses) | agree to 1e-9 (0 mismatches expected) | wrong Beta params / tail |
| `test_coverage_synthetic` (V10) | bound ≤ true p ≥95% (state + corrected) | ≥95% of trials | invalid corrected bound |
| `test_corrected_guards` | q_L≤b_U or a_U≤b_U → 0.0 | 0.0 | certifying noise |
| `test_ceiling_monotone` | ceiling ↑ with n_cell, labels | monotone | budget mis-sizing |
| `test_ceiling_bucket_split` | failure labels split across B=4 buckets (n_fail/B each); ceiling uses worst-bucket `b_U`, not pooled n_fail | bucket-split ceiling ≤ pooled ceiling; pooled version must FAIL this test | ceiling overstated when B>1 |

## Validity checks
- V10 is the gate: coverage ≥95% at delta=0.05; SciPy agreement. Corrected-bound literature status stays [VERIFY] — claim only "derived for this project".

## Expected numbers
Ceiling at a=0.95, b=0.02, 300+300 labels, n_cell=150, K=16: prints value in (0,1]; record it. Outside [VERIFY range]: if median ceiling <0.85 even at a=0.95/b=0.02, flag for G2 risk now, do not retune delta.

## Gate
Run: `make gate PHASE=01`. Pass: tests + `check_locked.sh` pass, prints `PHASE 01: PASS`. STOP if: coverage <95% after 3 fixes — report, do not loosen (H7).

## Fallback / cut
None for math. If ceiling is low, keep module; decision deferred to G2/P08 targets.

## Budget and time-box
0 episodes/API $0; agent ≤ $3. Half day, Oct 28 PM. Tag `eod-1028`.

## Compliance
H6, H7, H12 (delta=0.05 frozen in config). Hackathon: Technical Depth.

## Human review (15 min)
Read `stats.py` vs Appendix A line by line; check `LOCKED_HASHES.txt`; run `make gate PHASE=01`. Wrong: any delta not from config, coverage printed without trial count.

## Agent run prompt
Read AGENTS.md, the plan §4/§11/Appendix A, and this phase file. Run Phase 01 only: tests first, lock hashes, `make gate PHASE=01`, stop. Never edit locked files after locking.
