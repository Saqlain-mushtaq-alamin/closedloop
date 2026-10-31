# Phase 04 — Baselines B0/B1 + H1 (Gate G1)

## Goal
Measure one-shot (B0) vs naive loop (B1) and the H1 generalization gap at pilot then full pilot-scale. Why it matters: G1 proves difficulty is in the measurable band; H1 justifies (or refutes) falsification.

## Inputs
- Plan §9 (30–80% band), §12; P02 env, P03 generator/runner. Arms: B0 one-shot, B1 random-seed feedback; equal episodes/rounds/tokens.

## Deliverables
- `experiments/run_baselines.py`, `configs/exp_h1.yaml` (frozen), `runs/<run_id>/episodes.jsonl` + manifest, gap table (generated)

## Tasks
1. (60m) Difficulty tuning on repair-stream seeds only. Done when: B0 pilot (10%, ~20 traj) in 30–80% or retuned once.
2. (90m) B0/B1 harness with paired scenarios + bootstrap CI code (tests first). Done when: V3/V6 unit checks pass on pilot logs.
3. (90m) Pilot run (V15, ~10%) → check V1–V14 subset → full run ≥20 trajectories/arm on T1. Done when: manifest config hash frozen, gap + CI generated from logs.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_positive_control` (V3) | hand-written good program | in tuned band (record band) | broken env/predicate |
| `test_h1_gap_report` | gap = loop − held-out, paired bootstrap 95% CI (10k) | CI reported, either sign valid | cherry-picked scenarios |
| `test_budget_parity_unit` (V6) | arm budgets compared | within 5% or FAIL | unfair arms |
| `test_frozen_manifest` (V11) | manifest hash = frozen hash, n fixed | PASS | outcome-based stopping |

## Validity checks
- V2/V3 controls in-run; V6 parity ≤5%; V11 frozen; V15 pilot gates full run. Negative H1 (gap ≈0) is a valid finding — report as-is.

## Expected numbers
**G1: B0 success 30–80%.** Gap: any value with CI; |gap| <2 pts with wide CI → underpowered, do not extend post-hoc (H12) — note as limitation. Outside band: retune difficulty (pose range, mass/friction) on repair seeds only, new run_id.

## Gate
Run: `make gate PHASE=04`. Pass: tests + G1 in band, prints `PHASE 04: PASS (G1 PASS)`. STOP if band unreachable after 2 retunes.

## Fallback / cut
Hero task T1 only (already default). Reduce trajectories? No — floor is 20/arm (plan §12); cut T2 instead (P09 optional).

## Budget and time-box
Pilot ≤ $3, full ≤ $8 API; episodes per manifest; agent ≤ $4. Oct 30 AM. Tag `eod-1030` with P05.

## Compliance
H9, H11, H12, H13. No certification seeds touched.

## Human review (15 min)
Check manifest hash, arm episode counts (within 5%), gap CI, 3 raw episodes. Wrong: held-out scenarios overlapping loop scenarios, hand-typed numbers.

## Agent run prompt
Read AGENTS.md, plan §9/§12, and this phase file. Run Phase 04 only: pilot first, freeze config, ≥20 trajectories/arm, `make gate PHASE=04`, stop. Report gap with CI from logs.
