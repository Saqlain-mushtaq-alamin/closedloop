# Phase 09 — Shift test H4 (+ optional T2)

## Goal
Show the D-certificate does not transfer to shifted D′ and that recertification on D′ refuses or lowers the bound. Why it matters: H4 is the honesty figure — it bounds every claim in the demo and README.

## Inputs
- Plan §12 shift test; P08 certificate + final program. D′: wider/heavier, lower friction (frozen in config before running). Optional T2 (push task) only if P04–P08 ahead of calendar.

## Deliverables
- `configs/shift.yaml` (frozen D′), `experiments/run_shift.py`, shift figure data (D bound vs D′ empirical + recertified bound)

## Tasks
1. (45m) Freeze D′ + sample sizes. Done when: config hash logged pre-run (V11).
2. (90m) Pilot (V15, ~10%) then full: evaluate certified program on D′, recertify on D′ fresh seeds. Done when: figure data generated from logs.
3. (Optional, 90m) T2 smoke: B0 only, ≥20 trajectories, gap reported. Done when: logged or explicitly cut in DECISIONS.md.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_h4_shift_refusal` | D′ recertified bound < D bound or refusal (0/below target) | holds, or investigated | bound/sampler bug (plan H4) |
| `test_shift_disjoint_seeds` (V4) | D′ eval uses fresh seeds, no reuse | PASS | inflated D′ success |
| `test_shift_config_frozen` (V11) | D′ defined before outcomes | PASS | shift tuned to pass |

## Validity checks
- V4, V11, V15 pilot. If D′ bound does NOT drop: valid to report only after checking sampler actually shifted (test distribution stats differ) — plan H4 says investigate bound/sampler.

## Expected numbers
D′ empirical success below D (direction expected, magnitude not gated). No drop with verified shift → STOP, audit P01/P08 before claiming.

## Gate
Run: `make gate PHASE=09`. Pass: figure data + tests, prints `PHASE 09: PASS`. STOP if shift not detectable in scenario stats (sampler bug).

## Fallback / cut
Cut T2 first (always optional). Never cut the shift figure — shrink sample size per frozen pilot instead.

## Budget and time-box
≤ $4 API (state mode default); agent ≤ $3. Nov 2 AM. Tag `eod-1102`.

## Compliance
H9, H11, H12, H14 ("under distribution D" wording).

## Human review (15 min)
Plot D vs D′ scenario histograms (really shifted?); read figure caption wording. Wrong: caption implying real-world safety.

## Agent run prompt
Read AGENTS.md, plan §12, and this phase file. Run Phase 09 only: freeze D′, pilot, full shift test, `make gate PHASE=09`, stop. T2 only if instructed.
