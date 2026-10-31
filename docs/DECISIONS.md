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

## 2026-10-30 — Invalidation of Run judge-g2-01 and Rerun judge-g2-02 (Adversarial Review)
- **Run ID:** `judge-g2-01` (invalidated, kept on disk per H12)
- **What happened (Adversarial Review Findings):**
  1. The judge used PyBullet body-ID segmentation buffer (`img[4]`) rather than live SAM 3.1 segmentation via Meta Model API (`/v1/responses`).
  2. Gate verification was loose: checked counts $\ge 30$, $b_U \le 0.50$, ignored freeze hash, and did not enforce `episodes_planned == episodes_observed`.
  3. Tests in `test_judge.py` were synthetic/tautological and did not exercise production code or real V9 controls.
  4. Failure sampling ran an outcome-dependent loop (366 collected), discarding 540 attempted episodes unlogged (H10/H13 breach), with divergent mass/friction distributions between success and failure arms.
  5. Cost accounting logged $0.00$ because `client.py` omitted `cost_usd`, and pre-flight used an arbitrary $0.0020 floor instead of measured pilot spend.
  6. The prompt was hardcoded in `judge.py` rather than covered by the freeze hash in `configs/judge.yaml`.
- **Fix:**
  1. Integrated live SAM 3.1 segmentation calling `https://api.meta.ai/v1/responses` with prompt grounding (`"red cube"`, `"green pad"`) in `LLMClient.segment()`, paired with strict geometric inner-margin test and Muse Spark 1.3 multimodal reasoning (`temperature=0.0`, `seed=42`).
  2. Implemented fixed sample plan (Rule H12): exactly 600 calibration episodes (300 successes on seeds 1,000,000–1,000,299, 300 failures on seeds 1,000,300–1,000,599), drawing $(mass, friction, yaw)$ from the identical distribution $D$, with every episode logged append-only (H10) to `episodes.jsonl`.
  3. Froze the complete judge configuration including prompt and camera in `configs/judge.yaml` and hashed it via `compute_judge_freeze_hash()`.
  4. Saved 10 visual inspection PNGs with bounding box and centroid overlays to `runs/judge-g2-02/inspection/`.
  5. Implemented live metered pilot and pre-flight cost check without invented floors.
  6. Rewrote `test_judge.py` to assert real do-nothing control, shuffled-labels permutation test, config freeze hash, seed overflow checks, and strict geometry.
- **Action (Gate G2 Rerun):** Executed clean run under fresh `run_id` `judge-g2-02`:
  - TPR: 1.0000 ($a_L = 0.9825 \ge 0.85$, PASS)
  - FPR: 0.0000 across all 300 failures
  - Worst-bucket upper bound $b_U = 0.8120 > 0.15$ (governed by deep bucket sample size $n=4$ where $cp\_upper(0, 4, 0.00125) = 0.8120$)
  - Gate G2 Verdict: `FAIL -> Pitch B` (H7/H8 compliant, camera certification blocked for Phase 08).

## 2026-10-30 — Pre-registration for Single Redo Run judge-g2-03 (Sample Allocation Fix)
- **Run ID:** `judge-g2-03`
- **Rationale & Scope:** Single pre-declared redo under Rule H12. In `judge-g2-02`, failure rollouts were partitioned by margin into B=4 buckets post-hoc from a fixed offset schedule, which resulted in uneven bucket counts ($n=0, 162, 134, 4$) and artificially inflated $b_U$ in the $n=4$ deep bucket ($cp\_upper(0, 4, 0.00125) = 0.8120$).
- **Pre-registered Sample Plan:**
  - Successes: Exactly 300 fresh successes starting at seed `1,001,000`.
  - Failures: Exactly 100 failures in each of the 4 pre-registered margin buckets ($B=4$, total 400 failures, total planned episodes = 700):
    1. `near_boundary`: $m \in [-0.05, 0.0)$ ($n=100$)
    2. `shallow`: $m \in [-0.15, -0.05)$ ($n=100$)
    3. `medium`: $m \in [-0.35, -0.15)$ ($n=100$)
    4. `deep`: $m \in [-1.00, -0.35)$ ($n=100$)
