"""Pilot evaluation for Phase 05: Falsifier vs Random Search (V15).

Compares CMA-ES falsification vs uniform random search across 5 programs
with equal budget, logging episodes to runs/<run_id>/episodes.jsonl and
producing pilot table and minimized counterexamples.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.falsify.falsifier import falsify, FalsificationResult
from closedloop.falsify.minimizer import distance_to_nominal, minimize
from closedloop.sim.env import T1Env, PAD_POS, SimResult
from closedloop.sim import primitives as prim


def git_head() -> str:
    """Repo HEAD SHA; abort if unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"git unavailable: {exc}") from exc
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not sha:
        raise RuntimeError("cannot determine git HEAD")
    return sha


def make_policy(grip_force: float, offset: tuple[float, float] = (0.0, 0.0)) -> Callable[[T1Env, Any], None]:
    """Create parameterized pick-and-place policy."""
    def policy(env: T1Env, rng: Any) -> None:
        cube_pos, _ = prim.get_object_pose(env, "cube")
        above = (cube_pos[0], cube_pos[1], 0.15)
        prim.move_to(env, above, steps=40)
        prim.move_to(env, (cube_pos[0], cube_pos[1], cube_pos[2] + 0.03), steps=40)
        prim.close_gripper(env, grip_force)
        prim.move_to(env, above, steps=40)
        prim.move_to(
            env,
            (PAD_POS[0] + offset[0], PAD_POS[1] + offset[1], 0.15),
            steps=60,
        )
        prim.move_to(
            env,
            (PAD_POS[0] + offset[0], PAD_POS[1] + offset[1], 0.06),
            steps=40,
        )
        prim.open_gripper(env)
        prim.move_to(
            env,
            (PAD_POS[0] + offset[0], PAD_POS[1] + offset[1], 0.15),
            steps=40,
        )
    return policy


PILOT_PROGRAMS: dict[str, dict[str, Any]] = {
    "P1_very_weak": {
        "description": "Very weak grip (20N); slips for mass > 1.7kg",
        "grip_force": 20.0,
        "offset": (0.0, 0.0),
    },
    "P2_weak": {
        "description": "Weak grip (35N); slips for mass > 3.0kg",
        "grip_force": 35.0,
        "offset": (0.0, 0.0),
    },
    "P3_medium": {
        "description": "Medium grip (55N); slips for mass > 4.7kg",
        "grip_force": 55.0,
        "offset": (0.0, 0.0),
    },
    "P4_offset_place": {
        "description": "Medium-strong grip (70N) with small placement offset",
        "grip_force": 70.0,
        "offset": (0.015, -0.015),
    },
    "P5_good_policy": {
        "description": "Strong grip (80N); standard positive reference policy",
        "grip_force": 80.0,
        "offset": (0.0, 0.0),
    },
}


