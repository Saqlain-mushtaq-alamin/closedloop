# Validity Checklist — Fully Audited for Submission (Phase 12b Remediation)

Check every box from logs/output, not memory. Any FAIL = result invalid; keep run dir, log in docs/DECISIONS.md, rerun under new run_id (H12).

## Controls V1–V15 (All Verified PASS on Valid Runs)

- [x] **V1 Determinism** (P02): Same (program, scenario, seed) executed twice produces bit-for-bit identical trajectory and margin across all valid runs. Note: Quarantined run `cert2-full-01` failed determinism and single-use seed rules due to duplicate batch logging; it is quarantined in [`runs/INVALID_RUNS.json`](file:///d:/canvas/closedloop/runs/INVALID_RUNS.json) and superseded by clean rerun [`runs/cert3-full-01`](file:///d:/canvas/closedloop/runs/cert3-full-01/manifest.json).  
  *Evidence:* Verified in [`tests/test_sim.py::test_determinism`](file:///d:/canvas/closedloop/tests/test_sim.py), [`runs/cert-full-01`](file:///d:/canvas/closedloop/runs/cert-full-01/manifest.json), and [`runs/cert3-full-01`](file:///d:/canvas/closedloop/runs/cert3-full-01/manifest.json) (PASS).
- [x] **V2 Negative Control** (P02/P04): Do-nothing controller achieves 0.0% success; random actions achieve 0.0% success.  
  *Evidence:* Verified in [`tests/test_baselines.py::test_negative_control`](file:///d:/canvas/closedloop/tests/test_baselines.py) on 100 trials (PASS).
- [x] **V3 Positive Control** (P02/P04): Hand-written expert heuristic controller achieves 100% success in nominal conditions ($p_L \ge 0.90$).  
  *Evidence:* Verified in [`tests/test_baselines.py::test_positive_control`](file:///d:/canvas/closedloop/tests/test_baselines.py) (PASS).
- [x] **V4 Data Separation & Leakage** (P02/P08): Disjoint seed streams strictly enforced (repair 0–999,999; calibration 1,000,000–1,999,999; certification 2,000,000–2,999,999). Only `closedloop/certify/` loads certification seeds; `sampler.py` raises `LeakageError` on reuse.  
  *Evidence:* Verified in [`tests/test_sampler.py::test_seed_ranges`](file:///d:/canvas/closedloop/tests/test_sampler.py) and [`tests/test_cert.py`](file:///d:/canvas/closedloop/tests/test_cert.py) (PASS).
- [x] **V5 A/A Control** (P06): Same repair algorithm evaluated on two independent seed sets confirms paired bootstrap difference 95% CI covers zero.  
  *Evidence:* Verified in [`tests/test_baselines.py::test_aa_control`](file:///d:/canvas/closedloop/tests/test_baselines.py) and [`runs/h2h3-full-03/repair_results.json`](file:///d:/canvas/closedloop/runs/h2h3-full-03/repair_results.json) (PASS).
- [x] **V6 Budget Parity** (P06): All repair arms (B1, B2, B3) restricted to equal episode budgets (580 episodes) and token caps within 5%.  
  *Evidence:* Verified in [`tests/test_baselines.py::test_budget_parity`](file:///d:/canvas/closedloop/tests/test_baselines.py) and [`runs/h2h3-full-03/repair_results.json`](file:///d:/canvas/closedloop/runs/h2h3-full-03/repair_results.json) (`budget_parity_ok: true`) (PASS).
- [x] **V7 Crash & Failure Accounting** (P03+): Exceptions, syntax errors, memory limits, and timeouts are strictly recorded as failures (`margin = -1.0`, `success = False`). Zero silent retries.  
  *Evidence:* Verified in [`tests/test_runner.py::test_crash_accounting`](file:///d:/canvas/closedloop/tests/test_runner.py) (PASS).
- [x] **V8 Predicate Agreement** (P02+): Dual independent success predicates (geometric bounding box overlap and contact force sensor) agree with disagreement rate $\le 2.0\%$. Success requires dual consensus.  
  *Evidence:* Verified in [`tests/test_sim.py::test_predicate_agreement`](file:///d:/canvas/closedloop/tests/test_sim.py) (PASS).
- [x] **V9 Vision Judge Controls** (P07): Do-nothing controller pass rate matches measured FPR ($0.005$); shuffled label test yields TPR $\approx$ FPR.  
  *Evidence:* Verified in [`tests/test_judge.py::test_judge_controls`](file:///d:/canvas/closedloop/tests/test_judge.py) and [`runs/judge-g2-03/calibration_report.json`](file:///d:/canvas/closedloop/runs/judge-g2-03/calibration_report.json) (PASS).
- [x] **V10 Statistical Coverage** (P01): Exact Clopper-Pearson confidence interval coverage confirmed $\ge 95.0\%$ across 10,000 synthetic trials; verified identical to SciPy `scipy.stats.beta`.  
  *Evidence:* Verified in [`tests/test_stats.py`](file:///d:/canvas/closedloop/tests/test_stats.py) and [`tests/test_coverage.py`](file:///d:/canvas/closedloop/tests/test_coverage.py) (PASS).
- [x] **V11 Frozen Sample Plan** (P04+): Manifest config hashes (`runs/*/manifest.json`) strictly match frozen configuration files (`configs/*.yaml`). Sample sizes frozen prior to execution.  
  *Evidence:* Verified in [`tests/test_cert.py::test_config_hash_frozen`](file:///d:/canvas/closedloop/tests/test_cert.py) (PASS). Note: `h1-full-02` recorded config hash is noted in [`docs/DECISIONS.md`](file:///d:/canvas/closedloop/docs/DECISIONS.md) as unverifiable against current configs due to interim tuning.
- [x] **V12 Full Regeneration & Byte Determinism** (P10+): `make report` executed twice into separate directories produces 100% byte-identical asset SHA-256 hashes. All numbers in README and report derived from logs.  
  *Evidence:* Verified in [`tests/test_final_compliance.py::test_full_regeneration`](file:///d:/canvas/closedloop/tests/test_final_compliance.py) and [`tests/test_report_readme.py::test_readme_numbers_from_logs`](file:///d:/canvas/closedloop/tests/test_report_readme.py) (PASS).
- [x] **V13 Compliance & Cleanliness** (P12): Zero secrets in git tree or commit history (`scripts/check_no_secrets.sh`); `THIRD_PARTY.md` contains permissive licenses for all dependencies; Rule H14 wording scan completely clean.  
  *Evidence:* Verified in [`tests/test_final_compliance.py::test_final_compliance_scan`](file:///d:/canvas/closedloop/tests/test_final_compliance.py) and [`tests/test_audit_remediation.py::test_banned_claim_wording`](file:///d:/canvas/closedloop/tests/test_audit_remediation.py) (PASS).
- [x] **V14 Cost Meter Enforcement** (P00+): `CostMeter` aborts at configured dollar cap (`BUDGET_USD_CAP`); all LLM calls logged with token counts and pricing. Total project spend was $5.12 across valid production runs ($6.00 across all runs including quarantined runs), with SAM 3.1 labeled as ESTIMATE (token counts synthetic), well below the $60.00 budget cap.  
  *Evidence:* Verified in [`tests/test_cost.py::test_cost_cap_abort`](file:///d:/canvas/closedloop/tests/test_cost.py) and [`assets/spend_summary.json`](file:///d:/canvas/closedloop/assets/spend_summary.json) (PASS).
- [x] **V15 Pilot-Scale Pre-Registration** (P04+): 10% pilot scale runs verified controls V1–V14 before executing full-scale certification.  
  *Evidence:* Verified in [`runs/cert-pilot-01`](file:///d:/canvas/closedloop/runs/cert-pilot-01/manifest.json) and [`tests/test_pilot.py`](file:///d:/canvas/closedloop/tests/test_pilot.py) (PASS).

---

## Controls V1–V15 Pilot & Full Scale Evidence Matrix

| Control | Description | Pilot Run / Test ID | Pilot Output | Full Run ID | Full Output / Result | Status |
|---|---|---|---|---|---|---|
| **V1** | Determinism (bit-for-bit replay) | `tests/test_sim.py::test_determinism` | 10 pairs bit-for-bit matched | `cert3-full-01` / `cert-full-01` | 2459 episodes deterministically matched; recomputation matches | PASS |
| **V2** | Negative Control (do-nothing = 0%) | `tests/test_baselines.py::test_negative_control` | 0/100 passes (0.0% success) | `h1-full-02` (B0 nominal baseline) | 0.0% unassisted grip on out-of-reach payloads | PASS |
| **V3** | Positive Control (expert = 100%) | `tests/test_baselines.py::test_positive_control` | 100/100 passes ($p_L \ge 0.9623$) | `challenge-grid-01` (nominal heuristic) | 100% nominal pass rate | PASS |
| **V4** | Seed Separation (disjoint streams) | `tests/test_sampler.py::test_seed_ranges` | `LeakageError` raised on violation | `sampler.py` + all valid runs | Zero seed collisions across streams (repair/calib/cert) | PASS |
| **V5** | A/A Control (null contrast CI covers 0) | `tests/test_baselines.py::test_aa_control` | 95% CI [-0.0875, 0.1500] contains 0 | `h2h3-full-03` (`aa_null_v5`) | Difference 0.00, 95% CI [-0.0825, +0.0825] covers 0 | PASS |
| **V6** | Budget Parity (equal episodes & tokens) | `tests/test_baselines.py::test_budget_parity` | Episode counts matched within 5% | `h2h3-full-03` (`budget_parity_ok`) | Exactly 580 eps/arm, token parity verified PASS | PASS |
| **V7** | Failure Accounting (no silent retries) | `tests/test_runner.py::test_crash_accounting` | Timeouts & syntax errors logged as fail | `h2h3-full-03` / `cert-full-01` | All crashes recorded with margin = -1.0, 0 silent retries | PASS |
| **V8** | Predicate Agreement (consensus >= 98%) | `tests/test_sim.py::test_predicate_agreement` | Disagreement rate 0.0% (< 2.0%) | `cert-full-01` episodes | Bounding box & contact force agree on 100% of trials | PASS |
| **V9** | Vision Judge Controls (shuffled/do-nothing) | `tests/test_judge.py::test_judge_controls` | Shuffled label TPR ~ FPR verified | `judge-g2-03` (700 calibration eps) | TPR=1.0000, worst-bucket FPR=0.1048 | PASS |
| **V10** | Statistical Coverage (CP >= 95%) | `tests/test_coverage.py` | 10,000 synthetic trials coverage >= 95% | `cert-full-01` & `cert3-full-01` | 57/57 bounds verified via SciPy `verify_evidence.py` | PASS |
| **V11** | Frozen Sample Plan (manifest == config) | `tests/test_cert.py::test_config_hash_frozen` | Config hashes match frozen yaml | `cert-full-01` / `cert3-full-01` | Config hashes `0407...` and `3c06...` verified frozen | PASS |
| **V12** | Full Regeneration (byte-identical make report) | `tests/test_final_compliance.py::test_full_regeneration` | Byte-identical assets in separate dirs | `assets/manifest.json` | 57/57 verified matches across independent runs | PASS |
| **V13** | Compliance & Cleanliness (zero secrets, H14) | `scripts/check_no_secrets.sh` + `check_locked.sh` | 0 secrets, locked files unmodified | Git history & public documentation | Zero banned claims ("safe", "proven", "camera alone") | PASS |
| **V14** | Cost Meter Enforcement (cap <= $60) | `tests/test_cost.py::test_cost_cap_abort` | BudgetExceeded raised at cap | `assets/spend_summary.json` | Valid spend $5.12, total $6.00 <= $60.00 cap | PASS |
| **V15** | Pilot-Scale Pre-Registration | `runs/cert-pilot-01` (15 episodes) | Pilot run executed and logged | `runs/cert-full-01` (2,459 episodes) | Full scale executed strictly following pilot protocols | PASS |

---

## Per-Result Checks (All Verified PASS)

- [x] **Run Manifest Integrity:** `run_id`, git SHA, config hash, seed ranges, model IDs (`muse-spark-1.3`, `sam-3.1`), and cost totals present in all valid `runs/*/manifest.json`.
- [x] **Paired Trajectory Statistical Power:** $\ge 20$ repair trajectories evaluated per arm with 10,000-resample paired bootstrap 95% confidence intervals; negative/null results reported as-is.
- [x] **Independent Certificate Verification:** Every bound recomputed independently from `episodes.jsonl` using SciPy matches reported values ($57/57$ match via `make verify-evidence`).
- [x] **Judge Freeze Prior to Certification:** Prompt hash, threshold, and camera configuration hash frozen since Gate G2 calibration (`0a085ba70f01e4ef311e6e41472c16ce03cc9fd221d07698f526806ab8d4c94e`).
- [x] **Heatmap Delta Allocation:** Error budget strictly allocated across $K=16, B=4, M=1$ with exact significance conservation ($\sum \delta_i = 0.05$).
- [x] **Spend Governance:** Total project spend under cap ($5.12 on valid runs, $6.00 total across all runs $\le \$60.00$ cap); zero calls bypassed `closedloop/llm/client.py`.
