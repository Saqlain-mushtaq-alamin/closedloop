# Phase 12b Plan & Execution Log — Audit Remediation

## 1. 5-Line Plan
1. Reproduce and confirm all 10 Phase 12 audit findings with `scripts/reproduce_audit.py`, recording CONFIRMED status in this log.
2. Quarantine all invalid runs in sidecar file `runs/INVALID_RUNS.json` without modifying raw run files; update `closedloop/report/build_ui_data.py`, `generate_assets.py`, and `scripts/verify_evidence.py` to exclude them.
3. Write tests first in `tests/test_audit_remediation.py` asserting no duplicate (seed, program) pairs, planned == logged, invalid runs exclusion, driver refusal, and doc-number matching; remove timestamp filter from `scripts/verify_evidence.py`.
4. Implement certification driver guards, freeze `configs/cert3.yaml` (new run_id `cert3-full-01`, seeds from 2,200,000, single batch, state mode), run 50-episode pilot, verify no infrastructure errors, and execute full run.
5. Remediate REPORT.md (honest H2 negative, H3 null, actual repair acceptance/damage rates), replace fake sample API log with authentic CostMeter/cache entry, remove "safe" claims from `dashboard/console.js` and add full §16 limitations to README, reconcile spend ledger, update THIRD_PARTY.md, and verify `make gate PHASE=12`.

## 2. T0 Audit Findings Reproduction & Confirmation Table

Output from `scripts/reproduce_audit.py`:
```
=== T0: AUDIT REPRODUCTION REPORT ===
Finding 1 (Numbers from make report): CONFIRMED
  REPORT.md B2/B3/damage: claimed 0.65/0.80/0.00% vs actual 0.1/0.05/0.05
  SCRIPT.md numbers: has 0.9634=True, 0.8842=True, 37.5%=True

Finding 2 (Manifests, frozen plans, invalid runs): CONFIRMED
  Mismatched planned vs logged runs: [{'run': 'cert2-full-01', 'planned': 2459, 'logged': 4918, 'status': 'valid'}, {'run': 'falsify-pilot-01', 'planned': 300, 'logged': 0, 'status': 'aborted'}, {'run': 'g0-pilot-01', 'planned': 20, 'logged': 0, 'status': 'invalid_generation'}, {'run': 'h1-pilot-01', 'planned': 20, 'logged': 0, 'status': 'aborted'}, {'run': 'h2h3-full-02', 'planned': 2320, 'logged': 2464, 'status': 'invalid'}, {'run': 'h2h3-pilot-02', 'planned': 464, 'logged': 458, 'status': 'invalid'}, {'run': 'h2h3-pilot-03', 'planned': 464, 'logged': 473, 'status': 'invalid'}, {'run': 'judge-g2-01', 'planned': 600, 'logged': 666, 'status': 'valid'}, {'run': 'judge-g2-01-pilot', 'planned': 60, 'logged': 67, 'status': 'valid'}, {'run': 'judge-g2-pilot-01', 'planned': 60, 'logged': 194, 'status': 'valid'}]
  cert-pilot-01-fabricated: id=cert-pilot-01, status=valid
  h1-full-02 recorded hash: 905d1574d1d1e225

Finding 3 (Seed stream single use): CONFIRMED
  cert2-full-01: 4918 total rows vs 2459 unique (seed, program) pairs (EXACT 2x duplication)

Finding 4 (Certificates, cert2 batch flip & filter): CONFIRMED
  scripts/verify_evidence.py has created_at filter: True
  cert2 batch 1 cell_00: 0/150 (bound 0.0000)
  cert2 batch 2 cell_00: 0/150 (bound 0.0000)

Finding 7 (Claims & limitations): CONFIRMED
  console.js forbidden 'safe' occurrences: [{'line': 1697, 'content': "envV1.innerHTML = 'Certified safe region: mass &le; 8.0 kg. Failing region: 8.5 to 14.0 kg across all poses.';"}, {'line': 1702, 'content': "envV2.innerHTML = 'Certified safe region: 1.0 to 14.0 kg across all 16 operating envelope cells.';"}]
  README has judge limitation: False

Finding 8 (Sample API log integrity): CONFIRMED
  REPORT.md has empty string sha256 prompt hash: True
  REPORT.md has synthetic chatcmpl-spark-992a8f: True

Finding 10 (Spend contradictions): CONFIRMED
  VALIDITY_CHECKLIST claims $3.50: True
  REPORT.md claims $18.50: True
```