def run_falsify_pilot(
    run_id: str,
    *,
    config_path: str = "configs/falsify.yaml",
    runs_dir: str = "runs",
) -> dict[str, Any]:
    """Execute falsifier pilot comparing CMA-ES vs Random search on 5 programs."""
    cfg_file = ROOT / config_path
    if not cfg_file.exists():
        raise FileNotFoundError(f"Missing config: {cfg_file}")

    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run dir already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    log_path = run_dir / "episodes.jsonl"
    bounds_raw = cfg["bounds"]
    bounds = {k: tuple(v) for k, v in bounds_raw.items()}
    nominal = {k: float(v) for k, v in cfg["minimizer"]["nominal"].items()}
    budget = int(cfg.get("pilot", {}).get("budget", 30))
    base_seed = int(cfg.get("pilot", {}).get("seed", 20000))

    env = T1Env()
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    git_sha = git_head()
    cfg_hash = run_manifest.config_hash([cfg_file])

    summary_rows = []
    minimized_counterexamples = []
    used_seeds: list[int] = []

    print(f"=== Starting Phase 05 Pilot: {run_id} ===")
    print(f"Config: {config_path} (hash: {cfg_hash}), git: {git_sha[:8]}")
    print(f"Programs: 5, Budget per search: {budget} episodes\n")

    for idx, (prog_id, pinfo) in enumerate(PILOT_PROGRAMS.items()):
        policy = make_policy(pinfo["grip_force"], pinfo["offset"])
        prog_hash = hashlib.sha256(prog_id.encode()).hexdigest()[:16]

        print(f"Evaluating {prog_id}: {pinfo['description']}")

        # 1. CMA-ES falsification
        cmaes_seed = base_seed + idx * 500
        used_seeds.append(cmaes_seed)

        def eval_cmaes(sc: dict) -> SimResult:
            seed = int(sc.get("seed", cmaes_seed))
            res = env.run_episode(policy, sc, seed)
            rec = episode_log.EpisodeResult(
                episode_id=f"{prog_id}-cmaes-s{seed}",
                stream="repair",
                task="task_T1",
                program_id=prog_id,
                program_version=0,
                scenario=dict(sc),
                seed=seed,
                truth_success=res.truth_success,
                truth_success_alt=res.truth_success_alt,
                margin=res.margin,
                judge_mode="state",
                judge_pass=None,
                judge_confidence=None,
                trace_path="",
                frames_path=None,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                created_at=created_at,
            )
            episode_log.append_episode(log_path, rec)
            return res

        res_cmaes = falsify(eval_cmaes, bounds=bounds, budget=budget, seed=cmaes_seed, sampler_type="cmaes")
        sims_first_cmaes = (
            min(f["trial_index"] for f in res_cmaes.failures) + 1
            if res_cmaes.failures
            else None
        )

        # 2. Random search baseline
        rand_seed = base_seed + 10000 + idx * 500
        used_seeds.append(rand_seed)

        def eval_rand(sc: dict) -> SimResult:
            seed = int(sc.get("seed", rand_seed))
            res = env.run_episode(policy, sc, seed)
            rec = episode_log.EpisodeResult(
                episode_id=f"{prog_id}-rand-s{seed}",
                stream="repair",
                task="task_T1",
                program_id=prog_id,
                program_version=0,
                scenario=dict(sc),
                seed=seed,
                truth_success=res.truth_success,
                truth_success_alt=res.truth_success_alt,
                margin=res.margin,
                judge_mode="state",
                judge_pass=None,
                judge_confidence=None,
                trace_path="",
                frames_path=None,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                created_at=created_at,
            )
            episode_log.append_episode(log_path, rec)
            return res

        res_rand = falsify(eval_rand, bounds=bounds, budget=budget, seed=rand_seed, sampler_type="random")
        sims_first_rand = (
            min(f["trial_index"] for f in res_rand.failures) + 1
            if res_rand.failures
            else None
        )

        # 3. Minimization of best counterexample (if any failure found)
        minimized_info = None
        if res_cmaes.failures:
            best_fail = res_cmaes.failures[0]["scenario"]
            eval_min = lambda sc: env.run_episode(policy, sc, int(sc.get("seed", cmaes_seed)))
            shrunk = minimize(best_fail, eval_fn=eval_min, nominal=nominal)
            recheck = eval_min(shrunk)
            d_init = distance_to_nominal(best_fail, nominal)
            d_shrunk = distance_to_nominal(shrunk, nominal)
            minimized_info = {
                "program_id": prog_id,
                "original_scenario": {k: round(best_fail[k], 4) for k in bounds},
                "minimized_scenario": {k: round(shrunk[k], 4) for k in bounds},
                "distance_initial": round(d_init, 4),
                "distance_shrunk": round(d_shrunk, 4),
                "reduction_pct": round(100.0 * (1.0 - d_shrunk / max(d_init, 1e-6)), 1),
                "recheck_still_fails": not recheck.truth_success,
            }
            minimized_counterexamples.append(minimized_info)

        row = {
            "program_id": prog_id,
            "cmaes_sims_to_first": sims_first_cmaes,
            "rand_sims_to_first": sims_first_rand,
            "cmaes_failures": len(res_cmaes.failures),
            "rand_failures": len(res_rand.failures),
            "cmaes_min_margin": round(res_cmaes.best_margin, 4),
            "rand_min_margin": round(res_rand.best_margin, 4),
            "minimized": minimized_info is not None,
            "minimized_still_fails": (
                minimized_info["recheck_still_fails"] if minimized_info else None
            ),
        }
        summary_rows.append(row)
        print(f"  -> CMA-ES first failure: {sims_first_cmaes}/{budget} (failures: {len(res_cmaes.failures)}, min_margin: {res_cmaes.best_margin:.3f})")
        print(f"  -> Random first failure: {sims_first_rand}/{budget} (failures: {len(res_rand.failures)}, min_margin: {res_rand.best_margin:.3f})")
        if minimized_info:
            print(f"  -> Minimized dist: {minimized_info['distance_initial']} -> {minimized_info['distance_shrunk']} (still fails: {minimized_info['recheck_still_fails']})\n")

    env.close()

    manifest = run_manifest.build_manifest(
        run_id=run_id,
        git_sha=git_sha,
        config_hash=cfg_hash,
        model="none (physics simulation)",
        pricing={},
        budget_cap_usd=0.0,
        episodes_planned=budget * 2 * len(PILOT_PROGRAMS),
        seeds=used_seeds,
        generation={"falsifier": "CmaEsSampler", "minimizer": "coordinate_bisection"},
        created_at=created_at,
        status="valid",
    )
    run_manifest.write_manifest(run_dir, manifest)

    pilot_results = {
        "run_id": run_id,
        "created_at": created_at,
        "config_hash": cfg_hash,
        "git_sha": git_sha,
        "summary": summary_rows,
        "minimized_counterexamples": minimized_counterexamples,
    }
    (run_dir / "pilot_table.json").write_text(json.dumps(pilot_results, indent=2))

    return pilot_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 05 falsifier pilot")
    parser.add_argument("--run-id", default="falsify-pilot-01", help="Run ID")
    parser.add_argument("--config", default="configs/falsify.yaml", help="Config file")
    args = parser.parse_args()
    results = run_falsify_pilot(args.run_id, config_path=args.config)
    print("Pilot completed successfully.")
