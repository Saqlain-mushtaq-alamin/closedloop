# Phase 00 plan (5 lines)
1. Tests first: `tests/test_compliance.py` (V13/V14/H4 checks) failing on empty tree.
2. Repo files: README (built-during note), LICENSE (MIT), THIRD_PARTY.md, configs/base.yaml.
3. Makefile (setup/test/lint/controls/gate/report) + `check_no_secrets.sh` + `check_locked.sh` stub.
4. `closedloop/llm/cost.py` (CostMeter, cap abort) + `client.py` (env keys, max tokens, 3 retries).
5. Probe API (record tier/SAM mode in API_NOTES.md; offline if blocked), then `make gate PHASE=00`.
