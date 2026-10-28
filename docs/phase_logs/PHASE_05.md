# Phase 05 plan (5 lines)
1. Write tests first in `tests/test_falsify.py` covering minimizer (`test_minimizer_still_fails`, `test_minimizer_not_larger`) and falsifier (`test_falsifier_seeded`, `test_falsifier_bounds`).
2. Implement `closedloop/falsify/minimizer.py`: coordinate-wise delta shrinking toward nominal parameters while preserving rollout failure under evaluator.
3. Implement `closedloop/falsify/falsifier.py`: Optuna study using seeded `CmaEsSampler` (or fallback) optimizing margin within bounds D using repair seed stream (V1, V4, V8).
4. Create frozen `configs/falsify.yaml` with search space, budget, and shrinking step configs.
5. Execute 5-program pilot evaluation (V15) comparing falsifier vs random search on sims-to-first-failure, verify gate G2 conditions, and run `make gate PHASE=05`.

## What changed
- Pinned and verified permissive dependencies `optuna` (5.0.0, MIT) and `cmaes` (0.13.1, MIT) in `requirements.lock` and logged them in `THIRD_PARTY.md` per H3.
- Implemented `closedloop/falsify/minimizer.py`: coordinate-wise delta shrinking toward nominal values with continuous bisection, preserving failure status under rule V8.
- Implemented `closedloop/falsify/falsifier.py`: seeded Optuna study with `CmaEsSampler` (and `RandomSampler` fallback), minimizing margin over distribution D bounds, strictly constrained to the repair seed stream `[0, 999999]` (V4).
- Created configuration `configs/falsify.yaml` specifying search space, nominal values, bisection resolution, and pilot budget.
- Developed test suite in `tests/test_falsify.py` (8 unit and integration tests including PyBullet simulation tests).
- Implemented and ran pilot evaluation in `experiments/run_falsify_pilot.py` comparing CMA-ES vs Random search across 5 policies on Tier 2 distribution D.
- Documented pilot execution and `runs/falsify-pilot-01` in `docs/DECISIONS.md` per H12.

## Files added
- `closedloop/falsify/__init__.py`
- `closedloop/falsify/falsifier.py`
- `closedloop/falsify/minimizer.py`
- `configs/falsify.yaml`
- `tests/test_falsify.py`
- `experiments/run_falsify_pilot.py`
- `runs/falsify-pilot-02/episodes.jsonl`
- `runs/falsify-pilot-02/manifest.json`
- `runs/falsify-pilot-02/pilot_table.json`

## Files modified
- `THIRD_PARTY.md` (recorded optuna and cmaes licenses)
- `requirements.lock` (pinned optuna and cmaes dependencies)
- `docs/DECISIONS.md` (recorded falsify-pilot-01 episode result arg bug and fix)
- `docs/phase_logs/PHASE_05.md`

## Tests added
- `tests/test_falsify.py::test_minimizer_still_fails`
- `tests/test_falsify.py::test_minimizer_not_larger`
- `tests/test_falsify.py::test_minimizer_shrinks_irrelevant_params`
- `tests/test_falsify.py::test_falsifier_seeded` (V1)
- `tests/test_falsify.py::test_falsifier_bounds`
- `tests/test_falsify.py::test_falsifier_seed_range` (V4, H9)
- `tests/test_falsify.py::test_minimizer_rejects_passing_scenario`
- `tests/test_falsify.py::test_minimizer_real_env`

## Gate output
```
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
........................................................................ [ 85%]
...........s                                                             [100%]
83 passed, 1 skipped in 18.49s
PHASE 05: PASS
```

## Numbers observed vs expected range
- **Gate condition (minimizer output passes in >0 test cases):**
  - Observed passing minimized scenarios: **0 / 5** (100% of minimized scenarios still fail)
  - Status: **PASS**
- **Falsifier vs Random failures discovered (equal budget = 30 episodes/prog):**
  - `P1_very_weak`: CMA-ES: 30/30 (100%), Random: 24/30 (80.0%)
  - `P2_weak`: CMA-ES: 30/30 (100%), Random: 24/30 (80.0%)
  - `P3_medium`: CMA-ES: 29/30 (96.7%), Random: 21/30 (70.0%)
  - `P4_offset_place`: CMA-ES: 20/30 (66.7%), Random: 15/30 (50.0%)
  - `P5_good_policy`: CMA-ES: 24/30 (80.0%), Random: 17/30 (56.7%)
  - Total failures across 150 trials/arm: **CMA-ES 133 / 150 (88.7%) vs Random 101 / 150 (67.3%)** (+21.4% improvement)
- **Sims to first failure:**
  - Observed: 1 to 5 trials across all programs.
  - Expected: >0 failures on known-weak programs (observed > 0 for all 5 programs).
- **API spend this phase (H5):**
  - Observed: **$0.00** (simulation-only, no LLM calls)
  - Phase budget cap: $3.00

## Human review (3 minimal counterexamples inspection)
1. **P1_very_weak (20N grip force; physical slip limit ~1.70 kg):**
   - Original failure: `x: -0.0321, y: 0.1084, yaw: -0.2239, mass: 2.9017, friction: 0.1694` (distance to nominal: 3.7967)
   - Minimized counterexample: `x: 0.0, y: 0.0, yaw: 0.0, mass: 1.7197, friction: 0.8` (distance to nominal: 1.6197, -57.3% distance)
   - Inspection: All 4 non-mass variables (`x, y, yaw, friction`) shrunk to exact nominal `(0, 0, 0, 0.8)`. Mass shrunk from 2.90 kg to 1.72 kg, cleanly isolating the slip boundary. Rerun still fails: `True`.
2. **P2_weak (35N grip force; physical slip limit ~2.97 kg):**
   - Original failure: `x: -0.1404, y: 0.0903, yaw: -0.4656, mass: 9.1294, friction: 0.6003` (distance to nominal: 9.9254)
   - Minimized counterexample: `x: 0.0, y: 0.0, yaw: 0.0, mass: 3.0628, friction: 0.8` (distance to nominal: 2.9628, -70.1% distance)
   - Inspection: All 4 irrelevant variables restored to exact nominal. Mass shrunk from 9.13 kg down to 3.06 kg. Rerun still fails: `True`.
3. **P5_good_policy (80N grip force; physical slip limit ~6.80 kg):**
   - Original failure: `x: 0.0609, y: 0.0443, yaw: -0.0462, mass: 8.0965, friction: 0.5758` (distance to nominal: 8.3721)
   - Minimized counterexample: `x: 0.0, y: 0.0, yaw: 0.0, mass: 6.8471, friction: 0.8` (distance to nominal: 6.7471, -19.4% distance)
   - Inspection: Irrelevant perturbations zeroed out; mass shrunk to 6.85 kg. Rerun still fails: `True`.

## Surprises and open questions
- **Surprises:**
  - Coordinate-wise minimization with bisection isolated the single active failure parameter with remarkable precision: for policies with 20N, 35N, and 80N grip forces, the minimizer zeroed out all position/orientation/friction parameters and converged mass to 1.72 kg, 3.06 kg, and 6.85 kg, which match the theoretical physics slip limits ($F / (g \times 1.2)$) of 1.70 kg, 2.97 kg, and 6.80 kg within ~1-2%.
- **Open questions:** None.
