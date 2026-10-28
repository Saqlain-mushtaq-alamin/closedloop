# API probes (H17: probe, don't guess)

## 2026-10-28 — Phase 00 environment probe

- `MODEL_API_KEY`: **unset**. `META_API_KEY`: **unset**. (Presence only; values
  never printed, logged, or committed per H2.)
- No live API call attempted: without a key there is nothing to authenticate,
  and the plan (§17, Oct 27 status) already reports billing restricted until the
  card test hold clears. Probe spend: $0.00 (cap for this task: $2).
- Consequence (phase fallback): P01–P02 proceed offline; no experiment spend
  until a key exists and billing is confirmed.
- Still [VERIFY]: model IDs (`muse-spark-1.3`), base URL
  (`https://api.meta.ai/v1`), Spark $/Mtok, SAM 3.1 image-vs-video pricing, and
  account tier (P07/P08 caps assume Contributor tier + SAM video mode).
  Re-probe (text + image call, tokens/cost recorded here) once keys exist.

## 2026-10-28 — Phase 03 G0 pilot (verified live)
- `MODEL_API_KEY`: present and functional against `https://api.meta.ai/v1`.
- `muse-spark-1.3` live probe observations:
  - Model generates reasoning tokens (returned in `usage.completion_tokens_details.reasoning_tokens`).
  - Supports `reasoning_effort: "low"` parameter at root payload level (`reasoning: {"effort": ...}` returns 400).
  - Default reasoning effort consumes ~1022 tokens, exhausting a 1024 cap before content generation.
  - Setting `reasoning_effort: "low"` and `max_output_tokens: 2048` yields clean structured JSON output (~600 reasoning + ~600 output tokens).
- Live G0 pilot executed: 20 episodes, 20/20 pass rate (1.000 vs 0.30 threshold), spend $0.0055 USD.