- **Sampling Constraint:** Buckets are filled using simulator ground truth margin (`sim_res.margin`) ONLY. Judge verdicts are never read during sampling or used to filter rollouts.
- **Invariants:**
  - `configs/judge.yaml` is unchanged.
  - Judge freeze hash `0a085ba70f01e4ef311e6e41472c16ce03cc9fd221d07698f526806ab8d4c94e` is unchanged.
  - Bucket edges are unchanged (`[-0.05, 0.0)`, `[-0.15, -0.05)`, `[-0.35, -0.15)`, `[-1.00, -0.35)`).
  - Gate G2 criteria ($a_L \ge 0.85$, $b_U \le 0.15$, ceiling $\ge 0.85$) are unchanged.
  - Delta split ($d_a = 0.005$, $d_b = 0.00125$) is unchanged.
- **Stop Condition:** One redo only. If G2 fails again, stop and report; do not retry.
- **Outcome (judge-g2-03 Execution):**
  - Planned: 700 episodes (300 successes, 400 failures). Logged: 700 episodes.
  - Successes ($n=300$): $k=300 \rightarrow \hat{a} = 1.0000$, one-sided Clopper-Pearson lower bound $a_L = 0.9825 \ge 0.85$ (**PASS**).
  - Failures ($n=400$, 100 per bucket):
    - `near_boundary` ($m \in [-0.05, 0.0)$): $n=100, k=2 \rightarrow \hat{b} = 0.0200$, $b_U = 0.1048 \le 0.15$
    - `shallow` ($m \in [-0.15, -0.05)$): $n=100, k=0 \rightarrow \hat{b} = 0.0000$, $b_U = 0.0647 \le 0.15$
    - `medium` ($m \in [-0.35, -0.15)$): $n=100, k=0 \rightarrow \hat{b} = 0.0000$, $b_U = 0.0647 \le 0.15$
    - `deep` ($m \in [-1.00, -0.35)$): $n=100, k=0 \rightarrow \hat{b} = 0.0000$, $b_U = 0.0647 \le 0.15$
  - Worst-bucket FPR upper bound: $b_U = 0.1048 \le 0.15$ (**PASS**).
  - Day-1 Ceiling: `ceiling(a=1.0, b=0.005, n_succ_cal=300, n_fail_cal=400, n_cell=113, K=16, delta=0.05, B=4, seed=1001000)` = $0.9435 \ge 0.85$ (**PASS**).
  - Gate G2 Verdict: **`PASS (G2 PASS)`** — unlocks camera-mode certification for Phase 08.




## 2026-10-30 - Pre-registration: single replacement repair trajectory cert-mint-01 (Phase 08 certification input)

- **Why:** Phase 06 passed its gate but persisted only 200-char `code_preview` per repair (`experiments/run_repair_h2h3.py:639`,
  `cand_code[:200] + "..."`). An exhaustive scan of all 816 JSON files under `runs/` found no full accepted program source
  (only 31-char do-nothing policies and 203-char previews), and `runs/` is gitignored so no git recovery exists. P06 results,
  reports, and Phase 07 results are NOT modified; this run only mints the missing Phase 08 input.
- **Design (B1-equivalent, text-only, one trajectory):** initial Spark generation (`muse-spark-1.3`, `max_output_tokens=2048`)
  then at most 1 repair round (plan cap is 5; P06 `max_rounds=1` replicated exactly). B1 random-search counterexample with
  `search_budget = falsifier_budget + bisection_steps + 1 = 17` evals; repair prompt text-only
  (`trace_summary="Naive loop failure from random parameter search"`); no filmstrip, no minimizer (faithful B1).
- **Acceptance (plan Section 10, all three required):** (1) candidate passes the counterexample, (2) candidate passes the
  regression set (nominal scenario plus loop scenario if the initial program passed it), (3) candidate survives a short
  falsifier re-run with fixed budget 5 (`CmaEsSampler`, `rerun_budget=5`). Single attempt: if the candidate is rejected at
  any stage, STOP and report; no second trajectory without human approval.
- **Seeds (repair stream only, H9):** `seed_base=60000`: paired scenarios 60000-60005 (loop 60000, retest 60001,
  held-out 60002-60005), B1 search RNG 160000 with episode seeds 160010-160026, evaluator/rerun base 260000
  (rerun episodes 260000-260004). Nominal scenario seed 150027 (P06 formula gives 150000, which already appears in
  `h2h3-full-03` episodes; 150027 is verified unused across all `runs/*/episodes.jsonl`; scenario content is the
  unchanged config nominal). No certification seed (2,000,000+) is touched. Overlap of every other planned seed with all
  prior runs verified empty before launch.
