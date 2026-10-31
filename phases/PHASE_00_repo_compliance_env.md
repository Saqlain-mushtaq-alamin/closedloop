# Phase 00 — Repo, compliance, environment

## Goal
Stand up the public repo, compliance scaffolding, and the metered Meta API client so every later phase is reproducible and capped. Why it matters: protects Technical Depth and validity — no result is trusted without H2/H5/H11 enforced from commit one.

## Inputs
- `planning/closeloop_plan.md` §3, §7, §17; `AGENTS.md` H1–H17. No earlier phase outputs.

## Deliverables
- `README.md` (built-during-hackathon note, licence, track), `LICENSE`, `.gitignore` (`.env`), `THIRD_PARTY.md`
- `Makefile` (`setup/test/lint/controls/gate/report`), `requirements.lock`, `scripts/check_no_secrets.sh`, `scripts/check_locked.sh`
- `closedloop/llm/client.py`, `closedloop/llm/cost.py` (CostMeter), `docs/API_NOTES.md`, `configs/base.yaml`

## Tasks
1. (45m) Repo layout + licence + README note + `.gitignore`. Done when: `git status` clean, `.env` ignored (`git check-ignore .env`).
2. (60m) Makefile + check scripts (stub locked-check until P01). Done when: `make test` runs, both scripts exit 0 on clean tree.
3. (90m) CostMeter + client skeleton (env keys only, `max_output_tokens` required, ≤3 retries). Done when: cap test passes (below).
4. (60m) API probe: model IDs, base URL `https://api.meta.ai/v1`, text + image call, tokens/cost/call, **account tier + SAM image-vs-video pricing/mode** (P07/P08 caps assume Contributor tier + SAM video mode). Done when: results in `docs/API_NOTES.md`; if billing blocked, record blocker + date [VERIFY] and continue offline.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_cost_meter_cap` (V14) | spend over tiny cap aborts | raises/aborts at cap | unbounded billing |
| `test_no_secrets` (V13) | scan finds planted fake key in tmp copy | FAIL on plant, PASS clean | committed keys |
| `test_llm_client_only` | only client.py references provider | PASS | H4 bypass |
| `test_env_ignored` | `.env` not tracked | PASS | H2 leak |

## Validity checks
- V14: cap abort with `BUDGET_USD_CAP=0.01` test double. V13: secrets + wording scan clean. Prices/model IDs marked [VERIFY] until probe output exists.

## Expected numbers
Probe: 1 text + 1 image call succeed; cost/call recorded (plan est. Spark $1.25/$4.25 per M tokens [VERIFY]). Outside: if API blocked, STOP experiment spend, do P01–P02 offline.

## Gate
Run: `make gate PHASE=00`. Pass: all tests pass, prints `PHASE 00: PASS`. STOP if: probe needs a guessed model ID (H17) or a secret would be logged (H2).

## Fallback / cut
If API blocked: finish repo offline; Ollama plumbing only (never in experiment results, H8). Cut nothing else.

## Budget and time-box
0 episodes; probe ≤ $2; agent ≤ $3. Half day, Oct 28 AM. Tag `eod-1028` shared with P01.

## Compliance
H1, H2, H3, H4, H5, H14, H17. Hackathon: eligibility [VERIFY], IP/licence, Meta-models, billing cap.

## Human review (15 min)
Open `README.md`, `THIRD_PARTY.md`, `docs/API_NOTES.md`; run `make gate PHASE=00`. Wrong looks like: any key-like string, missing built-during note, unpriced probe.

## Agent run prompt
Read AGENTS.md, the plan, and this phase file. Run Phase 00 only: tests first, then code, `make gate PHASE=00`, paste gate output in the phase log, stop.
