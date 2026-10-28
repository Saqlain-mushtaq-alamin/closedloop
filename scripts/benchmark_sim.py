#!/usr/bin/env python3
"""Time scripted T1 episodes for the Phase 02 log (not a test).

Usage: python scripts/benchmark_sim.py [N]  (run from the repo root)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from closedloop.data.sampler import sample  # noqa: E402
from closedloop.sim.env import T1Env, good_policy  # noqa: E402


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    scenarios = sample("repair", n, 4242)
    env = T1Env()
    try:
        start = time.perf_counter()
        steps = 0
        for sc in scenarios:
            res = env.run_episode(good_policy, sc, seed=int(sc["seed"]))
            steps += res.steps
        dt = time.perf_counter() - start
    finally:
        env.close()
    print(f"episodes={n} steps={steps} seconds={dt:.1f} eps_per_sec={n / dt:.2f}")


if __name__ == "__main__":
    main()
