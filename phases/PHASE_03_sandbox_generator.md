# Phase 03 — Sandbox runner + program generator (Gate G0)

## Goal
Run LLM-written programs safely in a subprocess and generate Spark programs with structured output, logged as EpisodeResult JSONL. Why it matters: protects validity (H13/H15) and Use of Meta Tooling; G0 proves the task is learnable at all.

## Inputs
- Plan §6, §8; P00 client/CostMeter; P02 env/sampler.

## Deliverables
- `closedloop/exec/runner.py` (timeout, memory, no network, temp-dir writes, primitives-only imports), `closedloop/gen/generator.py`, `closedloop/data/log.py` (append-only JSONL), `configs/gen.yaml`

## Tasks
1. (90m) Runner tests first, then runner. Done when: sandbox tests pass (below).
2. (60m) EpisodeResult writer/reader (plan §6 fields). Done when: integration test writes + re-reads valid records.
3. (90m) Spark generator (structured `{code, rationale}`, parse-validate before exec, prompt-hash cache). Done when: generated program runs via runner.
4. (60m) G0 pilot: Spark on tier-1 tasks (pilot scale, V15). Done when: pass rate computed from logs only.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_sandbox_timeout_memory_network` | infinite loop killed; network/write escape blocked | timeout=failure recorded | H15 escape, hangs |
| `test_crash_accounting` (V7) | exception/timeout/invalid = failure, counted | count in report | dropped failures (H13) |
| `test_jsonl_append_only` (H10) | second run appends, never rewrites | line count grows only | edited raw data |
| `test_no_fake_imports` (H8) | no Fake* in closedloop/experiments paths | PASS | fake science |
| `test_generator_parse_gate` | unparseable output never executed | counted failure | arbitrary code exec |

## Validity checks
- V7 crash count printed; V15 pilot before any scale-up; V11 config frozen for G0 pilot. Every LLM call via client + CostMeter (H4/H5).

## Expected numbers
**G0: Spark tier-1 pass ≥30%.** Below: simplify primitives/tasks (plan §14), re-pilot once; still below → STOP and ask. Invalid-program rate >50% also STOP (prompt/API problem, check API_NOTES [VERIFY]).

## Gate
Run: `make gate PHASE=03`. Pass: tests pass + G0 ≥30%, prints `PHASE 03: PASS (G0 PASS)`. STOP on sandbox escape — do not proceed.

## Fallback / cut
Simpler primitives (fewer args, slower motion). No forensic tools here (cut order item 2, P06 optional only).

## Budget and time-box
Pilot ≤200 episodes, ≤ $5 API; agent ≤ $4. Oct 29. Tag `eod-1029`.

## Compliance
H4, H5, H8, H10, H13, H15, H17. Hackathon: Meta model use (model IDs logged).

## Human review (15 min)
Read 5 generated programs + traces; check `episodes.jsonl` fields; confirm crash count >0 test was real. Wrong: program imports beyond primitives, any direct API call outside client.py.

## Agent run prompt
Read AGENTS.md, plan §6/§8, and this phase file. Run Phase 03 only: tests first, G0 pilot at pilot scale, `make gate PHASE=03`, stop. Report G0 pass rate from logs.
