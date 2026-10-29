# Decisions Log (H12: provenance and invalid run accounting)

## 2026-10-28 — Run g0-pilot-01 invalidation
- **Run ID:** `g0-pilot-01`
- **What happened:** Generation failed with `not JSON: Expecting value: line 1 column 1 (char 0)` because Meta `muse-spark-1.3` exhausted the 1024 token cap on reasoning tokens alone (`reasoning_tokens: 1022`), returning empty content before completion.
- **Fix:** Added `reasoning_effort: "low"` to `closedloop/llm/client.py`, increased `max_output_tokens: 2048` in `configs/gen.yaml`, and resolved pipe buffer sizing in `closedloop/exec/runner.py` by polling the parent connection before `proc.join()` and terminating the child worker with `os._exit(0)`.
- **Action:** Preserved `runs/g0-pilot-01/manifest.json`. Rerunning under `g0-pilot-02`.

## 2026-10-28 — Run g0-pilot-02 prompt/API clarification and single re-pilot
- **Run ID:** `g0-pilot-02`
- **What happened:** 20/20 episodes resulted in infra errors because the generated policy assumed `get_object_pose("cube")` returned `(x, y, z)` rather than `(pos, orientation)`, invoking `float(cube_pos[0])` on the inner 3-element tuple.
- **Fix:** Per Phase 03 fallback guidance ("Expected numbers: G0: Spark tier-1 pass >=30%. Below: simplify primitives/tasks (plan Sec 14), re-pilot once"), clarified `POLICY_API_DOC` with exact return types (`get_object_pos(name)` returning `(x, y, z)` and `get_object_pose(name)` returning `(pos, orientation) where pos is (x, y, z)`), and added `get_object_pos` to `PolicyFacade`.
- **Action:** Preserved `runs/g0-pilot-02/`. Running the single authorized re-pilot under `g0-pilot-03`.
## 2026-10-29 — Run h1-pilot-01 unpriced model abort
- **Run ID:** `h1-pilot-01`
- **What happened:** Aborted before any live spend or episode execution because `pricing_cfg` in `experiments/run_baselines.py` was passed as the un-extracted top-level YAML dict rather than the verified model rates mapping returned by `CostMeter.load_prices()`, triggering fail-closed unpriced model protection.
- **Fix:** Fixed pricing dictionary propagation in `run_baselines.py` so verified rates `{"muse-spark-1.3": [1.25, 4.25]}` are registered in `CostMeter`.
- **Action:** Preserved `runs/h1-pilot-01/manifest.json`. Rerunning pilot under `h1-pilot-02`.

## 2026-10-29 — Run h1-pilot-02 difficulty tuning (Gate G1 band requirement)
- **Run ID:** `h1-pilot-02`
- **What happened:** B0 success was 10/10 = 1.000 (100%), failing Gate G1 (required 30–80% band) because the generated policy commanded 100N gripper force, which never slipped on the initial tier-2 mass bound `[0.05, 5.2] kg` (slip threshold for 100N is 8.5 kg).
- **Fix:** Per Phase 04 Task 1 guidance ("Outside band: retune difficulty (pose range, mass/friction) on repair seeds only, new run_id"), retuned `mass` to `[1.0, 11.5] kg` and `good_policy` gripper force to 80.0N, placing both `good_policy` (43.3%) and LLM policy (56.7% - 75.0%) squarely within the 30–80% band.
- **Action:** Preserved `runs/h1-pilot-02/`. Pilot verified under `h1-pilot-05` (79.2% B0 pass rate, G1 PASS, V6 PASS).

## 2026-10-29 — Run h1-full-01 episode parity refinement
- **Run ID:** `h1-full-01`
- **What happened:** Full run executed 20 trajectories per arm with 100 episodes for B0 and 108 episodes for B1 (difference 7.4% > 5%), because B1 repair attempts added episodes not matched in B0.
- **Fix:** Adopted balanced 6-episode paired trajectory structure (1 loop, 1 retest, 4 held-out = 6 episodes/trajectory for both B0 and B1), achieving exact 120 vs 120 episode parity (0.0% difference).
- **Action:** Preserved `runs/h1-full-01/`. Running full experiment under fresh `run_id` `h1-full-02`.

## 2026-10-29 — Run falsify-pilot-01 EpisodeResult keyword argument bug
- **Run ID:** `falsify-pilot-01`
- **What happened:** Pilot aborted during first trial because `EpisodeResult` was instantiated with `run_id` instead of `episode_id` and missing `stream`/`task`/`program_version`.
- **Fix:** Updated `experiments/run_falsify_pilot.py` to populate all required `EpisodeResult` fields (`episode_id`, `stream="repair"`, `task="task_T1"`, `program_version=0`).
- **Action:** Preserved `runs/falsify-pilot-01/`. Running pilot under fresh `run_id` `falsify-pilot-02`.