- **Budgets:** sim episodes fixed by rule pre-run: 1 loop + 17 search + 1 ce + R regression + 5 rerun + 4 held-out,
  where R = 1 + (1 if the initial program passes loop else 0), i.e. 29 or 30 total; the driver asserts logged==planned.
  LLM calls at most 2 (1 generation + 1 repair), CostMeter cap USD 5.00 for this run. Fresh empty prompt cache (NOT the
  shared `runs/llm_cache.json`): both calls are live, no replay of any P06 program.
- **Loop-pass contingency (pre-registered):** if the initial program passes the loop scenario, the 17-eval search still runs
  (fixed budget); if the search finds >=1 failure, the first failure becomes the CE and the single-repair path proceeds
  unchanged. If zero failures are found anywhere, STOP: report v0 undefeated, mint nothing, spend nothing further.
- **Freeze rule:** on accept only, write the COMPLETE program source to `runs/cert-mint-01/program_final.py`, plus
  `freeze.json` (sha256, program_id, seeds, acceptance evidence) and `manifest.json` referencing the exact source file.
  P06 gap noted: full source was never persisted; this run persists it by construction.

## 2026-10-30 — Outcome of Run cert-mint-01 (Valid Refusal Accounting)
- **Run ID:** `cert-mint-01`
- **Result:** REJECTED — candidate passed counterexample (Stage 1) and nominal regression (Stage 2), but failed Stage 3 short falsifier re-run (4 of 5 trials failed in simulation, worst margin -0.3696 on seed 260000).
- **Accounting & Preservation (Rule H12):** The run is preserved intact in `runs/cert-mint-01/` with 29 logged episodes. In accordance with Rule H12, a refusal is a valid experimental outcome and is not converted to a pass.
- **Infrastructure Findings & Remediations:**
  1. Mint driver updated to always persist `program_initial.py`, `program_candidate_v1.py`, `mint_trace.json`, and `llm_cache.json` for full traceability on both accepted and rejected runs.
  2. Initial generation tokens and cost are now explicitly attributed to Episode 1 in `episodes.jsonl`.
  3. Real measured counterexample margin is passed to `build_repair_prompt`.
  4. Manifest records total `spent_usd` and structured `tokens_spent`.
  5. Tested and verified with 7 passing unit tests in `tests/test_mint.py`.

## 2026-10-30 — Pre-registration: single replacement repair trajectory cert-mint-02 (Phase 08 certification input)
- **Run ID:** `cert-mint-02`
- **Why:** Replace rejected trajectory `cert-mint-01` with an authorized, single pre-registered attempt using the refreshed, audited mint infrastructure.
- **Configuration & Arm:** B1-equivalent, text-only (`muse-spark-1.3`, `max_output_tokens=2048`, `budget_cap_usd=5.0`, Tier 2 bounds from `configs/mint.yaml`). Single trajectory.
- **Acceptance Criteria (Plan §10, exact frozen rule):**
  1. Candidate passes the minimal counterexample.
  2. Candidate passes the regression set (nominal scenario + loop scenario if passed by initial program).
  3. Candidate survives short falsifier re-run (budget 5, CMA-ES sampler).
  Refusal at any stage is a valid outcome: preserve all artifacts, report, and stop.
- **Seeds (disjoint repair stream [0, 999999], Rule H9):**
  - `seed_base: 500000`: paired scenarios 500000–500005 (loop 500000, retest 500001, held-out 500002–500005).
  - Search RNG: 600000 with episode seeds 600010–600026 (17 episodes).
  - Evaluator/rerun base: 700000 with rerun episode seeds 700000–700004 (5 episodes).
  - Nominal scenario seed: 550027.
  - Verification: all seeds strictly in `[0, 999999]`; zero seeds in `[400000, 999999]` were used in any previous run.
