"""G0 pilot orchestration: generate once, run N tier-1 episodes, log all.

Test seams: generate_fn supplies (policy_code, generation_record) and
execute_fn maps (scenario, seed, policy_code) to ("sim", result_dict) or
("infra", info_dict). The real execute path (runner + trusted preamble +
physics) runs only on a simulator machine; failures of every kind become
logged episode failures, never silent passes.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from closedloop.data import log as episode_log
from closedloop.data import manifest as run_manifest
from closedloop.data.sampler import sample
from closedloop.exec import episode as episode_mod
from closedloop.exec import runner as sandbox
from closedloop.gen.generator import InvalidProgram

G0_THRESHOLD = 0.30
RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


class PilotAbort(RuntimeError):
    """Configuration/run setup problem: nothing valid to measure."""


class PilotInvalid(RuntimeError):
    """The run is recorded but invalid (e.g. generation failed): no rate."""


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def execute_episode(scenario: dict, seed: int, policy_code: str, *,
                    repo_root: str, timeout_s: float,
                    memory_mb: int) -> tuple[str, dict]:
    """Real episode path: sandboxed trusted preamble + policy, checked data.

    Returns ("sim", result_dict) or ("infra", info_dict). Runner-level
    failure and malformed payloads both arrive as infra (episode failure).
    """
    code = episode_mod.build_episode_code(scenario, seed, policy_code, repo_root)
    outcome = sandbox.run_program(
        code, {}, timeout_s=timeout_s, memory_mb=memory_mb,
        allow_modules=episode_mod.ALLOW_MODULES,
    )
    if not outcome.ok:
        return ("infra", {"reason": outcome.reason, "detail": outcome.detail})
    try:
        return ("sim", episode_mod.check_result(outcome.data))
    except episode_mod.EpisodeError as exc:
        return ("infra", {"reason": "malformed_result", "detail": str(exc)})


def _episode_record(run_id: str, index: int, scenario: dict, seed: int,
                    program_id: str, kind: str, payload: dict,
                    created_at: str) -> tuple[dict, dict]:
    """Assemble (EpisodeResult kwargs, trace-file content) for one episode."""
    trace_name = f"traces/{index:03d}.json"
    base = dict(
        episode_id=f"{run_id}-{index:03d}", stream="repair", task="T1",
        program_id=program_id, program_version=0,
        scenario=dict(scenario), seed=seed, judge_mode="state",
        judge_pass=None, judge_confidence=None, trace_path=trace_name,
        frames_path=None, tokens_in=0, tokens_out=0, cost_usd=0.0,
        created_at=created_at,
    )
    if kind == "sim":
        base.update(truth_success=bool(payload["truth_success"]),
                    truth_success_alt=bool(payload["truth_success_alt"]),
                    margin=float(payload["margin"]))
        trace_content = {"trace": payload["trace"], "steps": payload["steps"],
                         "final_pos": list(payload["final_pos"])}
    else:
        base.update(truth_success=False, truth_success_alt=False, margin=-1.0)
        trace_content = {"outcome": payload.get("reason"),
                         "detail": str(payload.get("detail", ""))[-1500:]}
    return base, trace_content


def run_pilot(run_id: str, *, runs_dir: str, gen: dict, pricing: dict,
              budget_cap: float, generate_fn, execute_fn, git_sha: str,
              config_hash: str, created_at: str, repo_root: str) -> dict:
    """Run the pilot. Returns summary; raises PilotAbort/PilotInvalid."""
    if not RUN_ID_RE.fullmatch(run_id or ""):
        raise PilotAbort(f"unsafe run_id: {run_id!r}")
    for key in ("model", "episodes", "seed", "timeout_s", "memory_mb",
                "max_output_tokens"):
        if key not in gen:
            raise PilotAbort(f"gen config lacks {key}")
    episodes = int(gen["episodes"])
    if episodes <= 0 or int(gen["tier"]) != 1:
        raise PilotAbort(f"bad pilot shape: {gen!r}")
    run_dir = Path(runs_dir) / run_id
    if run_dir.exists():
        raise PilotAbort(f"run dir exists, refusing overwrite: {run_dir}")
    run_dir.mkdir(parents=True)
    (run_dir / "traces").mkdir(exist_ok=True)
    log_path = run_dir / "episodes.jsonl"
    try:
        policy_code, gen_record = generate_fn()
    except InvalidProgram as exc:
        manifest = run_manifest.build_manifest(
            run_id=run_id, git_sha=git_sha, config_hash=config_hash,
            model=gen["model"],
            pricing=pricing, budget_cap_usd=budget_cap, episodes_planned=episodes,
            seeds=[], generation={"error": str(exc)}, created_at=created_at,
            status="invalid_generation")
        run_manifest.write_manifest(run_dir, manifest)
        raise PilotInvalid(f"generation failed: {exc}") from exc
    program_id = hashlib.sha256(policy_code.encode()).hexdigest()[:16]
    scenarios = sample("repair", episodes, int(gen["seed"]))
    infra_errors = 0
    for index, scenario in enumerate(scenarios):
        seed = int(scenario["seed"])
        kind, payload = execute_fn(scenario, seed, policy_code)
        if kind != "sim":
            infra_errors += 1
        record, trace_content = _episode_record(
            run_id, index, scenario, seed, program_id, kind, payload, created_at)
        (run_dir / trace_content_path(record)).write_text(json.dumps(trace_content))
        episode_log.append_episode(
            log_path, episode_log.EpisodeResult(**record))
    manifest = run_manifest.build_manifest(
        run_id=run_id, git_sha=git_sha, config_hash=config_hash,
        model=gen["model"],
        pricing=pricing, budget_cap_usd=budget_cap,
        episodes_planned=episodes,
        seeds=[int(s["seed"]) for s in scenarios],
        generation=gen_record, created_at=created_at, status="valid")
    manifest["infra_errors"] = infra_errors
    run_manifest.write_manifest(run_dir, manifest)
    summary = episode_log.summarize_run(run_dir)
    return {"run_id": run_id, "n": summary["n"], "k": summary["k"],
            "rate": summary["rate"], "cost_usd": gen_record.get("cost_usd", 0.0),
            "status": "valid"}


def trace_content_path(record: dict) -> str:
    """Relative trace path stored on the record (portable across machines)."""
    return str(record["trace_path"])
