# Phase 07 — Vision judge + calibration (Gate G2) — STRETCH

## Goal
Stretch phase (committed baseline is Pitch B, decided Oct 31 go/no-go): build the rendered-footage judge (SAM 3.1 masks + geometric check + Spark verdict) and calibrate it on 300+300 labelled rollouts, then freeze it. Why it matters: decides Pitch A vs B; an unfrozen or boundary-blind judge voids camera-mode certificates. Skipped entirely if P06 missed its Oct 31 gate.

## Inputs
- Plan §8 (judge/calibration), §4 corrected bound; P01 stats, P02 renderer/predicates, P06 repaired programs. Calibration seeds 1M–1999999 only; include repaired programs + falsifier near-misses; bucket FPR by margin (B=4).

## Deliverables
- `closedloop/judge/judge.py`, `closedloop/judge/calibrate.py`, `configs/judge.yaml` (frozen at gate), calibration report (TPR/FPR + CIs per bucket)

## Tasks
1. (90m) Render + SAM masks + geometric check. Done when: masks overlay correctly on 10 inspected frames (human eyeball + centroid-in-pad test).
2. (90m) Spark verdict (structured `{pass, confidence, reason}`) + combination rule — decide geometric∧Spark vs Spark-only, record in DECISIONS.md [OPEN → frozen]. Done when: judge returns verdicts via client/CostMeter only.
3. (90m) Pilot (V15, ~60 rollouts) incl. V9 controls + **cost pre-flight**: project full-calibration cost from pilot-metered per-call cost (state tier + SAM mode actually probed — caps assume Contributor tier, SAM video mode [VERIFY P00]); launch full run only if estimate < remaining `BUDGET_USD_CAP` headroom, else STOP before launch (never let the cap abort mid-run). Then full calibration ≥300 true-success + ≥300 true-failure. Done when: TPR/FPR one-sided CP bounds per bucket computed with P01 stats.
4. (45m) Freeze judge (prompt/threshold/camera hash in config). Done when: freeze hash logged; any later change = new calibration (STOP rule).

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_judge_controls` (V9) | do-nothing pass ≈ FPR; shuffled labels TPR≈FPR | within CI of FPR | judge guessing/task leak |
| `test_calibration_counts` | ≥300/≥300, calibration stream only (V4) | PASS | underpowered bounds |
| `test_judge_frozen` | config hash unchanged after freeze | PASS at P08 start | post-hoc judge tuning |
| `test_bucket_fpr` | worst-bucket b_U reported | present in report | boundary errors hidden |
| `test_cost_preflight` | projected full-run cost from pilot metering vs remaining cap | launch blocked if estimate ≥ headroom | cap aborting a run halfway (invalid run) |

## Validity checks
- V9 controls; V4 stream check; **G2: TPR CI lower ≥0.85, FPR CI upper ≤0.15 (worst bucket), ceiling (P01) ≥0.85.** Fail any → Pitch B, no camera certificates.

## Expected numbers
TPR 0.85–0.98, FPR 0.02–0.15 expected. Outside: FPR >0.15 concentrated in near-boundary bucket → expected failure mode; do not drop bucket — G2 fails honestly.

## Gate
Run: `make gate PHASE=07`. Pass prints `PHASE 07: PASS (G2 PASS)` or `PHASE 07: PASS (G2 FAIL -> Pitch B)` — both are valid phase passes; G2 FAIL blocks camera mode in P08. STOP if calibration uses certification seeds (H9 breach).

## Fallback / cut
Pitch B (committed baseline): SAM annotates failure frames only; P08 state-mode only. Taken on Oct 31 go/no-go, G2 fail, or pre-flight fail — none costs replanning.

## Budget and time-box
Pilot ≤ $4, calibration ≤ $12 API — **only on Contributor tier with SAM in video mode [VERIFY at P00 probe]**; on any other tier/mode the pre-flight estimate governs and may block launch. Agent ≤ $5. Nov 1, G2 at night. Tag `eod-1101` with P08 start.

## Compliance
H4, H5, H9, H12. Hackathon: Use of Meta Tooling (SAM 3.1 + Spark vision).

## Human review (15 min)
View 10 filmstrips with masks (wrong-object masks?), read per-bucket table, confirm freeze hash. Wrong: calibration all easy scenarios (no near-misses).

## Agent run prompt
Read AGENTS.md, plan §8, and this phase file. Run Phase 07 only: pilot + V9 first, 300+300 calibration, freeze, `make gate PHASE=07` with explicit G2 verdict, stop.