- **Budgets:** Exactly 29 episodes (or 30 if initial loop passes: 1 loop + 17 search + 1 ce + R regression + 5 rerun + 4 held-out). At most 2 LLM calls (1 generation + 1 repair). CostMeter cap USD 5.00. Fresh empty cache (live calls, Rule H8).
- **Post-Run Protocol:**
  - If rejected: preserve `program_initial.py`, `program_candidate_v1.py`, `mint_trace.json`, `llm_cache.json`, manifest, and episodes. Report cost and STOP.
  - If accepted: persist `program_final.py` and `freeze.json` (SHA-256 pin, program_id), validate freeze, report program_id and total cost, STOP. Do not begin certification.

## 2026-10-31 — Outcome of Run cert-mint-02 (Valid Refusal Accounting)
- **Run ID:** `cert-mint-02`
- **Result:** REJECTED — candidate passed counterexample (Stage 1) and nominal regression (Stage 2), but failed Stage 3 short falsifier re-run on seed 700002 ($mass=9.1765, friction=0.4259, margin=-0.2800$).
- **Artifacts Preserved (Rule H12):** `runs/cert-mint-02/` preserved intact with 29 logged episodes, `program_initial.py`, `program_candidate_v1.py`, `mint_trace.json`, `manifest.json`, and `llm_cache.json`.
- **Cost:** Total API spend $0.009645 (1,806 tokens total).

## 2026-10-31 — Pre-registration: single B2-guided replacement repair trajectory cert-mint-03 (Phase 08 certification input)
- **Run ID:** `cert-mint-03`
- **Arm:** B2 (falsifier-guided active search with coordinate minimization toward nominal, Plan §8/§10). Text-only feedback (no vision calls, no filmstrip frames).
- **Model & Spending Cap:** `muse-spark-1.3`, `max_output_tokens=2048`, `budget_cap_usd=5.00`.
- **Difficulty & Bounds:** Tier 2 bounds from `configs/mint.yaml` ($x, y \in [-0.15, 0.15], yaw \in [-0.5, 0.5], mass \in [1.0, 11.5], friction \in [0.1, 1.0]$).
- **Seed Ledger (29 Episodes, strictly disjoint repair stream [0, 999999], Rule H9):**
  - Initial generation evaluation: 1 episode, seed `750000` (`s_loop`).
  - Falsification (CMA-ES, 10 evals): 10 episodes, seeds `760000`–`760009`.
  - Coordinate minimization (5 parameters toward nominal): 6 episodes, seeds `770000`–`770005` (initial eval + 5 coordinate substitutions).
  - Minimizer recheck: 1 episode, seed `770006`.
  - *Exploration subtotal: 10 + 6 + 1 = 17 episodes.*
  - Acceptance Stage 1 (minimized counterexample): 1 episode, seed `780000`.
  - Acceptance Stage 2 (nominal regression): 1 episode, seed `780001`.
  - Acceptance Stage 3 (short falsifier rerun, 5 evals): 5 episodes, seeds `790000`–`790004`.
  - Held-out evaluation (4 reporting episodes): 4 episodes, seeds `750002`–`750005`.
  - *Total planned episodes: 1 + 17 + 1 + 1 + 5 + 4 = 29 episodes.*
- **Verification:** Every episode seed in the 29-episode ledger is pairwise unique, in the repair stream (`0`–`999,999`), and completely disjoint from all previous runs and all calibration (`1,000,000`–`1,999,999`) and certification (`2,000,000`–`2,999,999`) seeds.
- **Acceptance Criteria (Plan §10, exact frozen rule):**
  1. Candidate passes the minimized counterexample (seed `780000`).
  2. Candidate passes the regression set (nominal seed `780001` + loop seed `750000` if passed by initial program).
  3. Candidate survives 5-episode short falsifier rerun (seeds `790000`–`790004`).
- **Protocol:** Execute exactly ONE trajectory.
  - If rejected: preserve `program_initial.py`, `program_candidate_v1.py`, `mint_trace.json`, `llm_cache.json`, manifest, and episodes. Report cost and STOP. No second trajectory without human approval.
  - If accepted: preserve `program_final.py`, `freeze.json` (SHA-256 pin, program_id), manifest, and acceptance evidence. STOP. Do not begin Phase 08 certification automatically.

## 2026-10-31 — Outcome of Run cert-mint-03 (ACCEPTED)
- **Run ID:** `cert-mint-03`
- **Result:** **ACCEPTED** — candidate repair passed all three acceptance stages:
  1. Stage 1 (minimized counterexample, seed 780000): PASS ($margin = +0.0050 > 0$).
  2. Stage 2 (nominal regression, seed 780001): PASS ($margin = +0.0050 > 0$).
  3. Stage 3 (5-episode short falsifier rerun, seeds 790000–790004): PASS (5/5 passed, min margin $+0.0050 > 0$).
