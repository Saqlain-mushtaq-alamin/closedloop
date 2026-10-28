"""Pilot evaluation for Phase 05: Falsifier vs Random Search (V15).

Compares CMA-ES falsification vs uniform random search across 5 programs
with equal budget, logging EVERY episode (search, minimizer shrinking steps,
and recheck) to runs/<run_id>/episodes.jsonl (H10). Includes an A/A control
and multi-seed evaluation.
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
from closedloop.falsify.falsifier import falsify
from closedloop.falsify.minimizer import distance_to_nominal, is_failing, minimize
from closedloop.sim.env import T1Env, PAD_POS, SimResult
from closedloop.sim import primitives as prim


def git_head() -> str:
    """Repo HEAD SHA; verify falsifier is present at this SHA."""
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

    # Verify falsifier exists at this commit or in working tree
    falsifier_path = ROOT / "closedloop" / "falsify" / "falsifier.py"
    if not falsifier_path.exists():
        raise RuntimeError(f"falsifier.py not found at {falsifier_path}")
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
    num_seeds_per_program: int = 3,
) -> dict[str, Any]:
    """Execute falsifier pilot comparing CMA-ES vs Random search across 5 programs.

    All episodes (search trials, minimizer shrinking steps, and verification rechecks)
    are logged to runs/<run_id>/episodes.jsonl (H10).
    """
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
    param_order = list(cfg["minimizer"].get("param_order", ["x", "y", "yaw", "friction", "mass"]))
    bisection_steps = int(cfg["minimizer"].get("bisection_steps", 6))
    budget = int(cfg.get("pilot", {}).get("budget", 30))
    base_seed = int(cfg.get("pilot", {}).get("seed", 20000))

    env = T1Env()
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    git_sha = git_head()
    cfg_hash = run_manifest.config_hash([cfg_file])

    summary_rows = []
    minimized_counterexamples = []
    used_seeds: list[int] = []
    total_episodes_logged = 0

    print(f"=== Starting Phase 05 Pilot: {run_id} ===")
    print(f"Config: {config_path} (hash: {cfg_hash}), git: {git_sha[:8]}")
    print(f"Programs: 5, Seeds/prog: {num_seeds_per_program}, Budget per trial: {budget} episodes\n")

    for p_idx, (prog_id, pinfo) in enumerate(PILOT_PROGRAMS.items()):
        policy = make_policy(pinfo["grip_force"], pinfo["offset"])

        cmaes_failures_total = 0
        rand_failures_total = 0
        aa_failures_total = 0
        cmaes_first_fails = []
        rand_first_fails = []
        cmaes_best_margin = 1e9
        rand_best_margin = 1e9
        best_overall_failure = None

        print(f"Evaluating {prog_id}: {pinfo['description']}")

        for s_idx in range(num_seeds_per_program):
            cmaes_seed = base_seed + p_idx * 2000 + s_idx * 200
            rand_seed = base_seed + 10000 + p_idx * 2000 + s_idx * 200
            aa_seed = base_seed + 20000 + p_idx * 2000 + s_idx * 200
            used_seeds.extend([cmaes_seed, rand_seed, aa_seed])

            # 1. CMA-ES falsification
            def eval_cmaes(sc: dict) -> SimResult:
                nonlocal total_episodes_logged
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
                total_episodes_logged += 1
                return res

            res_cmaes = falsify(eval_cmaes, bounds=bounds, budget=budget, seed=cmaes_seed, sampler_type="cmaes")
            cmaes_failures_total += len(res_cmaes.failures)
            if res_cmaes.failures:
                first_f = min(f["trial_index"] for f in res_cmaes.failures) + 1
                cmaes_first_fails.append(first_f)
                if res_cmaes.best_margin < cmaes_best_margin:
                    cmaes_best_margin = res_cmaes.best_margin
                    # Lowest margin failure as candidate for minimization
                    best_overall_failure = res_cmaes.failures[0]["scenario"]

            # 2. Random search baseline
            def eval_rand(sc: dict) -> SimResult:
                nonlocal total_episodes_logged
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
                total_episodes_logged += 1
                return res

            res_rand = falsify(eval_rand, bounds=bounds, budget=budget, seed=rand_seed, sampler_type="random")
            rand_failures_total += len(res_rand.failures)
            if res_rand.failures:
                first_r = min(f["trial_index"] for f in res_rand.failures) + 1
                rand_first_fails.append(first_r)
                if res_rand.best_margin < rand_best_margin:
                    rand_best_margin = res_rand.best_margin

            # 3. A/A Control: independent Random search Arm B (for null baseline verification)
            def eval_aa(sc: dict) -> SimResult:
                nonlocal total_episodes_logged
                seed = int(sc.get("seed", aa_seed))
                res = env.run_episode(policy, sc, seed)
                rec = episode_log.EpisodeResult(
                    episode_id=f"{prog_id}-randB-s{seed}",
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
                total_episodes_logged += 1
                return res

            res_aa = falsify(eval_aa, bounds=bounds, budget=budget, seed=aa_seed, sampler_type="random")
            aa_failures_total += len(res_aa.failures)

        # 4. Minimization of best counterexample (LOGGING ALL STEPS to episodes.jsonl)
        minimized_info = None
        if best_overall_failure is not None:
            min_step = 0

            def eval_min_logged(sc: dict) -> SimResult:
                nonlocal min_step, total_episodes_logged
                min_step += 1
                seed = base_seed + 30000 + p_idx * 500 + min_step
                used_seeds.append(seed)
                res = env.run_episode(policy, sc, seed)
                rec = episode_log.EpisodeResult(
                    episode_id=f"{prog_id}-minimize-step{min_step:02d}-s{seed}",
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
                total_episodes_logged += 1
                return res

            shrunk = minimize(
                best_overall_failure,
                eval_fn=eval_min_logged,
                nominal=nominal,
                bisection_steps=bisection_steps,
                param_keys=param_order,
                bounds=bounds,
            )
            # Recheck verification (also logged)
            recheck_res = eval_min_logged(shrunk)
            recheck_fails = is_failing(recheck_res)

            d_init = distance_to_nominal(best_overall_failure, nominal)
            d_shrunk = distance_to_nominal(shrunk, nominal)

            minimized_info = {
                "program_id": prog_id,
                "original_scenario": {k: round(best_overall_failure[k], 4) for k in bounds},
                "minimized_scenario": {k: round(shrunk[k], 4) for k in bounds},
                "distance_initial": round(d_init, 4),
                "distance_shrunk": round(d_shrunk, 4),
                "reduction_pct": round(100.0 * (1.0 - d_shrunk / max(d_init, 1e-6)), 1),
                "recheck_still_fails": recheck_fails,
                "minimizer_steps_logged": min_step,
            }
            minimized_counterexamples.append(minimized_info)

        total_trials = budget * num_seeds_per_program
        row = {
            "program_id": prog_id,
            "total_trials_per_arm": total_trials,
            "cmaes_failures": cmaes_failures_total,
            "rand_failures": rand_failures_total,
            "aa_failures": aa_failures_total,
            "cmaes_failure_rate": round(cmaes_failures_total / total_trials, 3),
            "rand_failure_rate": round(rand_failures_total / total_trials, 3),
            "aa_failure_rate": round(aa_failures_total / total_trials, 3),
            "cmaes_mean_sims_to_first": round(sum(cmaes_first_fails) / max(len(cmaes_first_fails), 1), 2),
            "rand_mean_sims_to_first": round(sum(rand_first_fails) / max(len(rand_first_fails), 1), 2),
            "cmaes_best_margin": round(cmaes_best_margin, 4) if cmaes_best_margin < 1e8 else None,
            "rand_best_margin": round(rand_best_margin, 4) if rand_best_margin < 1e8 else None,
            "minimized": minimized_info is not None,
            "minimized_still_fails": minimized_info["recheck_still_fails"] if minimized_info else None,
        }
        summary_rows.append(row)
        print(f"  -> CMA-ES failure rate: {cmaes_failures_total}/{total_trials} ({row['cmaes_failure_rate']:.1%}), min margin: {row['cmaes_best_margin']}")
        print(f"  -> Random failure rate: {rand_failures_total}/{total_trials} ({row['rand_failure_rate']:.1%}), min margin: {row['rand_best_margin']}")
        print(f"  -> A/A    failure rate: {aa_failures_total}/{total_trials} ({row['aa_failure_rate']:.1%})")
        if minimized_info:
            print(f"  -> Minimized: dist {minimized_info['distance_initial']} -> {minimized_info['distance_shrunk']} ({minimized_info['reduction_pct']}% reduction in {minimized_info['minimizer_steps_logged']} steps, still fails: {minimized_info['recheck_still_fails']})\n")

    env.close()

    manifest = run_manifest.build_manifest(
        run_id=run_id,
        git_sha=git_sha,
        config_hash=cfg_hash,
        model="none (physics simulation)",
        pricing={},
        budget_cap_usd=0.0,
        episodes_planned=total_episodes_logged,
        seeds=sorted(list(set(used_seeds))),
        generation={
            "falsifier": "CmaEsSampler",
            "minimizer": "coordinate_bisection",
            "seeds_per_program": num_seeds_per_program,
            "aa_control": "RandomSampler_ArmB",
        },
        created_at=created_at,
        status="valid",
    )
    run_manifest.write_manifest(run_dir, manifest)

    pilot_results = {
        "run_id": run_id,
        "created_at": created_at,
        "config_hash": cfg_hash,
        "git_sha": git_sha,
        "total_episodes_logged": total_episodes_logged,
        "summary": summary_rows,
        "minimized_counterexamples": minimized_counterexamples,
    }
    (run_dir / "pilot_table.json").write_text(json.dumps(pilot_results, indent=2))
    print(f"Pilot {run_id} complete. Logged {total_episodes_logged} total episodes to {log_path}.")

    return pilot_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 05 falsifier pilot")
    parser.add_argument("--run-id", default="falsify-pilot-03", help="Run ID")
    parser.add_argument("--config", default="configs/falsify.yaml", help="Config file")
    parser.add_argument("--seeds", type=int, default=3, help="Seeds per program")
    args = parser.parse_args()
    results = run_falsify_pilot(args.run_id, config_path=args.config, num_seeds_per_program=args.seeds)