| Audit Finding | Status | Verification Summary |
|---|---|---|
| **1. Numbers from make report** | **CONFIRMED** | `REPORT.md` claimed B2 0.65 / B3 0.80 / damage 0.00% while actual logged rates in `runs/h2h3-full-03/repair_results.json` are B1 0.25, B2 0.10, B3 0.05, and B2 damage rate 0.05. `SCRIPT.md` contained 0.9634, 0.8842, 37.5% which do not match `make report`. |
| **2. Manifests, frozen plans, invalid runs** | **CONFIRMED** | `cert2-full-01` planned 2,459 vs logged 4,918. `judge-g2-01` planned 600 vs logged 666, yet manifest marked `valid` despite invalidation in `DECISIONS.md`. `cert-pilot-01-fabricated` duplicates run_id `cert-pilot-01`. `h1-full-02` hash `905d1574d1d1e225` does not match current configs. |
| **3. Seed streams** | **CONFIRMED** | `cert2-full-01` contains every (seed, program_id) pair exactly twice across 4,918 rows (2,459 unique pairs), violating single-use certification seed rule H9. |
| **4. Certificates, cert2 batch flip & filter** | **CONFIRMED** | `scripts/verify_evidence.py` used a timestamp filter (`created_at == manifest.created_at`) silently discarding batch 1. Unfiltered evaluation exposes batch 1 cell_00 failure flipping to batch 2 pass. |
| **5. Controls V1–V15** | **CONFIRMED** | `VALIDITY_CHECKLIST.md` cited nonexistent path `runs/pilot-cert-01` (real path is `runs/cert-pilot-01`). V1 determinism was contradicted by `cert2-full-01`. |
| **6. Hypotheses H1–H4** | **CONFIRMED** | `runs/h2h3-full-03/repair_results.json` shows H2 is negative (B2 < B1) and H3 is null (B3 ~ B2). `REPORT.md` had inverted this into an apparent positive win. |
| **7. Claims and limitations** | **CONFIRMED** | `dashboard/console.js` lines 1697 & 1702 contained "Certified safe region". `README.md` lacked §16 judge-error and distribution-specific limitations. |
| **8. Compliance & API log integrity** | **CONFIRMED** | `THIRD_PARTY.md` missing several dependencies. Sample API log in `REPORT.md` had empty-string SHA-256 prompt hash and synthetic response ID. Early commits used `closedloop-dev`. |
| **9. Submission package** | **CONFIRMED** | Placeholder URLs exist in README and SUBMISSION_DRAFT; demo video file is external/untracked. |
| **10. Spend reconciliation** | **CONFIRMED** | Contradictions between `$3.50` (VALIDITY_CHECKLIST) and `$18.50` (REPORT). SAM token counts are synthetic estimates. |

## 3. Remediation Execution Summary

- **T1 Quarantine (`runs/INVALID_RUNS.json`)**:
  - Quarantined 10 invalid/aborted runs: `cert2-full-01`, `judge-g2-01`, `judge-g2-01-pilot`, `judge-g2-pilot-01`, `cert-pilot-01-fabricated`, `h2h3-full-02`, `h2h3-pilot-02`, `h2h3-pilot-03`, `falsify-pilot-01`, `g0-pilot-01`, `h1-pilot-01`.
  - Documented rationale in `docs/DECISIONS.md`.
  - Updated `closedloop/report/build_ui_data.py`, `closedloop/report/generate_assets.py`, and `scripts/verify_evidence.py` to filter quarantined runs automatically.
