# ClosedLoop — Phase Index

Solo, 12-core CPU, 8 GB GPU (sim on CPU, models via Meta Model API). Submit target Nov 3; Nov 4 buffer. No reruns: pilot before every full run (V15).

## Index

| Phase | File | Day (revised) | Gate |
|---|---|---|---|
| 00 Repo, compliance, environment | [PHASE_00_repo_compliance_env.md](PHASE_00_repo_compliance_env.md) | Oct 28 AM | — |
| 01 Statistics (LOCKED) | [PHASE_01_statistics_locked.md](PHASE_01_statistics_locked.md) | Oct 28 PM | — |
| 02 Simulator, T1, sampler | [PHASE_02_simulator_sampler.md](PHASE_02_simulator_sampler.md) | Oct 28–29 | — |
| 03 Sandbox runner + generator | [PHASE_03_sandbox_generator.md](PHASE_03_sandbox_generator.md) | Oct 29 | G0 |
| 04 Baselines B0/B1 + H1 | [PHASE_04_baselines_h1.md](PHASE_04_baselines_h1.md) | Oct 30 AM | G1 |
| 05 Falsifier + minimizer | [PHASE_05_falsifier_minimizer.md](PHASE_05_falsifier_minimizer.md) | Oct 30 PM | — |
| 06 Repair + H2 + H3 | [PHASE_06_repair_h2_h3.md](PHASE_06_repair_h2_h3.md) | Oct 31 | — |
| 07 Vision judge + calibration | [PHASE_07_vision_judge.md](PHASE_07_vision_judge.md) | Nov 1 | G2 (moved) |
| 08 Certification | [PHASE_08_certification.md](PHASE_08_certification.md) | Nov 1–2 | — |
| 09 Shift test H4 (+ opt. T2) | [PHASE_09_shift_h4.md](PHASE_09_shift_h4.md) | Nov 2 AM | — |
| 10 Dashboard + assets | [PHASE_10_dashboard.md](PHASE_10_dashboard.md) | Nov 2 PM | G3 freeze |
| 11 Demo, README, report | [PHASE_11_demo_readme_report.md](PHASE_11_demo_readme_report.md) | Nov 3 AM | — |
| 12 Compliance + submission | [PHASE_12_compliance_submission.md](PHASE_12_compliance_submission.md) | Nov 3 PM | Tag |

Traceability: [TRACEABILITY.md](TRACEABILITY.md). Pre-trust checklist: [../docs/VALIDITY_CHECKLIST.md](../docs/VALIDITY_CHECKLIST.md).

## Dependency graph

```text
P00 -> P01 -> P08 (stats locked first)
P00 -> P02 -> P03 -> P04 -> P05 -> P06 -> P08
P02 -> P07 (needs renderer+margin) ; P06 -> P07 (repaired programs in calibration)
P07 -> P08 (frozen judge) -> P09 -> P10 -> P11 -> P12
P04 - - > P06 (equal-budget harness reused)
```

## Calendar Oct 27 – Nov 4 (revised; proposed calendar infeasible, see Open questions)

| Date | Work | EOD tag |
|---|---|---|
| Oct 27 (past) | Plan only; billing fix [VERIFY] | — (slip noted) |
| Oct 28 | P00 AM, P01 PM, start P02 | `eod-1028` |
| Oct 29 | Finish P02, P03, G0 | `eod-1029` |
| Oct 30 | P04 AM (G1), P05 PM | `eod-1030` |
| Oct 31 | P06; pilots for P07/P08 done by today (V15). **EOD go/no-go (below)** | `eod-1031` |
| Nov 1 | Stretch path: P07 (G2 night), start P08. Baseline path: P08 state-only | `eod-1101` |
| Nov 2 | AM: finish P08, P09 (last experiments). PM: P10, **G3 freeze**, then QA only | `eod-1102` |
| Nov 3 | P11 AM, P12 PM, submit | `submission-v1` |
| Nov 4 | Buffer only; claim credits before 9 PM ET | — |

Feasibility verdict: proposed calendar (G2 Oct 30 night) is **not feasible** — P06 (repair, ≥20 traj/arm) + 600 calibration rollouts cannot both finish Oct 30. G2 moves to Nov 1 night. Nov 2 AM is the last experiment window; from G3 (Nov 2 PM) it is freeze+QA only, no new experiments.

**Pitch B is the committed baseline; the vision judge (P07) is a stretch.** Early go/no-go, end of Oct 31: if P06 has not passed its gate, skip P07 entirely, take Pitch B (state certificates + SAM-annotated frames), and run P08 state-only on Nov 1. Even if P06 passes, P07 runs only if its cost pre-flight (P07) passes; a G2 fail also lands on Pitch B with no schedule loss.

