# Phase 00 plan (5 lines)
1. Tests first: `tests/test_compliance.py` (V13/V14/H4 checks) failing on empty tree.
2. Repo files: README (built-during note), LICENSE (MIT), THIRD_PARTY.md, configs/base.yaml.
3. Makefile (setup/test/lint/controls/gate/report) + `check_no_secrets.sh` + `check_locked.sh` stub.
4. `closedloop/llm/cost.py` (CostMeter, cap abort) + `client.py` (env keys, max tokens, 3 retries).
5. Probe API (record tier/SAM mode in API_NOTES.md; offline if blocked), then `make gate PHASE=00`.

## Gate output (2026-10-28; `make` not installed — ran gate steps directly)
no secrets found
locked check: LOCKED_HASHES.txt not present yet (pre-Phase-01 stub); PASS
4 passed in 0.34s
PHASE 00: PASS
Numbers: 4/4 tests; probe spend $0.00; agent $: metered at $0 (no API calls).
Surprises: no pytest/pip/ensurepip (bootstrapped via get-pip.py into .venv);
no `make` on machine (needs install; Makefile present). Key env vars unset.
