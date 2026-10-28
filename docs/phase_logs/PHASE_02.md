# Phase 02 plan (5 lines)
1. Tests first: `tests/test_sampler.py` (V4) + `tests/test_sim.py` (V1/V2/V8/margin) failing on empty modules.
2. `closedloop/data/sampler.py`: three seed streams + `LeakageError`; `configs/tasks.yaml` (T1 tiers).
3. `closedloop/sim/env.py` + `primitives.py`: PyBullet DIRECT, T1 pick-place, scripted-episode smoke.
4. `closedloop/sim/predicates.py`: dual predicates + signed margin; V2 negative controls.
5. Determinism hash + eps/sec benchmark (+ grasp time-box note), `make gate` steps, final reply.
