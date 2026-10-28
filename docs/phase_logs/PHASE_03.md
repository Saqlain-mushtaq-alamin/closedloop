# Phase 03 plan (5 lines)
1. Tests first: `tests/test_runner.py` (timeout/memory/network/write-escape, V7, H8) failing on empty module.
2. `closedloop/exec/runner.py`: subprocess + timeout + RLIMIT/Job-Object memory cap (fail-closed) + import-level network/process block + tempdir-confined files + injected API only.
3. `closedloop/data/log.py` + `EpisodeResult` (plan Sec 6 fields) + append-only JSONL test (H10).
4. `closedloop/gen/generator.py`: structured {code, rationale} via client/CostMeter, ast parse gate, prompt-hash cache; `configs/gen.yaml`.
5. G0 pilot needs live Spark API (keys unset here): attempt probe, else STOP at Task 4 with 1-3 gated; Windows owns physics/API runs.
