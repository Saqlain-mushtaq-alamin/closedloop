# Phase 03 plan (5 lines)
1. Tests first: `tests/test_runner.py` (timeout/memory/network/write-escape, V7, H8) failing on empty module.
2. `closedloop/exec/runner.py`: subprocess + timeout + RLIMIT/Job-Object memory cap (fail-closed) + import-level network/process block + tempdir-confined files + injected API only.
3. `closedloop/data/log.py` + `EpisodeResult` (plan Sec 6 fields) + append-only JSONL test (H10).
4. `closedloop/gen/generator.py`: structured {code, rationale} via client/CostMeter, ast parse gate, prompt-hash cache; `configs/gen.yaml`.
5. G0 pilot needs live Spark API (keys unset here): attempt probe, else STOP at Task 4 with 1-3 gated; Windows owns physics/API runs.

## Gate output (2026-10-28; Tasks 1-3 only)
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
37 passed in 22.14s (test_sim.py excluded: needs PyBullet, Windows-only)
G0 NOT measured -> no PHASE 03 PASS claim.
Numbers: runner 7/7, log 3/3, generator 5/5 (incl. tightened schema gate:
both code+rationale required). Probe spend $0.00.
Surprises: generator schema test caught a lenient default (fixed in code,
not the test); fork-child needed sys.modules eviction for the import block.
## Task 4 STOP: G0 pilot needs live Spark API; MODEL_API_KEY unset here and
billing blocked (plan Sec 17). Runner/generator/sim integration + pilot are
Windows work: install lock, run pytest tests/test_sim.py, then a keyed pilot
per configs/gen.yaml, pass rate computed from runs/<run_id>/episodes.jsonl.
