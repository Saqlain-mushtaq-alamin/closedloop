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

## Windows job-object fix 2026-10-28 (UNVERIFIED live; uncommitted)
Root causes of 'job-object limit failed' x6: (1) no restype on
CreateJobObjectW/OpenProcess -> 64-bit HANDLE truncated to 32 bits ->
ERROR_INVALID_HANDLE everywhere; (2) DWORD*12 (48 B) for a 64 B struct,
LimitFlags written at byte 4 not 16; (3) bare False hid the failing call.
Fix: exact ABI structs (64/48/144 B, guarded by tests/test_win32_job.py),
declared argtypes/restype, per-call GetLastError diagnostics surfaced in
outcome.detail, QueryInformation round-trip kept. Fail-closed preserved.
Also: fork replaced by spawn everywhere (measured parent VmSize 3.2 GB
inherited across fork vs 256 MB RLIMIT_AS -> order-dependent flake in
test_sandbox_write_escape); full suite 3x41 stable after the change.
Memory test is now incremental growth (robust to post-start assignment).
Windows still must prove: real Job Object path + memory bomb under the cap.

## Pre-G0 changes 2026-10-28 (uncommitted; no live calls, $0 spent)
A. Fail-closed accounting: charge() raises UnpricedModelError without a
verified price (was: silent $0.00); set_price rejects negatives;
load_prices() requires pricing_verified:true (configs/pricing.yaml ships
unverified -> live calls blocked); client validates usage block
(missing/negative/non-int rejected before charging; explicit zeros
allowed and logged). Cap enforced cumulatively per response; failed
attempts cost nothing client-side (server-side work unknowable: noted).
B. G0 harness: scripts/run_g0_pilot.py + closedloop/exec/pilot.py
(generate-once, 20 repair episodes, manifest, summarize vs 0.30) +
episode builder/checker (sub-namespace isolation, parent-side truth) +
facade (env.py) + summarize_run/write_manifest + shared llm_cache.json.
Verified: abort path live (exit 2, no spend, no runs/ dir); 66/66 tests
(excl. sim). pricing/model rates still UNVERIFIED -> pilot stays blocked.
