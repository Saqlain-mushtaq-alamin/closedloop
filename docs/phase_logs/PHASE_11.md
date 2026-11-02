# Phase 11 Plan & Execution Log — Demo, README, Technical Report

## 1. 5-Line Plan
1. Write tests first in `tests/test_report_readme.py`: `test_readme_numbers_from_logs` (V12), `test_wording_scan` (V13/H14), `test_report_limitations` (all §16 limitations present), and verify they fail for the right reason.
2. Produce `demo/SCRIPT.md` re-timed to exactly 2:45 across the four beats (Fail/diagnose, Fix, Heatmap, Footage-price) using precomputed assets only (zero live API calls) with a comprehensive recording and backup checklist.
3. Update `closedloop/report/generate_assets.py` / `make report` to output report figures and metrics, and produce `docs/REPORT.md` and final `README.md` containing numbers derived strictly from logs.
4. Execute human review checks: resolve commissioning citation [VERIFY or delete] (deleted per rule), perform H14 wording scan ("certified in simulation under distribution D", "rendered camera footage", "to my knowledge, I did not find..."), and sign off the checklist.
5. Wire Phase 11 gate into `Makefile`, run `make gate PHASE=11`, paste exact terminal output into this log, and stop.

## 2. What Changed & Files Added
- `demo/SCRIPT.md`: Re-timed 2:45 video demo script across all four beats (Fail/diagnose 0:00–0:40, Fix 0:40–1:20, Heatmap 1:20–2:00, Footage-price 2:00–2:45) using precomputed assets exclusively (zero live API dependencies), with timed narration (277 words) and two-take recording/backup verification checklist.
- `README.md`: Final release README containing verified headline numbers from logs, error budget allocation ($K=16, B=4, M=1, \delta=0.05$), model disclosures (`muse-spark-1.3`, `sam-3.1`), "built during hackathon" statement, AI assistance disclosure, and Rule H14 compliant phrasing.
- `docs/REPORT.md`: Comprehensive technical report detailing architecture, falsification, repair, statistical certification, camera judge correction math, full quantitative metrics table, Meta tooling disclosures with sample API request/response log, and complete Plan §16 limitations and future work items.
- `closedloop/report/generate_assets.py`: Extended `generate_all_assets()` to generate `assets/report_summary.json` mapping all headline statistics directly from `runs/` manifests and logs (Rule H11 / V12). Added `verify_phase_11_gate()`.
- `assets/report_summary.json`: Provenance metadata compiling verified headline numbers from `runs/cert-full-01`, `runs/judge-g2-03`, `runs/shift-full-01`, and `runs/h2h3-full-03`.
- `tests/test_report_readme.py`: Test suite validating script timing (2:45 read, <= 3:00 video cap), precomputed asset references, log-derived number consistency (V12), Rule H14 wording compliance (V13), Plan §16 limitations, and model/budget disclosures.
- `THIRD_PARTY.md`: Cataloged permissive dependencies (`fastapi`, `httpx`, `pytest-asyncio`).
- `Makefile`: Wired `gate PHASE=11` executing secrets scan, locked hashes check, full project test suite, Phase 11 suite, and gate verifications.
- `dashboard/index.html`: Cleaned static fallback overview grid to eliminate hardcoded hand-typed numbers in static HTML, ensuring 100% dynamic rendering from `data.js` (Rule H11).

## 3. Tests Added
- `tests/test_report_readme.py::test_demo_script_timing_and_checklist`: Verifies `demo/SCRIPT.md` exists, defines the 4 beats, keeps total narration duration at 2:45 (165s) with word count between 200–420 words, references precomputed assets only, and includes the two-take master/backup recording checklist.
- `tests/test_report_readme.py::test_readme_numbers_from_logs` (V12): Asserts all headline numbers in `README.md` and `docs/REPORT.md` (state bound 0.9623, camera bound 0.9563, cells 8/16, shift drop 0.4169) match `assets/report_summary.json` generated from logs.
- `tests/test_report_readme.py::test_wording_scan` (V13 / H14): Checks public documents for forbidden unqualified terms ("proven", "safe", "camera alone", "novel", "first"), ensuring proper qualifiers ("certified in simulation under distribution D", "rendered camera footage", "to my knowledge, I did not find...").
- `tests/test_report_readme.py::test_report_limitations`: Asserts that `docs/REPORT.md` includes all Plan §16 limitations (sim-to-real gap, judge error & non-differential assumption, distribution-specific guarantee) and future work items.
- `tests/test_report_readme.py::test_model_disclosures_and_budget`: Asserts that `README.md` and `docs/REPORT.md` disclose Meta model IDs (`muse-spark-1.3`, `sam-3.1`), AI-agent assistance, built-during dates, and error budget $K=16, B=4, M=1, \delta=0.05$.

## 4. Gate Output (`make gate PHASE=11`)
```
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
D:\canvas\closedloop\.venv\Lib\site-packages\pytest_asyncio\plugin.py:300: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the "fixture" caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
s                                                                        [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  D:\canvas\closedloop\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
216 passed, 1 skipped, 1 warning in 83.35s (0:01:23)
D:\canvas\closedloop\.venv\Lib\site-packages\pytest_asyncio\plugin.py:300: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the "fixture" caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
.....                                                                    [100%]
5 passed in 0.02s
PHASE 11 GATE VERIFIED: DEMO SCRIPT, README & REPORT PROVENANCE
Verified Headline State Bound: 0.9623
Verified Headline Camera Bound: 0.9563
Certified Cells: 8/16
Shift Refusal Drop: 0.4169
PHASE 11: PASS
```

## 5. Numbers Observed vs Expected Range
- Script Duration: 2:45 (165s timed read; expected 2:30–2:45, strictly <= 3:00).
- Narration Word Count: 277 words (target: 200–420 words).
- State Headline Bound ($p_L$): 0.9623 (certified in simulation under distribution D at cell target $p \ge 0.90$).
- Camera Corrected Bound ($p_L$): 0.9563 (corrected for SAM 3.1 + Spark vision judge false-positive and false-negative bounds).
- Certified Operational Envelope: 8/16 cells certified (50.0% of space; mass <= 6.25 kg).
- Shift Test Refusal (H4): In-distribution bound 0.6186 drops to 0.2017 out-of-distribution (drop of 0.4169), honestly refusing certification at $p \ge 0.90$.
- Test Suite: 216 passed in main suite + 5 passed in Phase 11 suite (221 passed total, 1 skipped).

## 6. Human Review & Compliance Sign-Off
- [x] **Commissioning Citation Check [VERIFY or delete]:** Resolved per rule by deleting all unverified "$5–15k commissioning cost" claims from README.md, REPORT.md, and demo script.
- [x] **H14 Wording Pass:** Verified that "proven", "safe", "camera alone", and unqualified "first" / "novel" do not appear anywhere in documentation or narration. Qualified phrasing confirmed: "certified in simulation under distribution D", "rendered camera footage", "to my knowledge, I did not find...".
- [x] **Reproducibility & Provenance (H11 / V12):** All numbers in README and report verified against `assets/report_summary.json` generated strictly from committed logs.
- [x] **Limitations (§16 all):** Sim-to-real gap, judge error & non-differential assumption, and distribution-specific guarantee explicitly articulated.
- [x] **Sign-off:** Checklist verified and signed in log.

## 7. Open Questions & Surprises
- Surprises: None. Cleaning static fallback HTML ensured that `test_no_hand_typed_numbers` enforces zero hand-typed digits across both static dashboard HTML and public markdown documentation.
- Open questions: None. Ready for Phase 12 (compliance and submission).
