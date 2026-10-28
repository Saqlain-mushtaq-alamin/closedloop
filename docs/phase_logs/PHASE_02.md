# Phase 02 plan (5 lines)
1. Tests first: `tests/test_sampler.py` (V4) + `tests/test_sim.py` (V1/V2/V8/margin) failing on empty modules.
2. `closedloop/data/sampler.py`: three seed streams + `LeakageError`; `configs/tasks.yaml` (T1 tiers).
3. `closedloop/sim/env.py` + `primitives.py`: PyBullet DIRECT, T1 pick-place, scripted-episode smoke.
4. `closedloop/sim/predicates.py`: dual predicates + signed margin; V2 negative controls.
5. Determinism hash + eps/sec benchmark (+ grasp time-box note), `make gate` steps, final reply.

## Blocker (2026-10-28): PyBullet uninstallable in sandbox
- `pip install pybullet` fetches sdist 3.2.7 (80MB); source build fails on
  Python 3.14. `--only-binary` finds no wheels: 3.2.7 ships Linux wheels for
  cp36-cp311 only (verified full file list), plus sdist. No cp312+ anywhere.
- License verified zlib/libpng (permissive, H3-clean). requires_python: none.
- Consequence: Tasks 2-4 (env, predicates, determinism/benchmark) need a
  running simulator and CANNOT be built or verified in this sandbox.
- Windows outlook (human must check): no win_amd64 wheels for 3.2.6/3.2.7, so
  `pip install pybullet==3.2.7` on 3.11.9 builds the 80MB sdist from source
  (needs MSVC C++ compiler; 10-30 min). STOPPING here per H17/STOP rules.
