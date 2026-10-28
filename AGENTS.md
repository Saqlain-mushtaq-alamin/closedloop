# AGENTS.md: rules for AI coding agents working on ClosedLoop

You are helping ONE human build **ClosedLoop** for the Meta Global AI Developer Hackathon
(Indie track, theme "Push the Frontier"). Build window: Oct 26 - Nov 4, 2026.
Final deadline: Nov 4, 9:00 PM ET. The human's own target is to submit on **Nov 3**.

**Goal: a VALID, reproducible result.** A small valid result beats a big invalid one.
There is no time for reruns, so find problems early. When in doubt, STOP and ask.

## 0. Read first, in this order
1. `closeloop_plan.md` (the plan; decisions tagged `[LOCKED]` must not change)
2. The current phase file `phases/PHASE_XX_*.md`
3. This file

If they conflict, the HARD RULES below win, then the phase file, then the plan.
Report the conflict to the human. Never resolve it silently.

## 1. HARD RULES (never break one; if a task seems to need it, STOP and ask)

- **H1 Built during the event.** Write all code in this repo, during the event. Do not paste code from
  earlier private projects, employers, or unlicensed sources. Never rewrite git history: no `push --force`,
  no rebase or squash of pushed commits, no amend after push, no deleting pushed branches or tags.
- **H2 Secrets.** Never open, print, log or commit `.env` or any key. Read keys only from the environment
  (`META_API_KEY` for Muse Code, `MODEL_API_KEY` for project code). No keys in code, tests, logs,
  notebooks or error messages. Run `scripts/check_no_secrets.sh` before every commit.
- **H3 Licences and assets.** Only permissive dependencies (MIT, BSD, Apache-2.0, PSF). Record every third-party
  asset (URDF, mesh, texture, font, dataset) in `THIRD_PARTY.md` with its licence and source URL.
  No copyrighted media (music, images, logos) in the repo or the demo.
- **H4 Meta models only.** All LLM and vision calls go through `closedloop/llm/client.py`
  (Meta Model API, base URL `https://api.meta.ai/v1`; models `muse-spark-1.3`, `muse-wonder-1.0`, SAM 3.1).
  Never call another AI provider from project code.
- **H5 Budget.** Every call goes through `CostMeter`. Hard cap from env `BUDGET_USD_CAP` (default 60).
  Abort at the cap. Log tokens and cost for each call. Set `max_output_tokens` on every call
  (reasoning tokens count toward it and are billed). Max 3 retries with backoff. No unbounded loops.
- **H6 Locked files.** NEVER modify `closedloop/certify/stats.py`, `tests/test_stats.py`,
  `tests/test_coverage.py`, `LOCKED_HASHES.txt`. `scripts/check_locked.sh` verifies them.
  If you think there is a bug, STOP and report it with a failing example.
- **H7 Tests are sacred.** Never edit, delete, skip, xfail or loosen a test or threshold to make it pass.
  You MAY add tests. If a test looks wrong, STOP and explain why.
- **H8 No fake science.** No mocks or stubs of the simulator, the judge or the LLM in any code path that
  produces experiment results. Fakes are allowed only in unit tests, are named `Fake*`, and are never
  imported by `closedloop/` or `experiments/`.
- **H9 Data separation.** Seed ranges: repair 0-999,999; calibration 1,000,000-1,999,999;
  certification 2,000,000-2,999,999. Only `closedloop/certify/` may load certification seeds.
  Each certification seed is used once per program. `sampler.py` raises `LeakageError` on violation.
- **H10 Raw data is append-only.** Write one `EpisodeResult` per episode to `runs/<run_id>/episodes.jsonl`.
  Never edit or delete lines. Analysis reads logs only.
- **H11 Numbers are generated.** No number in the README, report or demo unless `make report` produced it
  from logs (with run_id, git SHA and config hash). Never type results by hand.
- **H12 Fixed sample plan.** Sample sizes, seeds, arms and thresholds live in `configs/*.yaml` and are frozen
  (config hash in the run manifest) before a full run. No stopping, extending or re-running based on
  outcomes. If a run is invalid because of a bug: keep the old run directory, add an entry to
  `docs/DECISIONS.md` (what, why), then rerun under a NEW run_id.
- **H13 Failure accounting.** Exceptions, timeouts, invalid programs and simulator errors count as FAILURES
  and are counted in the report. No bare `except:`. No `pass` on errors. No silent retry of an episode.
- **H14 Claim wording.** Never write "first", "novel", "proven", "safe" or "camera alone". Write
  "rendered camera footage", "certified in simulation under distribution D", and
  "to my knowledge, I did not find ...".
- **H15 Safe execution.** LLM-written robot programs run in a subprocess with a timeout and memory limit,
  no network, writes only to a temp dir, and only the primitives API importable.
- **H16 Scope.** Do only the current phase. No refactors of unrelated code, no extra features, no starting
  the next phase, no changes to `[LOCKED]` decisions.
- **H17 Do not guess.** If unsure about an API, a library function or a model name, run a tiny probe and
  record the result in `docs/API_NOTES.md`, or ask the human.

## 2. Workflow for every phase
1. Create or switch to branch `phase/NN-short-name`.
2. Read the phase file. Write a 5-line plan in `docs/phase_logs/PHASE_NN.md` before coding.
3. Do tasks in order. For each task: write or extend the test first, then the code, run its tests, then commit.
4. After the last task run `make gate PHASE=NN`. Paste the full command output into the phase log.
5. If a gate or control fails: do NOT edit tests. Diagnose, fix the code, rerun. Max 3 fix attempts,
   then STOP and report what you tried.
6. Finish with the final reply (section 6). Do not start the next phase. The human merges.

## 3. Commands (created in Phase 0)
`make setup`, `make test`, `make lint`, `make controls`, `make gate PHASE=NN`, `make report RUN=<run_id>`.
Tools: Python 3.11, pytest, ruff, pinned `requirements.lock`.

## 4. Code standards
- Type hints everywhere, short docstrings, modules under about 300 lines, pure functions for statistics.
- All randomness through `numpy.random.default_rng(seed)` with seeds from config. Nothing time-dependent.
- Interfaces follow Section 6 of `closeloop_plan.md` (`EpisodeResult` and the Protocols).
- Log model ID, reasoning effort, token counts and a response hash for every LLM call.
  Cache LLM responses by prompt hash so reruns do not respend.

## 5. Commit and review format
- One logical change per commit, about 300 changed lines at most.
- Message: `phaseNN: <what> [tests: <passed>/<total>]`.
- `docs/phase_logs/PHASE_NN.md` must contain: what changed, files added, tests added, gate output,
  numbers observed vs the expected range, open questions, and anything surprising.

## 6. Final reply format (end of every phase)
- **Status:** PASS or STOP.
- **Gate output:** pasted exactly, not summarized.
- **Changed files:** list.
- **Risks and surprises:** list. Say "none" only if true.
- **Questions for the human:** list.
- **Estimated spend this phase:** from CostMeter.

## 7. Stop conditions (stop and report immediately)
- A hard rule would be broken.
- A locked file needs a change, or a test seems wrong.
- A control fails (determinism, negative control, positive control, leakage, A/A, budget parity).
- An observed number is far outside the expected range in the phase file.
- Spend exceeds the phase budget.
- You are about to guess instead of check.
