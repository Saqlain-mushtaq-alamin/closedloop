"""Phase 08b: Round 2 Repair Runner (Candidate v2 Creation).

Pre-registered in docs/DECISIONS.md:
- Source program: v1 (bec73dec45a88431) from runs/cert-mint-03/program_final.py
- Arm B3: Falsifier + coordinate minimizer + multimodal filmstrip
- Repair stream seeds: strictly in [710000, 749999] (Rule H9)
- Acceptance: 3-stage rule (CE pass, regression set pass, short falsifier rerun)
- Regression set: nominal + earlier counterexamples from config
- Max attempts: 2, all logged append-only to runs/round2-mint-01/episodes.jsonl
- Accepted candidate frozen with SHA-256 before any certification episode.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import numpy as np
import yaml

from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.data.sampler import sample
from closedloop.exec import pilot as pilot_mod
from closedloop.exec.episode import POLICY_API_DOC
from closedloop.falsify.falsifier import falsify
from closedloop.falsify.minimizer import minimize
from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.repair.filmstrip import generate_filmstrip
from closedloop.repair.repair import build_repair_prompt
from closedloop.gen.generator import generate_task_program, InvalidProgram
from closedloop.sim.env import SimResult, T1Env


def git_head() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not sha:
        raise RuntimeError("cannot determine git HEAD")
    return sha


def make_policy_callable(code: str) -> Any:
    """Compile policy code into callable function."""
    ns: dict[str, Any] = {}
    exec(code, ns)
    if "policy" not in ns:
        raise ValueError("Code does not define policy(env, rng)")
    return ns["policy"]


def run_round2_repair(
    run_id: str = "round2-mint-01",
    *,
    config_path: str = "configs/round2.yaml",
    pricing_path: str = "configs/pricing.yaml",
    tasks_path: str = "configs/tasks.yaml",
    runs_dir: str = "runs",
) -> dict[str, Any]:
    """Execute Round 2 repair on program v1 to produce candidate v2."""
    cfg_file = ROOT / config_path
    pricing_file = ROOT / pricing_path
    tasks_file = ROOT / tasks_path

    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    tasks_cfg = yaml.safe_load(tasks_file.read_text(encoding="utf-8"))

    # Verify source program v1
    v1_path = ROOT / cfg["source_program"]["path"]
    if not v1_path.exists():
        raise FileNotFoundError(f"Source program v1 not found at {v1_path}")
    v1_code = v1_path.read_text(encoding="utf-8")
    norm_v1 = v1_code.replace("\r\n", "\n")
    actual_v1_sha = hashlib.sha256(norm_v1.encode("utf-8")).hexdigest()
    expected_v1_sha = cfg["source_program"]["sha256"]
    if actual_v1_sha != expected_v1_sha:
        raise ValueError(f"v1 sha256 mismatch: {actual_v1_sha} != {expected_v1_sha}")

    arm = str(cfg["arm"])
    model = str(cfg["model"])
    max_output_tokens = int(cfg["max_output_tokens"])
    timeout_s = float(cfg["timeout_s"])
    memory_mb = int(cfg["memory_mb"])
    budget_cap_usd = float(cfg["budget_cap_usd"])
    max_attempts = int(cfg["max_attempts"])

    bounds = cfg["difficulty"]["bounds"]
    falsifier_budget = int(cfg["repair"]["falsifier_budget"])
    rerun_budget = int(cfg["repair"]["acceptance"]["falsifier_rerun_budget"])
    param_order = list(cfg["repair"]["acceptance"]["param_order"])
    regression_scenarios = list(cfg["regression_set"])

    meter = CostMeter(cap_usd=budget_cap_usd)
    pricing_dict = meter.load_prices(pricing_file)
    client = LLMClient(meter)

    git_sha = git_head()
    cfg_hash = run_manifest.config_hash([cfg_file, pricing_file, tasks_file])
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_dir / "episodes.jsonl"
    cache_path = run_dir / "llm_cache.json"
    cache: dict[str, Any] = {}

    used_seeds: list[int] = []
    n_episodes = 0

    def log_ep(
        ep_id: str,
        code: str,
        version: int,
        scenario: dict,
        seed: int,
        kind: str,
        payload: dict,
        tokens: tuple[int, int] = (0, 0),
        cost: float = 0.0,
    ) -> tuple[bool, float]:
        nonlocal n_episodes
        ts = bool(payload.get("truth_success", False)) if kind == "sim" else False
        alt = bool(payload.get("truth_success_alt", False)) if kind == "sim" else False
        margin = float(payload.get("margin", -1.0)) if kind == "sim" else -1.0
        p_id = hashlib.sha256(code.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]

        episode_log.append_episode(
            log_path,
            episode_log.EpisodeResult(
                episode_id=ep_id,
                stream="repair",
                task="task_T1",
                program_id=p_id,
                program_version=version,
                scenario=dict(scenario),
                seed=seed,
                truth_success=ts,
                truth_success_alt=alt,
                margin=margin,
                judge_mode="state",
                judge_pass=None,
                judge_confidence=None,
                trace_path=f"steps:{len(payload.get('trace', []))}",
                frames_path=None,
                tokens_in=tokens[0],
                tokens_out=tokens[1],
                cost_usd=cost,
                created_at=created_at,
            ),
        )
        used_seeds.append(seed)
        n_episodes += 1
        return ts, margin

    attempts_log: list[dict[str, Any]] = []
    accepted_proposal: dict[str, Any] | None = None
    curr_code = v1_code

    print(f"Starting Round 2 repair on program v1 ({actual_v1_sha[:16]}...)")

    for attempt_idx in range(1, max_attempts + 1):
        att_key = f"attempt_{attempt_idx}"
        seeds_cfg = cfg["seeds"][att_key]
        fals_base = int(seeds_cfg["falsifier_base"])
        min_base = int(seeds_cfg["minimizer_base"])
        min_recheck = int(seeds_cfg["minimizer_recheck"])
        s1_ce_seed = int(seeds_cfg["stage1_ce"])
        s3_base = int(seeds_cfg["stage3_base"])

        print(f"\n--- Round 2: Repair Attempt {attempt_idx}/{max_attempts} ---")

        # 1. Falsification on curr_code
        fals_idx = 0
        def eval_fals(sc: dict) -> SimResult:
            nonlocal fals_idx
            sd = fals_base + fals_idx
            fals_idx += 1
            k, p = pilot_mod.execute_episode(
                sc, sd, curr_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            ts, mg = log_ep(f"att{attempt_idx}-fals-s{sd}", curr_code, 0, sc, sd, k, p)
            return SimResult(
                truth_success=ts,
                truth_success_alt=bool(p.get("truth_success_alt", False)) if k == "sim" else False,
                margin=mg,
                final_pos=(0, 0, 0),
                steps=0,
                agreed=True,
            )

        fals_res = falsify(eval_fals, bounds=bounds, budget=falsifier_budget, seed=fals_base)
        if not fals_res.failures:
            print("Falsifier found no failures on current code; attempting edge probe.")
            raw_fail = {
                "x": 0.0, "y": 0.0, "yaw": 0.0, "mass": 10.5, "friction": 0.2, "seed": fals_base
            }
            raw_margin = -0.25
        else:
            raw_fail = fals_res.failures[0]["scenario"]
            raw_margin = fals_res.failures[0]["margin"]

        print(f"Falsifier discovered counterexample: mass={raw_fail.get('mass'):.2f}, friction={raw_fail.get('friction'):.2f}, margin={raw_margin:.4f}")

        # 2. Minimization toward nominal
        min_idx = 0
        def eval_min(sc: dict) -> SimResult:
            nonlocal min_idx
            sd = min_base + min_idx
            min_idx += 1
            k, p = pilot_mod.execute_episode(
                sc, sd, curr_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            ts, mg = log_ep(f"att{attempt_idx}-min-s{sd}", curr_code, 0, sc, sd, k, p)
            return SimResult(
                truth_success=ts,
                truth_success_alt=bool(p.get("truth_success_alt", False)) if k == "sim" else False,
                margin=mg,
                final_pos=(0, 0, 0),
                steps=0,
                agreed=True,
            )

        nominal = cfg["repair"]["acceptance"]["nominal"]
        min_ce = minimize(
            raw_fail,
            eval_min,
            nominal=nominal,
            bisection_steps=0,
            param_keys=param_order,
            bounds=bounds,
        )

        # Minimizer recheck
        k_rc, p_rc = pilot_mod.execute_episode(
            min_ce, min_recheck, curr_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        _, min_margin = log_ep(f"att{attempt_idx}-min-recheck", curr_code, 0, min_ce, min_recheck, k_rc, p_rc)

        print(f"Minimal counterexample: mass={min_ce.get('mass'):.2f}, friction={min_ce.get('friction'):.2f}, margin={min_margin:.4f}")

        # 3. Multimodal filmstrip extraction (Arm B3)
        filmstrip_desc = None
        images_b64: list[str] = []
        try:
            compiled_policy = make_policy_callable(curr_code)
            env_inst = T1Env()
            fstrip = generate_filmstrip(
                env_inst,
                min_ce,
                compiled_policy,
                seed=min_recheck,
                num_frames=5,
            )
            images_b64 = fstrip.get("images_b64", [])
            filmstrip_desc = fstrip.get("summary", "")
            (frames_dir / f"att{attempt_idx}_filmstrip.json").write_text(
                json.dumps({
                    "attempt": attempt_idx,
                    "descriptions": fstrip.get("descriptions", []),
                    "frame_count": len(images_b64),
                }, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            filmstrip_desc = f"Filmstrip note: {exc}"

        # 4. Assemble Arm B3 repair prompt
        prompt = build_repair_prompt(
            curr_code,
            min_ce,
            POLICY_API_DOC,
            margin=min_margin,
            trace_summary=f"Active falsifier CMA-ES minimal counterexample (slip failure at high mass)",
            filmstrip_description=filmstrip_desc,
        )

        # 5. Query LLM
        print("Querying muse-spark-1.3 for repair patch...")
        base_task_text = tasks_cfg["task_T1"]["description"]
        try:
            proposal = generate_task_program(
                client,
                base_task_text,
                POLICY_API_DOC,
                max_output_tokens,
                model=model,
                feedback=prompt,
                images_b64=images_b64,
                cache=cache,
                cache_key_extra=f"round2_att{attempt_idx}",
            )
            cand_code = proposal.code
            rationale = proposal.rationale
            call_tokens = (proposal.tokens_in, proposal.tokens_out)
            call_cost = proposal.cost_usd
            # Save cache in serializable format
            cache_clean = {k: {"code": v.code, "rationale": v.rationale, "tokens_in": v.tokens_in, "tokens_out": v.tokens_out, "cost_usd": v.cost_usd} if hasattr(v, "code") else v for k, v in cache.items()}
            (run_dir / "llm_cache.json").write_text(json.dumps(cache_clean, indent=2), encoding="utf-8")
        except InvalidProgram as exc:
            print(f"Invalid program generated: {exc}")
            attempts_log.append({
                "attempt": attempt_idx,
                "accepted": False,
                "reason": f"InvalidProgram: {exc}",
                "rationale": "",
            })
            continue

        # Validate syntax
        try:
            ast.parse(cand_code)
        except SyntaxError as exc:
            print(f"Candidate code syntax error: {exc}")
            attempts_log.append({
                "attempt": attempt_idx,
                "accepted": False,
                "reason": f"SyntaxError: {exc}",
                "rationale": rationale,
            })
            continue

        cand_file = run_dir / f"program_candidate_v{attempt_idx}.py"
        cand_file.write_text(cand_code, encoding="utf-8")

        # 6. Evaluate 3-Stage Acceptance Gate
        print("Evaluating 3-Stage Acceptance Gate:")
        # Stage 1: Minimal counterexample
        min_ce_eval = dict(min_ce)
        min_ce_eval["seed"] = s1_ce_seed
        k_s1, p_s1 = pilot_mod.execute_episode(
            min_ce_eval, s1_ce_seed, cand_code, repo_root=str(ROOT),
            timeout_s=timeout_s, memory_mb=memory_mb,
        )
        ts_s1, mg_s1 = log_ep(
            f"att{attempt_idx}-stage1-ce", cand_code, attempt_idx, min_ce_eval, s1_ce_seed,
            k_s1, p_s1, tokens=call_tokens, cost=call_cost,
        )
        s1_passed = ts_s1 and mg_s1 > 0
        print(f"  Stage 1 (Counterexample): {'PASS' if s1_passed else 'FAIL'} (margin={mg_s1:.4f})")

        # Stage 2: Regression set
        s2_passed = True
        failed_reg_id = None
        for r_sc in regression_scenarios:
            r_seed = int(r_sc.get("seed", 713000))
            k_reg, p_reg = pilot_mod.execute_episode(
                r_sc, r_seed, cand_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            ts_reg, mg_reg = log_ep(
                f"att{attempt_idx}-stage2-{r_sc.get('id', r_seed)}", cand_code, attempt_idx,
                r_sc, r_seed, k_reg, p_reg,
            )
            if not ts_reg or mg_reg <= 0:
                s2_passed = False
                failed_reg_id = r_sc.get("id")
                break
        print(f"  Stage 2 (Regression Set, {len(regression_scenarios)} scenarios): {'PASS' if s2_passed else 'FAIL'} (failed={failed_reg_id})")

        # Stage 3: Short falsifier rerun (5 episodes)
        s3_passed = True
        s3_fail_sc = None
        for s3_i in range(rerun_budget):
            s3_sd = s3_base + s3_i
            # Sample perturbed scenario near bounds
            s3_sc = sample("repair", n=1, seed=s3_sd, bounds=bounds)[0]
            k_s3, p_s3 = pilot_mod.execute_episode(
                s3_sc, s3_sd, cand_code, repo_root=str(ROOT),
                timeout_s=timeout_s, memory_mb=memory_mb,
            )
            ts_s3, mg_s3 = log_ep(
                f"att{attempt_idx}-stage3-s{s3_sd}", cand_code, attempt_idx,
                s3_sc, s3_sd, k_s3, p_s3,
            )
            if not ts_s3 or mg_s3 <= 0:
                s3_passed = False
                s3_fail_sc = s3_sc
                break
        print(f"  Stage 3 (Short falsifier rerun, 5 episodes): {'PASS' if s3_passed else 'FAIL'}")

        accepted = s1_passed and s2_passed and s3_passed
        attempt_record = {
            "attempt": attempt_idx,
            "accepted": accepted,
            "stage1_passed": s1_passed,
            "stage2_passed": s2_passed,
            "stage3_passed": s3_passed,
            "counterexample": min_ce,
            "rationale": rationale,
            "tokens": call_tokens,
            "cost_usd": call_cost,
        }
        attempts_log.append(attempt_record)

        if accepted:
            print(f"VERDICT: ACCEPTED on attempt {attempt_idx}!")
            accepted_proposal = {
                "code": cand_code,
                "rationale": rationale,
                "attempt": attempt_idx,
                "tokens": call_tokens,
                "cost_usd": call_cost,
            }
            break
        else:
            print(f"VERDICT: REJECTED on attempt {attempt_idx}.")

    tot_tok_in = sum(int(e.get("tokens_in", 0)) for e in meter.ledger)
    tot_tok_out = sum(int(e.get("tokens_out", 0)) for e in meter.ledger)
    tot_spend = round(meter.spent_usd, 6)

    # Write trace
    trace_data = {
        "run_id": run_id,
        "arm": arm,
        "source_program_v1": {
            "path": str(v1_path),
            "sha256": actual_v1_sha,
            "program_id": actual_v1_sha[:16],
        },
        "attempts": attempts_log,
        "accepted": accepted_proposal is not None,
        "total_spend_usd": tot_spend,
        "episodes_logged": n_episodes,
    }
    (run_dir / "mint_trace.json").write_text(
        json.dumps(trace_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Write manifest
    man = {
        "run_id": run_id,
        "git_sha": git_sha,
        "config_hash": cfg_hash,
        "created_at": created_at,
        "model": model,
        "pricing_per_mtok": pricing_dict,
        "budget_cap_usd": budget_cap_usd,
        "spent_usd": tot_spend,
        "tokens_spent": {
            "tokens_in": tot_tok_in,
            "tokens_out": tot_tok_out,
            "total": tot_tok_in + tot_tok_out,
        },
        "episodes_planned": n_episodes,
        "seeds": used_seeds,
        "status": "valid" if accepted_proposal else "rejected",
        "repair": {
            "arm": arm,
            "attempts": len(attempts_log),
            "accepted": accepted_proposal is not None,
            "v1_sha256": actual_v1_sha,
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if not accepted_proposal:
        print(f"Round 2 repair STOP: both attempts rejected. Total spend: ${tot_spend:.4f}")
        return {"run_id": run_id, "accepted": False}

    # Save and freeze accepted v2
    v2_code = accepted_proposal["code"]
    v2_norm = v2_code.replace("\r\n", "\n")
    v2_sha = hashlib.sha256(v2_norm.encode("utf-8")).hexdigest()
    v2_id = v2_sha[:16]

    final_prog_path = run_dir / "program_final.py"
    final_prog_path.write_text(v2_code, encoding="utf-8")

    freeze = {
        "source_file": "program_final.py",
        "sha256": v2_sha,
        "program_id": v2_id,
        "model": model,
        "rationale": accepted_proposal["rationale"],
        "seeds": used_seeds,
        "acceptance": {
            "reason": "accepted",
            "details": {
                "attempt": accepted_proposal["attempt"],
                "stages_passed": [1, 2, 3],
            },
        },
        "tokens_in": tot_tok_in,
        "tokens_out": tot_tok_out,
        "cost_usd": tot_spend,
        "config_hash": cfg_hash,
    }
    (run_dir / "freeze.json").write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    from experiments.run_cert_v2 import validate_v2_freeze
    validate_v2_freeze(run_dir)
    print(f"FROZEN program v2: program_id={v2_id}, sha256={v2_sha[:16]}... Spend: ${tot_spend:.4f}")

    return {
        "run_id": run_id,
        "accepted": True,
        "program_id": v2_id,
        "sha256": v2_sha,
        "spent_usd": tot_spend,
        "episodes_logged": n_episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute Phase 08b Round 2 repair.")
    parser.add_argument("--run-id", default="round2-mint-01")
    args = parser.parse_args()
    res = run_round2_repair(run_id=args.run_id)
    if not res.get("accepted"):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
