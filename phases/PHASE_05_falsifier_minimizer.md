# Phase 05 — Falsifier + minimizer

## Goal
Find low-margin failures with Optuna/CMA-ES and shrink each to a minimal still-failing scenario. Why it matters: H2's claimed advantage lives or dies on counterexample quality, not search volume.

## Inputs
- Plan §8, §10; P02 margin/predicates, P03 runner. Search within distribution D bounds only.

## Deliverables
- `closedloop/falsify/falsifier.py` (CmaEsSampler, margin objective), `closedloop/falsify/minimizer.py` (shrink toward nominal), `configs/falsify.yaml`

## Tasks
1. (60m) Minimizer tests first (below), then shrinking step. Done when: minimizer tests pass on synthetic failing scenarios.
2. (90m) Falsifier: seeded Optuna study, fixed evaluation budget, failures sorted by margin. Done when: finds failures B1-random misses at equal budget on pilot programs (record rate; either direction logged).
3. (60m) Pilot (V15): 5 programs, fixed budget; log sims-to-first-failure. Done when: pilot table generated from logs.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_minimizer_still_fails` | shrunk scenario still fails | truth=False | "minimal" that passes |
| `test_minimizer_not_larger` | distance-to-nominal ≤ input | ≤ input | shrink that wanders |
| `test_falsifier_seeded` (V1) | same seed → same study result | identical best margin | unseeded search |
| `test_falsifier_bounds` | all proposals inside D | PASS | certifying outside D |

## Validity checks
- V1 seeded reproducibility; falsifier uses repair-stream seeds only (V4). Failure = margin<0 AND both predicates (V8 rule).

## Expected numbers
Falsifier first-failure within budget on known-weak programs: expect >0 failures; if 0 on programs with <80% success, check margin sign before scaling. No target rate is a gate — quality feeds P06.

## Gate
Run: `make gate PHASE=05`. Pass: tests pass, prints `PHASE 05: PASS`. STOP if minimizer output passes in >0 test cases (core bug).

## Fallback / cut
Random-search fallback with same budget if CMA-ES unstable — log choice; H2 comparison stays equal-budget. Do not add research-grade falsifier (out of scope).

## Budget and time-box
Sim-only, API $0; ≤2,000 pilot episodes; agent ≤ $3. Oct 30 PM. Tag `eod-1030`.

## Compliance
H9, H12, H16. [LOCKED] Optuna/CMA-ES + shrinking step unchanged.

## Human review (15 min)
Inspect 3 minimal counterexamples (few non-nominal params?); rerun one — still fails? Wrong: minimized scenario with all params extreme (shrink did nothing).

## Agent run prompt
Read AGENTS.md, plan §8/§10, and this phase file. Run Phase 05 only: minimizer tests first, seeded falsifier pilot, `make gate PHASE=05`, stop.
