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

