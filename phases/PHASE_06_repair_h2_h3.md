# Phase 06 — Repair engine + H2 + H3

## Goal
Repair programs from minimal counterexamples (B2 text, B3 text+filmstrip) and test H2/H3 at equal budget. Why it matters: core Impact claim; unfair budgets or leaky regression sets would fake the result.

## Inputs
- Plan §10, §12; P04 harness, P05 falsifier/minimizer. Arms: B1 (random feedback), B2 (falsifier, text), B3 (B2 + 4–6-frame filmstrip). Max 5 rounds/trajectory [OPEN — freeze in config]; same episodes/rounds/token cap per trajectory.

## Deliverables
- `closedloop/repair/repair.py` (accept iff: passes counterexample + regression set + short falsifier re-run), `configs/exp_h2h3.yaml` (frozen), run logs + paired-diff tables

## Tasks
1. (90m) Acceptance + regression-set tests first, then repair loop. Done when: acceptance tests pass.
2. (90m) A/A harness (same arm twice) + budget-parity enforcement. Done when: V5/V6 pass on pilot.
3. (90m) Pilot (V15, ~10%) → full: ≥20 trajectories/arm/task (T1; T2 only if P09 keeps it). Done when: H2/H3 paired bootstrap CIs (10k) + repair/damage rates generated.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_repair_acceptance` | repair failing regression set rejected | rejected | regressions shipped |
| `test_aa_null` (V5) | same arm twice, paired diff CI; on first exclude-0, one pre-declared fresh-seed rerun (false-alarm rate 1/20) | rerun CI contains 0; two exclude-0 = biased | harness bias vs chance |
| `test_budget_parity` (V6) | episodes + tokens per arm | within 5% else FAIL | unfair comparison |
| `test_h2_paired_diff` / `test_h3_paired_diff` | paired bootstrap CI from logs | CI reported, any sign valid | anecdote-as-result |

## Validity checks
- V5 CI contains 0 (pilot + full), with exactly one fresh-seed A/A rerun allowed before declaring bias (pre-declared here; a 95% CI excludes 0 ~1 time in 20 by chance — two independent exclude-0 results ≈ 1/400). V6 ≤5%; V7 damage counted; V11 frozen. Null/negative H2/H3 are valid findings.

## Expected numbers
Repair rate 10–90%, damage rate < repair rate expected but not gated. Outside: first A/A exclude-0 → fresh-seed rerun; second exclude-0 → STOP, fix harness before interpreting H2/H3. Damage >30% → inspect acceptance rule, do not relax it (H7).

## Gate
Run: `make gate PHASE=06`. Pass: tests + V5 (incl. allowed rerun) + V6 pass, prints `PHASE 06: PASS`. STOP after 3 harness fixes. **Oct 31 EOD go/no-go: gate not passed → skip P07, committed Pitch B, P08 state-only (README calendar).**

## Fallback / cut
Cut SAM-tool arm first, then forensic tool loop (never implemented unless ahead). Keep B1/B2/B3 + filmstrip.

## Budget and time-box
Pilot ≤ $4, full ≤ $12 API; agent ≤ $5. Oct 31 (full day). Pilots for P07/P08 must also finish today (V15 deadline). Tag `eod-1031`.

## Compliance
H5, H9, H11–H13, H15. Certification seeds never in repair (H9).

## Human review (15 min)
Compare arm budgets, A/A CI, 2 accepted + 1 rejected repair traces. Wrong: token counts differing by arm design (filmstrip tokens must count toward B3 cap).

## Agent run prompt
Read AGENTS.md, plan §10/§12, and this phase file. Run Phase 06 only: acceptance tests first, A/A pilot, frozen full run ≥20/arm, `make gate PHASE=06`, stop.