- **Held-out Rate:** 75.0% (3/4 held-out episodes passed, reporting only).
- **Frozen Program Identification:**
  - Program ID: `bec73dec45a88431`
  - SHA-256 Hash: `bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55`
  - Source File: `runs/cert-mint-03/program_final.py`
  - Validated by: `validate_freeze(Path("runs/cert-mint-03"))`
- **API Cost & Tokens:**
  - Tokens: 794 input, 2,112 output (2,906 total tokens across 2 calls).
  - Total Spend: $0.009968 (well under the $5.00 cap).
- **Episodes:** Exactly 29 planned and 29 logged episodes in `runs/cert-mint-03/episodes.jsonl`.
## 2026-10-31 — Phase 08 Audit Remediation and Certified Re-run (cert-full-01)
- **Context:** An audit of the initial Phase 08 certification artifact identified 25 findings (6 blockers, 11 majors, 8 minors) resulting in a STOP verdict. Principal issues:
  1. Full-run camera verdicts were copied from ground truth (`jp = ts`) with zero API calls/cost.
  2. Price-of-footage calculation fell back to truth success on missing data.
  3. Policy runs were executed in-process without the required subprocess sandbox (Rules H13, H15).
  4. In-memory `CertificationLedger` lost state across processes, and claimed seeds after sampling rather than before.
  5. Config and judge freeze hash checks were not strictly enforced against the calibration run.
  6. Phase log contradicted code regarding error budget allocations and friction bounds.
- **Action (per Rule H12):**
  - Archived initial fabricated runs to `runs/cert-pilot-01-fabricated` and `runs/cert-full-01-fabricated`.
  - Replaced in-memory ledger with persistent disk-backed `CertificationLedger` (`runs/.certification_ledger.json`) claiming seeds prior to sampling.
  - Implemented sandboxed subprocess execution for all policy runs with 120s timeout and 1024 MB memory limit.
  - Modified `closedloop/exec/episode.py` to capture rendered camera frames (`render_judge_frame`) in the sandboxed child.
  - Resolved Windows Job Object `multiprocessing.spawn` memory issues by eliminating scientific/C-extension imports from module top-levels.
  - Implemented live `VisionJudge` evaluation across all 709 unique rendered camera frames using Meta Model API (SAM 3.1 + Muse Spark 1.3) with thread-safe prompt caching.
  - Re-implemented `compute_price_plot_data` to fail closed on missing cell or judge data and reflect actual judge misclassifications.
  - Fixed error budget math and reporting in `PHASE_08.md` and `cert.yaml` to ensure exact consistency ($d_{\text{cell}} = 0.003125$, headline $\delta = 0.05$, friction bounds $[0.1, 1.0]$).
- **Execution & Outcome:**
  - Pilot Run `cert-pilot-01`: 15 episodes, 15 sandboxed rollouts, live camera judge ($0.0140 spend), pre-flight projection confirmed cost headroom ($2.30 projected vs $15.00 cap).
  - Full Run `cert-full-01`: 2,459 episodes (16 cells $\times$ 150 + 59 headline episodes) in sandboxed subprocesses.
  - 709 unique camera frames evaluated by Meta API ($2.5940 spend). Real confidence diversity: $[0.90, 0.92, 0.95, 0.97, 0.98]$.
  - Headline State: $35/59 \to p_L = 0.4778$ (target $0.95$, uncertified).
  - Regional Cells: 8/16 cells certified ($p_L \ge 0.9623 \ge 0.90$ for mass $\le 6.25$ kg across all friction values).
  - State Area Fraction: $0.5000$. Camera Area Fraction: $0.5000$. Price of Footage Area Loss: $0.0000$.
  - Gate verification independently recomputed all 16 cell bounds and headline bound directly from `episodes.jsonl`.
  - `make gate PHASE=08` PASSED.