## Gates (copied from plan §14; G2 date moved, conditions unchanged)

| Gate | When (plan → revised) | Pass condition | If failed |
|---|---|---|---|
| G0 | Oct 27–28 → Oct 29 | Spark passes ≥30% of tier-1 tasks. | Simplify primitives or tasks. |
| G1 | Oct 28 → Oct 30 | One-shot success 30–80% on hero task. | Retune difficulty. |
| G2 | Oct 30 → Nov 1 | Judge TPR CI lower ≥0.85, FPR CI upper ≤0.15, ceiling ≥0.85. | Pitch B; SAM only annotates frames. |
| G3 | Nov 2 → Nov 2 | Features frozen. | Cut by cut order. |

## Cut order (plan §3, §14, as amended Oct 28)

1. SAM-tool arm (H3 third arm). 2. Forensic tool-calling loop (keep static filmstrip). 3. Vision judge → Pitch B. Note: the Oct 31 go/no-go promotes item 3 to an explicit schedule gate — Pitch B is pre-committed as baseline, so taking it costs no replanning.

## Open questions — contradictions and gaps (not silently fixed)

1. **State target — DECIDED Oct 28:** heatmap cells p≥0.90 state (55 zero-failure/cell) / p≥0.85 camera; headline single certificate p≥0.95. At 0.95/cell, n=200 allows ~2 failures (power ~24% at true 0.98 — verified by computation); at 0.90/cell, n=150 allows 5 (~92%). Plan §11 updated.
2. **Demo length:** plan §13 beats sum to 3:00 vs 2:45 aim. P11 re-times to 2:45.
3. **Calendar slip:** plan §14 starts Oct 27; today is Oct 28 (day 3). P00–P02 compressed; G0/G1 dates moved (above).
4. **T3 undecided** [OPEN]: MVP lists 3 tasks, roadmap runs 1 hero task. Default: T1 only; T2 only in P09 if ahead.
5. **Judge combination rule, frames-vs-video, runs/cell (camera), M, repair budget** [OPEN] in plan §8/§11/§17 — decided in P07/P08 via ceiling script, frozen in config before full runs (H12).
6. **Ceiling code vs §11 — FIXED Oct 28:** Appendix `ceiling()` now splits labels per bucket (worst bucket) and uses `0.8*delta/(K*M)`; §11 check line corrected to `(K*M)` terms. Guarded by `test_ceiling_bucket_split` (P01); P08 still freezes M before running.
7. **Pricing, corrected-bound literature status, commissioning cost, rubric weights, prediction-powered inference** — all [VERIFY], see TRACEABILITY.
8. **Billing blocked** (plan §17, Oct 27): if API still blocked at P00 probe, build P01–P02 offline, use no experiment spend until probe passes. [VERIFY]

## Self-audit (yes/no + proof)

1. H1–H4 each ≥20 traj/arm/task? **Yes** — H1:P04, H2/H3:P06, H4:P09 (see TRACEABILITY rows H1–H4).
2. Every [VERIFY] has probe/human check? **Yes** — TRACEABILITY §VERIFY; probes in P00/P07/P12.
3. Every statistical claim has a test? **Yes** — V10 (P01), bootstrap CIs (P04/P06), corrected-bound coverage (P01/P08).
4. Every gate automatable, prints PASS/FAIL? **Yes** — each PHASE Gate section: `make gate PHASE=NN` → `PHASE NN: PASS/FAIL`.
5. Every hackathon rule mapped to phase + V13? **Yes** — TRACEABILITY §Hackathon; V13 checked P00/P11/P12.
6. Total within budget? **Yes (est.)** — phase caps sum to agents ≤$50 + API ≤$71 = **$121** of $150 credits (caps are ceilings, not forecasts; $29 headroom). The P07/P08 judge caps ($12+$15) assume Contributor tier + SAM video mode [VERIFY at P00 probe]; P07/P08 cost pre-flight must pass before launch. Cap enforced by CostMeter (V14).
7. Each phase ≤1 day, pilot before full run? **Yes** — V15 pilot task is first experiment task in P04/P06/P07/P08/P09.
8. Submittable tag each day? **Yes** — calendar EOD tags `eod-MMDD`; final `submission-v1` (P12).
9. Numbers agree? **Yes, after Oct 28 fixes** — items 1 and 6 decided/fixed above; item 2 (demo 2:45) handled in P11. Remaining checks agree (55/113 zero-failure runs §4↔§11; error budget sums to delta for all M, §11).
