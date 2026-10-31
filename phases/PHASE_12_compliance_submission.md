# Phase 12 — Compliance audit + submission + finals prep

## Goal
Audit the whole submission, fix only blockers, tag `submission-v1`, and leave a stable finals fallback. Why it matters: a valid result with a compliance miss is not submittable; Nov 4 must stay buffer, not repair day.

## Inputs
- Plan §17 checklist; all phase logs, `runs/`, P10 dashboard, P11 video/README/report. Independent audit prompt: `02_PHASE_PROMPTS.md` §C (Wonder, high).

## Deliverables
- `docs/SUBMISSION_DRAFT.md` (form fields filled [VERIFY via live submit page]), audit report in phase log, tag `submission-v1`, finals fallback note (stable dashboard + opt. 45 s clip)

## Tasks
1. (90m) Full audit: secrets (tree+history), licences, locked hashes, spend vs cap, V1–V15 evidence listed. Done when: audit table PASS/FAIL per item with evidence.
2. (60m) Human: open Official Rules + submit page; confirm eligibility, track, form fields, rubric weights, finals (Nov 9) terms [VERIFY]. Done when: confirmations recorded; discrepancies logged, not assumed.
3. (60m) Submit before Nov 3 midnight target; tag `submission-v1`; verify public repo + video link logged-out. Done when: submission receipt + tag recorded.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_final_compliance_scan` (V13) | secrets/licences/wording/THIRD_PARTY | PASS | disqualifying miss |
| `test_full_regeneration` (V12) | report twice byte-identical at tagged commit | PASS | non-reproducible headline |
| `test_submission_package` | public repo, video ≤3:00 no-login, contributors, tag exists | PASS | broken submission |

## Validity checks
- All V1–V15 evidenced (VALIDITY_CHECKLIST fully ticked). Any FAIL = fix code/data, new run_id if experimental (H12); never edit tests (H7).

## Expected numbers
Spend: phase caps sum to agents ≤$50 + API ≤$71 = $121 within $150 credits (actuals from CostMeter; [VERIFY credits claimed before Nov 4, 9 PM ET]). Over → report honestly; do not hide calls.

## Gate
Run: `make gate PHASE=12`. Pass prints `PHASE 12: PASS` and tag exists. STOP (no submit) on secrets found, locked-hash mismatch, or unreproducible headline.

## Fallback / cut
Submit Pitch B state if G2 failed; submit smaller valid result over larger doubtful one. Nov 4: resubmit only for broken-link fixes.

## Budget and time-box
API ≤ $2 (verification calls only); agent ≤ $4. Nov 3 PM. Finals: keep tagged dashboard runnable; rehearse live (Nov 9) from precomputed assets.

## Compliance
All H1–H17. Hackathon: submission package, IP licence, disclosure, credit claim.

## Human review (15 min)
You submit personally: re-open repo+video logged-out, read audit FAIL list (must be empty), confirm tag. Wrong: any CANNOT-CHECK treated as PASS.

## Agent run prompt
Read AGENTS.md, the plan, all phase logs, and this phase file. Run Phase 12 audit only until I confirm: full V1–V15/compliance audit with evidence, draft submission, `make gate PHASE=12`. Do not submit or tag until I say so.
