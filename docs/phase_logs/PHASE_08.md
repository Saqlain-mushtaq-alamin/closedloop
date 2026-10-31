# Phase 08 Plan — Certification

1. Write tests first in `tests/test_cert.py` (`test_cert_seed_once`, `test_error_budget_sum`, `test_cert_recompute`, `test_price_plot_data`, `test_cost_preflight`) and verify they fail for the right reasons.
2. Freeze `configs/cert.yaml` with config hash before any cert episode (M=1, K=16, B=4, delta=0.05, n=150 runs/cell, headline n=59, seeds strictly in certification stream 2,000,000–2,999,999 with each seed used once).
3. Execute pilot run (1 cell, ~10%), verify independent SciPy recomputation matches reported bound within 1e-9, and perform camera cost pre-flight metering against remaining API budget.
4. Run full certification for accepted program `bec73dec45a88431` (from `runs/cert-mint-03`): headline certificate (p >= 0.95), 4x4 state heatmap (cells p >= 0.90), 4x4 camera heatmap (cells p >= 0.85, Gate G2 passed), and price-of-footage plot from logs only (Rule H11).
5. Run `make gate PHASE=08`, paste full command output into this log, verify all locked hashes and controls, and stop.

## Phase 08 Execution Log

### 1. What Changed
- Created `configs/cert.yaml` with frozen parameters ($M=1, K=16, B=4, \delta=0.05, n=150$ per cell, $n=59$ headline, seed base $2,000,000$, config hash `04073afb3e1d4af2`).
- Implemented `closedloop/certify/certify.py` supporting:
  - Exact error budget math: family-wise state cell $\alpha = \delta / K = 0.05 / 16 = 0.003125$, headline $\delta = 0.05$; camera cell split $\delta_{\text{cell}} = 0.0025, \delta_A = 0.005, \delta_B = 0.00125$. Joint simultaneous split available summing strictly to $\le \delta$.
  - Clopper-Pearson exact lower bound computation via `closedloop/certify/stats.py`.
  - Camera-corrected lower bound accounting for calibrated vision judge TPR ($1.00$) and FPR ($0.02$) from Gate G2.
  - Verification and independent recomputation via SciPy exact binomial test matching within $10^{-9}$.
  - Preflight cost check verifying projected full-run cost from pilot measurements.
  - Price-of-footage calculation parsing raw append-only logs (`episodes.jsonl`), sensitive to judge misclassifications and failing closed on missing data.
- Created `experiments/run_cert.py` for running pilot (`cert-pilot-01`) and full certification (`cert-full-01`) pipelines with append-only logging, manifests, and run artifacts.
- Added Phase 08 verification target and gate in `Makefile`.

### 2. Files Added / Modified
- `configs/cert.yaml` (new)
- `closedloop/certify/certify.py` (new)
- `tests/test_cert.py` (new)
- `experiments/run_cert.py` (new)
- `Makefile` (modified to include `verify_phase_08_gate` and `PHASE=08`)
- `docs/phase_logs/PHASE_08.md` (updated)

### 3. Tests Added
- `tests/test_cert.py`:
  - `test_cert_seed_once`: verifies single-use rule H9 on certification seeds and persistent ledger tracking across process restarts.
  - `test_error_budget_sum`: verifies Bonferroni error budget allocation for both family-wise and joint simultaneous modes.
  - `test_cert_recompute`: verifies recomputation matches exact SciPy binomial test within $10^{-9}$.
  - `test_price_plot_data`: verifies price-of-footage data generation from log records and sensitivity to judge misclassifications.
  - `test_cost_preflight`: verifies preflight budget check passes within remaining budget.

### 4. Gate Output
```
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
........................................................................ [ 61%]
.............................................s                           [100%]
117 passed, 1 skipped in 16.54s
.....                                                                    [100%]
5 passed in 0.72s
pybullet build time: Oct 28 2026 19:50:31
PHASE 08 GATE VERIFIED: run_id=cert-full-01, episodes=2459
Headline State Bound: 0.4778 (certified: False)
State Area: 0.5000, Camera Area: 0.5000
PHASE 08: PASS
```

### 5. Numbers Observed vs Expected Range
- **Cell Count**: 16 regional cells ($4 \times 4$ grid over mass $[1.0, 11.5]$ kg and friction $[0.1, 1.0]$).
- **Episodes Run**: 2,459 total (2,400 regional cell episodes + 59 headline episodes) executed in parallel sandboxed subprocesses with memory and timeout enforcement. All logged append-only to `runs/cert-full-01/episodes.jsonl`.
- **Headline Pass Rate**: $k = 35 / 59 = 0.5932$.
- **Headline State Bound**: $p_L = 0.4778$ (at $\alpha = 0.05$). Uncertified against headline target $p \ge 0.95$.
- **Regional Certified Cells (State Ground Truth, $p_L \ge 0.90$)**:
  - Mass cells $00$–$07$ (mass $1.00$ to $6.25$ kg): 8 cells CERTIFIED ($150/150$ passes each, $p_L = 0.9623 \ge 0.90$).
  - Mass cells $08$–$11$ (mass $6.25$ to $8.88$ kg): Uncertified ($127$ to $134/150$ passes, $p_L = 0.7594$ to $0.8124 < 0.90$).
  - Mass cells $12$–$15$ (mass $8.88$ to $11.50$ kg): Uncertified ($0/150$ passes, $p_L = 0.0000$ due to gripper force limit).
  - State Area Fraction: $8 / 16 = 0.5000$.
- **Regional Certified Cells (Camera Judge, $p_L^{\text{cam}} \ge 0.85$)**:
  - Mass cells $00$–$07$: 8 cells CERTIFIED ($p_L^{\text{cam}} = 0.9563 \ge 0.85$).
  - Mass cells $08$–$15$: 8 cells uncertified.
  - Camera Area Fraction: $8 / 16 = 0.5000$.
- **Price of Footage (Area Loss)**:
  - $\Delta \text{Area} = 0.5000 - 0.5000 = 0.0000$.
- **Independent SciPy Recomputation**: Matched reported Clopper-Pearson bounds with difference $\le 10^{-12}$.
- **API Cost**: $0.0140 in pilot vision calls; $2.5940 in full certification (709 unique rendered camera frames evaluated via Meta Model API SAM 3.1 and Muse Spark 1.3). Total phase spend: $2.6080 against $15.00 phase cap.

### 6. Open Questions
- None. The result is fully reproducible, deterministic, and all raw records are frozen.

### 7. Surprises & Observations
- The regional certification heatmap clearly demonstrates the central thesis of ClosedLoop: while the global headline certificate honestly fails ($p_L = 0.4778 < 0.95$) due to physical limits of the simulated gripper on heavy objects ($m > 6.25$ kg), the regional heatmap certifies with rigorous statistical confidence ($p_L \ge 0.9623 \ge 0.90$) that the policy succeeds on 50% of the operational space (all friction regimes for objects under 6.25 kg).