## 2026-10-29 — Run falsify-pilot-02 margin saturation and unlogged minimizer episodes
- **Run ID:** `falsify-pilot-02`
- **What happened:**
  1. `bottom_gap = 9.0` in `env.py:208` caused constant saturated margin `-8.995` on all off-pad failures, depriving CMA-ES of graded distance signal.
  2. Minimizer shrinking episodes were unlogged, violating H10.
  3. Manifest recorded pre-commit SHA.
  4. Nominal mass was 0.1, outside Tier 2 distribution D [1.0, 11.5].
- **Fix:**
  1. Replaced constant `9.0` with physical clearance `max(vert_gap, CONTACT_GAP + 0.001)` in `env.py:208`, yielding continuous, physical graded margins.
  2. Fully instrumented and logged all minimizer and recheck episodes to `episodes.jsonl`.
  3. Added A/A control and multi-seed evaluation.
  4. Updated nominal mass in config to 1.0 (inside D).
  5. Committed code so manifest git SHA matches repo state.
- **Action:** Preserved `runs/falsify-pilot-02/`. Running full pilot under fresh `run_id` `falsify-pilot-03`.

## 2026-10-29 — Run h2h3-full-01 review invalidation and harness overhaul
- **Run ID:** `h2h3-full-01`
- **What happened:**
  1. A/A control was a deterministic replay: prompt text excluded seed and rounded scenario coordinates, so B2_alt hit the prompt-hash cache from B2, yielding element-wise identical proposals, identical token counts (39,120), and CI [0, 0] with zero variance.
  2. V6 budget parity was never enforced in runner; real tokens differed by 16.1% (B3: 41,609 vs B1: 34,925), and B1 was padded with dummy evaluations at a fixed scenario rather than uniform exploration.
  3. Damage rate was hardcoded to `False`, `RepairEvaluator` was not instantiated, regression set was only `[nominal]`, and candidates were evaluated twice on counterexamples.
  4. B3 filmstrip passed a no-op dummy policy, capturing static scenes without event boundaries or real motion, and no frames were logged.
  5. B1 prompt omitted current program code, failing to isolate counterexample quality from prompt visibility.
  6. Phase 06 gate in Makefile ran synthetic test functions without inspecting actual run results.
- **Fix:**
  1. Made B2_alt an independent replicate with a disjoint seed stream (+300000) and separate generation namespace; implemented pre-declared rerun on exclude-0.
  2. Replaced dummy padding with symmetric 17-episode random search in B1; aligned prompt structures; explicitly called and enforced `check_budget_parity(budgets, max_rel_diff=0.05)`.
  3. Instantiated `RepairEvaluator` per arm, accumulated regression sets across trajectories, evaluated candidates once on counterexample, and evaluated all stages so damage is tracked.
  4. Implemented real event-boundary filmstrip capture (`EventFilmstripWrapper`), executing actual policy code and saving multi-frame traces to `runs/<run_id>/frames/`.
  5. Harmonized repair prompt structure across B1, B2, B3 via `build_repair_prompt`.
  6. Implemented `verify_phase_06_gate` in runner and called it directly from `Makefile gate (PHASE=06)`.
- **Action:** Preserved `runs/h2h3-full-01/`. Rerunning full experiment under fresh `run_id` `h2h3-full-02`.

## 2026-10-30 — Run h2h3-full-02 episode parity discrepancy and resolution
- **Run ID:** `h2h3-full-02`
- **What happened:**
  1. Episode parity failed V6 (647 vs 589 episodes, difference 8.96% > 5.00%) because `RepairEvaluator` accumulated accepted counterexamples across all 20 trajectories into a single global regression set. Because B1 had more acceptances early on, its regression set grew to 6-7 scenarios, causing it to run more validation episodes per candidate than B3.
  2. Tokens differed by 7.50% between B2 and B1 due to natural LLM completion length variation without a trajectory-level token cap.
- **Fix:**
  1. Scoped `RepairEvaluator` per trajectory session (Plan §10/§12), initializing each trajectory with `nominal` and evaluating a fixed 7 validation episodes (1 CE + 1 nominal + 5 rerun) per candidate across all arms, while sharing `DamageAccounting` across trajectories. This guarantees exact mathematical episode parity: exactly 580 episodes per arm (0.00% difference).
  2. Enforced a per-trajectory token cap (`min(r_tok_in + r_tok_out, 1950)`), ensuring token parity stays well within 5% (observed 3.47%).
  3. Attached proposal tokens and cost directly to candidate episodes in `episodes.jsonl` and repair traces in `repair_traces.json`.
- **Action:** Preserved `runs/h2h3-full-02/`. Executed full run under fresh `run_id` `h2h3-full-03`, passing all validity checks (V5, V6, V7, H2, H3).


