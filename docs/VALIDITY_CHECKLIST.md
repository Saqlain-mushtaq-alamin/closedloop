# Validity Checklist — Fully Audited for Submission (Phase 12)

Check every box from logs/output, not memory. Any FAIL = result invalid; keep run dir, log in docs/DECISIONS.md, rerun under new run_id (H12).

## Controls V1–V15 (All Verified PASS)

- [x] **V1 Determinism** (P02): Same (program, scenario, seed) executed twice produces bit-for-bit identical trajectory and margin.  
  *Evidence:* Verified in `tests/test_sim.py::test_determinism` and `tests/test_dashboard.py::test_regeneration_determinism` (PASS).
- [x] **V2 Negative Control** (P02/P04): Do-nothing controller achieves 0.0% success; random actions achieve 0.0% success.  
  *Evidence:* Verified in `tests/test_baselines.py::test_negative_control` on 100 trials (PASS).
- [x] **V3 Positive Control** (P02/P04): Hand-written expert heuristic controller achieves 100% success in nominal conditions ($p_L \ge 0.90$).  
  *Evidence:* Verified in `tests/test_baselines.py::test_positive_control` (PASS).
- [x] **V4 Data Separation & Leakage** (P02/P08): Disjoint seed streams strictly enforced (repair 0–999,999; calibration 1,000,000–1,999,999; certification 2,000,000–2,999,999). Only `closedloop/certify/` loads certification seeds; `sampler.py` raises `LeakageError` on reuse.  
  *Evidence:* Verified in `tests/test_sampler.py::test_seed_ranges` and `tests/test_cert.py` (PASS).
- [x] **V5 A/A Control** (P06): Same repair algorithm evaluated on two independent seed sets confirms paired bootstrap difference 95% CI covers zero.  
  *Evidence:* Verified in `tests/test_baselines.py::test_aa_control` and `runs/h2h3-full-03/repair_results.json` (PASS).
- [x] **V6 Budget Parity** (P06): All repair arms (B1, B2, B3) restricted to equal episode budgets (580 episodes) and token caps within 5%.  
  *Evidence:* Verified in `tests/test_baselines.py::test_budget_parity` and `runs/h2h3-full-03/repair_results.json` (`budget_parity_ok: true`) (PASS).
- [x] **V7 Crash & Failure Accounting** (P03+): Exceptions, syntax errors, memory limits, and timeouts are strictly recorded as failures (`margin = -1.0`, `success = False`). Zero silent retries.  
  *Evidence:* Verified in `tests/test_runner.py::test_crash_accounting` (PASS).
- [x] **V8 Predicate Agreement** (P02+): Dual independent success predicates (geometric bounding box overlap and contact force sensor) agree with disagreement rate $\le 2.0\%$. Success requires dual consensus.  
  *Evidence:* Verified in `tests/test_sim.py::test_predicate_agreement` (PASS).
- [x] **V9 Vision Judge Controls** (P07): Do-nothing controller pass rate matches measured FPR ($0.005$); shuffled label test yields TPR $\approx$ FPR.  
  *Evidence:* Verified in `tests/test_judge.py::test_judge_controls` and `runs/judge-g2-03/calibration_report.json` (PASS).
- [x] **V10 Statistical Coverage** (P01): Exact Clopper-Pearson confidence interval coverage confirmed $\ge 95.0\%$ across 10,000 synthetic trials; verified identical to SciPy `scipy.stats.beta`.  
  *Evidence:* Verified in `tests/test_stats.py` and `tests/test_coverage.py` (PASS).
- [x] **V11 Frozen Sample Plan** (P04+): Manifest config hashes (`runs/*/manifest.json`) strictly match frozen configuration files (`configs/*.yaml`). Sample sizes frozen prior to execution.  
  *Evidence:* Verified in `tests/test_cert.py::test_config_hash_frozen` (PASS).
- [x] **V12 Full Regeneration & Byte Determinism** (P10+): `make report` executed twice into separate directories produces 100% byte-identical asset SHA-256 hashes. All numbers in README and report derived from logs.  
  *Evidence:* Verified in `tests/test_final_compliance.py::test_full_regeneration` and `tests/test_report_readme.py::test_readme_numbers_from_logs` (PASS).
- [x] **V13 Compliance & Cleanliness** (P12): Zero secrets in git tree or commit history (`scripts/check_no_secrets.sh`); `THIRD_PARTY.md` contains permissive licenses for all dependencies; Rule H14 wording scan completely clean.  
  *Evidence:* Verified in `tests/test_final_compliance.py::test_final_compliance_scan` (PASS).
- [x] **V14 Cost Meter Enforcement** (P00+): `CostMeter` aborts at configured dollar cap (`BUDGET_USD_CAP`); all LLM calls logged with token counts and pricing. Total API spend is under $3.50.  
  *Evidence:* Verified in `tests/test_cost.py::test_cost_cap_abort` (PASS).
- [x] **V15 Pilot-Scale Pre-Registration** (P04+): 10% pilot scale runs verified controls V1–V14 before executing full-scale certification.  
  *Evidence:* Verified in `runs/pilot-cert-01` and `tests/test_pilot.py` (PASS).

---

## Per-Result Checks (All Verified PASS)

- [x] **Run Manifest Integrity:** `run_id`, git SHA, config hash, seed ranges, model IDs (`muse-spark-1.3`, `sam-3.1`), and cost totals present in all `runs/*/manifest.json`.
- [x] **Paired Trajectory Statistical Power:** $\ge 20$ repair trajectories evaluated per arm with 10,000-resample paired bootstrap 95% confidence intervals; null results reported as-is.
- [x] **Independent Certificate Verification:** Every bound recomputed independently from `episodes.jsonl` using SciPy matches reported values ($57/57$ match via `make verify-evidence`).
- [x] **Judge Freeze Prior to Certification:** Prompt hash, threshold, and camera configuration hash frozen since Gate G2 calibration (`0a085ba70f01e4ef311e6e41472c16ce03cc9fd221d07698f526806ab8d4c94e`).
- [x] **Heatmap Delta Allocation:** Error budget strictly allocated across $K=16, B=4, M=1$ with exact significance conservation ($\sum \delta_i = 0.05$).
- [x] **Spend Governance:** Total project spend under cap ($3.50 API + $0.00 agent spend $\le \$60.00$ cap); zero calls bypassed `closedloop/llm/client.py`.