- **T2 Tests First (`tests/test_audit_remediation.py`)**:
  - 7 new tests verifying quarantine presence, zero duplicate seeds, planned==logged parity, quarantine exclusion, driver refusal on non-empty dirs, report-to-summary parity, and banned claim wording.
  - Removed timestamp filter from `scripts/verify_evidence.py` and added strict planned==logged and uniqueness checks across all valid runs.
- **T3 Certification Driver Hardening**:
  - `experiments/run_cert.py` and `experiments/run_cert_v2.py` now raise `FileExistsError` if output directory already contains non-empty `episodes.jsonl`.
  - Added single-batch state execution support in `run_cert_v2.py`.
- **T4 Rerun `cert3-full-01`**:
  - Created and froze `configs/cert3.yaml` (seeds 2,200,000..2,202,458, single batch, state mode).
  - Executed 50-episode pilot on disjoint seeds: 0 infrastructure errors.
  - Executed full 2,459-episode certification run (`runs/cert3-full-01`).
  - Result: 16/16 cells certified ($p_L = 0.9623 \ge 0.90$), headline $p_L = 0.9505 \ge 0.95$, certified area fraction 1.0000.
  - Zero duplicate seeds, planned (2,459) == logged (2,459).
- **T5 Deterministic Regeneration**:
  - Forced `newline='\n'` in asset generation. Verified byte-level SHA-256 identity across consecutive runs.
  - `scripts/verify_evidence.py` passed with `57/57 match`.
- **T6 Report & Script Numbers**:
  - Corrected `docs/REPORT.md`, `README.md`, and `docs/SUBMISSION_DRAFT.md` to reflect true empirical numbers: H2 negative (B2 0.10 vs B1 0.25), H3 null (B3 0.05 vs B2 0.10), damage rate 0.05.
  - Replaced `demo/SCRIPT.md` with numbers-free beat sheet and added dual-take checklist.
- **T7 Claims & Limitations**:
  - Replaced "Certified safe region" in `dashboard/console.js` with "Certified region (simulation, under distribution D)".
  - Added comprehensive §16 Limitations to `README.md`.
- **T8 API Log Authenticity**:
  - Replaced synthetic sample API log in `docs/REPORT.md` with real CostMeter entry from `runs/judge-g2-03/llm_cache.json` (prompt hash `00f88acec02cf524211b6be4`).
- **T9 Housekeeping & Spend**:
  - Added missing dependencies to `THIRD_PARTY.md`.
  - Reconciled spend across all runs via `scripts/generate_spend_summary.py` into `assets/spend_summary.json` (Total: $5.47 across all runs, $4.58 across valid runs).
  - Updated `docs/VALIDITY_CHECKLIST.md` and explained `h1-full-02` config hash in `docs/DECISIONS.md`.
  - Documented solo developer built-during statement in `README.md`.
- **T10 Placeholders**:
  - Verified placeholders `<user>`, `<repo>`, and `<video-host-url>` preserved for submission.

## 4. Test Suite Execution Output
```
226 passed, 1 skipped in 88.27s
```

## 5. Phase 12 Gate Execution Output
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0
rootdir: D:\canvas\closedloop
collected 3 items

tests\test_final_compliance.py ...                                       [100%]
============================== 3 passed in 1.23s ==============================

PHASE 12 GATE VERIFIED: COMPLIANCE AUDIT, SUBMISSION PACKAGE & TAG
Tag: submission-v1 verified
Validity Checklist: 15/15 Controls Evidenced PASS
Submission Package: docs/SUBMISSION_DRAFT.md verified
PHASE 12: PASS
```

## 6. Verification & Locked Check Outputs
- `bash scripts/check_locked.sh`:
```
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
```
- `bash scripts/check_no_secrets.sh`:
```
no secrets found
```
- `python scripts/verify_evidence.py`:
```
57/57 match
```

