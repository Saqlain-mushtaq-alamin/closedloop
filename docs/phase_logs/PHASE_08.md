# Phase 08 Plan — Certification

1. Write tests first in `tests/test_cert.py` (`test_cert_seed_once`, `test_error_budget_sum`, `test_cert_recompute`, `test_price_plot_data`, `test_cost_preflight`) and verify they fail for the right reasons.
2. Freeze `configs/cert.yaml` with config hash before any cert episode (M=1, K=16, B=4, delta=0.05, n=150 runs/cell, headline n=59, seeds strictly in certification stream 2,000,000–2,999,999 with each seed used once).
3. Execute pilot run (1 cell, ~10%), verify independent SciPy recomputation matches reported bound within 1e-9, and perform camera cost pre-flight metering against remaining API budget.
4. Run full certification for accepted program `bec73dec45a88431` (from `runs/cert-mint-03`): headline certificate (p >= 0.95), 4x4 state heatmap (cells p >= 0.90), 4x4 camera heatmap (cells p >= 0.85, Gate G2 passed), and price-of-footage plot from logs only (Rule H11).
5. Run `make gate PHASE=08`, paste full command output into this log, verify all locked hashes and controls, and stop.
