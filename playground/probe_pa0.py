"""PA0 Feasibility Probe: Measure episode reproduction, throughput, and frame rendering."""

from __future__ import annotations

import concurrent.futures
import json
import math
import multiprocessing as mp
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pybullet as p
from closedloop.judge.judge import render_judge_frame
from closedloop.sim.env import T1Env


def load_episodes(n: int = 20) -> list[dict]:
    ep_file = ROOT / "runs" / "cert-full-01" / "episodes.jsonl"
    episodes = []
    with open(ep_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))
            if len(episodes) == n:
                break
    return episodes


def load_policy():
    prog_file = ROOT / "runs" / "cert-mint-03" / "program_final.py"
    code = prog_file.read_text(encoding="utf-8")
    ns = {}
    exec(code, ns)
    return ns["policy"]


def run_worker_episodes(episodes: list[dict]) -> list[dict]:
    policy = load_policy()
    env = T1Env()
    out = []
    for ep in episodes:
        t0 = time.perf_counter()
        env.reset(ep["scenario"])
        rng = np.random.default_rng(ep["seed"])
        res = env.run_policy(policy, rng)
        elapsed = time.perf_counter() - t0
        out.append({
            "episode_id": ep["episode_id"],
            "seed": ep["seed"],
            "logged_truth": ep["truth_success"],
            "actual_truth": res.truth_success,
            "truth_match": ep["truth_success"] == res.truth_success,
            "logged_margin": ep["margin"],
            "actual_margin": res.margin,
            "margin_diff": abs(ep["margin"] - res.margin),
            "elapsed_s": elapsed,
        })
    env.close()
    return out


def main():
    episodes_20 = load_episodes(20)
    print(f"Loaded {len(episodes_20)} episodes from runs/cert-full-01/episodes.jsonl")

    # 1. 20-episode reproduction
    print("\n--- 1. 20-Episode Reproduction Check ---")
    t0 = time.perf_counter()
    results_20 = run_worker_episodes(episodes_20)
    total_1w_time = time.perf_counter() - t0

    truth_matches = sum(1 for r in results_20 if r["truth_match"])
    margin_matches = sum(1 for r in results_20 if r["margin_diff"] <= 1e-6)
    eps_1w = len(results_20) / total_1w_time

    print(f"Truth Success Matches: {truth_matches}/20 ({truth_matches / 20 * 100:.1f}%)")
    print(f"Margin Matches (<= 1e-6): {margin_matches}/20 ({margin_matches / 20 * 100:.1f}%)")
    max_diff = max(r["margin_diff"] for r in results_20)
    print(f"Max Margin Difference: {max_diff:.8e}")
    print(f"1 Worker Time: {total_1w_time:.3f}s -> Throughput: {eps_1w:.2f} eps/sec")

    for i, r in enumerate(results_20):
        print(f"  [{i:02d}] {r['episode_id']}: truth={r['actual_truth']} (match={r['truth_match']}), "
              f"margin_diff={r['margin_diff']:.2e}, time={r['elapsed_s']*1000:.1f}ms")

    # 2. Multi-worker throughput (2 workers)
    print("\n--- 2. Multi-Worker Throughput (2 workers) ---")
    episodes_40 = load_episodes(40)
    if len(episodes_40) < 40:
        episodes_40 = episodes_20 * 2

    chunk1 = episodes_40[:20]
    chunk2 = episodes_40[20:40]

    t0 = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_worker_episodes, chunk1)
        f2 = executor.submit(run_worker_episodes, chunk2)
        res1 = f1.result()
        res2 = f2.result()
    total_2w_time = time.perf_counter() - t0
    eps_2w = (len(res1) + len(res2)) / total_2w_time
    print(f"2 Workers (40 episodes): {total_2w_time:.3f}s -> Throughput: {eps_2w:.2f} eps/sec")

    # 3. Frame rendering benchmark (192x144, Plan §10)
    print("\n--- 3. Frame Rendering Benchmark (192x144) ---")
    env = T1Env()
    policy = load_policy()
    env.reset(episodes_20[0]["scenario"])
    render_times = []
    for _ in range(30):
        t0 = time.perf_counter()
        rgba, _ = render_judge_frame(env, {"width": 192, "height": 144})
        render_times.append(time.perf_counter() - t0)
    env.close()

    avg_render_ms = np.mean(render_times) * 1000
    p95_render_ms = np.percentile(render_times, 95) * 1000
    print(f"Average render time per 192x144 frame: {avg_render_ms:.2f} ms")
    print(f"p95 render time per 192x144 frame: {p95_render_ms:.2f} ms")
    print(f"Frames per second capacity: {1000.0 / avg_render_ms:.1f} fps")

    output_data = {
        "truth_matches": truth_matches,
        "margin_matches": margin_matches,
        "max_diff": max_diff,
        "eps_1_worker": eps_1w,
        "eps_2_workers": eps_2w,
        "avg_frame_render_ms": avg_render_ms,
        "p95_frame_render_ms": p95_render_ms,
        "results_20": results_20,
    }

    out_file = ROOT / "playground" / "pa0_measurements.json"
    out_file.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"\nSaved measurements to {out_file}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
