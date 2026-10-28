# Validity Checklist — run before trusting any result

Check every box from logs/output, not memory. Any FAIL = result invalid; keep run dir, log in docs/DECISIONS.md, rerun under new run_id (H12).

## Controls V1–V15

- [ ] **V1 Determinism** (P02): same (program, scenario, seed) twice → identical result hash.
- [ ] **V2 Negative** (P02/P04): do-nothing = 0%; random actions ≈0%.
- [ ] **V3 Positive** (P02/P04): hand-written good program in expected band (state band in P04).
- [ ] **V4 Leakage** (P02/P08): seed streams disjoint; certification seeds only loaded by certify/; each cert seed once/program.
- [ ] **V5 A/A** (P06): same arm twice → paired diff CI contains 0 (one pre-declared fresh-seed rerun allowed; two exclude-0 = biased).
- [ ] **V6 Budget parity** (P06): episodes + tokens within 5% across arms.
- [ ] **V7 Crash accounting** (P03+): exceptions/timeouts/invalid counted as failures; count printed.
- [ ] **V8 Predicate agreement** (P02+): disagreement ≤2%; success = both agree, disagreement = failure; rate logged.
- [ ] **V9 Judge controls** (P07): do-nothing pass rate ≈ FPR; shuffled labels TPR ≈ FPR.
- [ ] **V10 Statistics** (P01): synthetic coverage ≥95%; matches SciPy exact CI.
- [ ] **V11 Frozen plan** (P04+): manifest config hash = frozen hash; n unchanged; no outcome-based stopping.
- [ ] **V12 Regeneration** (P10+): `make report` twice byte-identical; every README number from logs.
- [ ] **V13 Compliance** (P12): no secrets (tree+history); THIRD_PARTY complete; no "first/novel/proven/safe/camera alone" (unqualified).
- [ ] **V14 Cost meter** (P00+): aborts at tiny cap in test; live total under phase cap.
- [ ] **V15 Pilot first** (P04+): ~10% pilot passed V1–V14 before full run.

## Per-result checks

- [ ] Run manifest: run_id, git SHA, config hash, seed ranges, model IDs, token/cost totals present.
- [ ] ≥20 trajectories/arm/task (H1–H3); paired bootstrap 95% CI (10k) reported, nulls shown as-is.
- [ ] Certificate recomputed independently from episodes.jsonl matches reported bound.
- [ ] Judge frozen before certification (prompt/threshold/camera hash unchanged since calibration).
- [ ] Heatmap: per-cell delta split applied (K=16, B=4, M as frozen); camera targets only if G2 passed.
- [ ] Spend: CostMeter total + agent spend ≤ budget; no call bypassed client.py/CostMeter.