## 2026-10-31 — Phase 09 Explicit Cut of Optional Task T2 (Push Task)
- **Context:** Phase 09 Task 3 specifies: "(Optional, 90m) T2 smoke: B0 only, ≥20 trajectories, gap reported. Done when: logged or explicitly cut in DECISIONS.md."
- **Rationale:** The prompt and phase file instruct to run Phase 09 with focus on Hypothesis H4 (shift test) and state: "T2 only if instructed. Fallback / cut: Cut T2 first (always optional). Never cut the shift figure." To maintain strict focus on certifying and demonstrating the boundaries of guarantee transfer under distribution shift on Task T1 without unnecessary API spend or scope bloat, optional Task T2 is explicitly cut per Phase 09 guidelines.
- **Action:** Optional Task T2 is cut. Phase 09 focuses entirely on frozen distribution shift $D \to D'$ on Task T1 with certified program `bec73dec45a88431`.

## 2026-10-31 — Phase 09 Human-Authorised Fix for test_shift_disjoint_seeds (Self-Referential Test)
- **Context:** `test_shift_disjoint_seeds` in `tests/test_shift.py` checked `overlap = shift_seeds.intersection(claimed_set)` where `claimed_set` was read from the mutable on-disk `.certification_ledger.json`. When `run_shift.py` executed, it claimed the shift seeds into the ledger, causing subsequent test executions during `make gate` to flag the runner's own claimed seeds as an overlap.
- **Rule H7 Stop & Human Review:** The agent stopped and reported under Rule H7. The human explicitly instructed to decouple the test from the mutable ledger state and separate concerns across 4 targeted tests.
- **Fix:**
  1. `test_shift_disjoint_seeds`: Replaced mutable ledger read with independent planned seed ranges from `configs/cert.yaml` (2,474 planned P08 seeds); verified shift seeds in $[2000000, 2999999]$; verified pilot and full shift cohorts disjoint; verified disjointness from P08 planned seeds with vacuity guards.
  2. `test_shift_vs_logged_p08_seeds`: Verified real `episodes.jsonl` from Phase 08 and `shift-full-01` are both non-empty and have zero seed overlap.
  3. `test_ledger_rejects_reclaim`: Verified `CertificationLedger` raises `LeakageError` on overlapping claims using an isolated temporary ledger (`tmp_path`).
  4. `test_shift_seeds_in_ledger_after_run`: Verified that all shift seeds executed in `shift-full-01` are recorded in the real on-disk ledger.
- **Action:** Human-authorized test restructuring applied to `tests/test_shift.py`.

## 2026-10-31 — Phase 10 Gate G3 Feature Freeze Declaration
- **Context:** Phase 10 Task 3 requires declaring Gate G3 Feature Freeze: "Done when: docs/DECISIONS.md freeze entry + tag; further changes only via P11 text. G3: after this gate, features frozen — bugs only, no new arms/tasks."
- **Scope & Deliverables Frozen:**
  1. All physical experiments, simulation environments, arms (B0, B1, B2, B3), and tasks (hero task T1) are frozen. No new arms or tasks.
  2. All precomputed assets (`assets/`) and provenance manifest (`assets/manifest.json`) are generated strictly from logs and frozen.
  3. The offline precomputed dashboard (`dashboard/index.html`) is frozen, verified with zero external network / API dependencies.
  4. Subsequent changes in Phase 11 and Phase 12 are strictly limited to documentation, README, technical report, and video voiceover assets.
- **Action:** Gate G3 feature freeze declared and logged. Tagged `eod-1102`.

## 2026-10-31 — Phase 10b Authorisation: Judge Console Presentation Layer Rebuild
- **Context:** Gate G3 froze physical experiments, simulation environments, arms, tasks, configs, and run directories. The existing dashboard was a static presentation layer with several schematic figures and hard-coded values that violated Rule H11.
- **Authorisation:** Human authorization granted to rebuild the presentation layer only.
- **Scope Restrictions:**
  1. Allowed modifications: `dashboard/`, `closedloop/report/`, `assets/`, `tests/test_dashboard.py` (adding new tests without loosening existing ones), and `docs/`.
  2. Forbidden modifications: `runs/*`, `configs/*`, `closedloop/certify/*`, `closedloop/sim/*`, locked files, or any experiment code.
- **Objective:** Replace static dashboard with interactive Judge Console (`build_ui_data.py`, `render_replays.py`, `dashboard/data.js`, pure client-side Clopper-Pearson calculator, live replay viewer, interactive probe), ensuring 100% of numbers, bounds, diffs, and replay frames are computed strictly from logs.



