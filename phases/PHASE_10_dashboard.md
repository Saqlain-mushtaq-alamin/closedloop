# Phase 10 — Dashboard + precomputed assets (Gate G3)

## Goal
Generate every demo asset (heatmap, filmstrip, plots, clips) from logs into a stable precomputed dashboard. Why it matters: Demo criterion (25% [VERIFY]) must survive without live API calls; G3 freezes features here.

## Inputs
- Plan §13; logs from P04/P06/P07/P08/P09 runs. No new experiments in this phase.

## Deliverables
- `dashboard/` (static/precomputed), `assets/` (heatmap, filmstrip w/ SAM masks, price plot, shift figure, clips), asset manifest linking each asset → run_id

## Tasks
1. (90m) Figure/clip generators reading logs only. Done when: each asset regenerates from `runs/` (V12 test below).
2. (60m) Dashboard assembly (rollout beside heatmap, run log w/ tokens/cost). Done when: opens offline, zero API calls (network-blocked check).
3. (45m) Freeze declared. Done when: `docs/DECISIONS.md` freeze entry + tag; further changes only via P11 text.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_regeneration_determinism` (V12) | `make report` twice | byte-identical outputs | hand-edited figures |
| `test_asset_provenance` (H11) | every asset maps to run_id + config hash | PASS | orphan/demo-only numbers |
| `test_dashboard_offline` | dashboard loads with network disabled | PASS, no API calls | live-call demo failure |

## Validity checks
- V12 byte-identical; G3: after this gate, features frozen — bugs only, no new arms/tasks.

## Expected numbers
Asset count matches manifest; regeneration hash stable. Mismatch → regenerate from logs, never patch numbers.

## Gate
Run: `make gate PHASE=10`. Pass prints `PHASE 10: PASS (G3 FREEZE)`. STOP if any asset lacks provenance.

## Fallback / cut
Static images + clips without interactive dashboard (finals fallback still needs one stable version — keep simplest offline page).

## Budget and time-box
API $0; agent ≤ $3. Nov 2 PM. Tag `eod-1102`.

## Compliance
H11, H16. Hackathon: finals stable precomputed version.

## Human review (15 min)
Open dashboard offline; click each asset to its run_id; run `make report` twice, diff hashes. Wrong: polished plot with no source run.

## Agent run prompt
Read AGENTS.md, plan §13, and this phase file. Run Phase 10 only: log-only generators, offline dashboard, freeze, `make gate PHASE=10`, stop.
