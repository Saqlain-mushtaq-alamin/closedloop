#!/usr/bin/env python3
"""Minimal G0 pilot: one generated program x N tier-1 repair episodes.

Writes runs/<run_id>/episodes.jsonl (+ traces/, manifest.json). Refuses an
existing run dir. Aborts BEFORE any spend when pricing is unverified or the
API key is missing. Exit 0 = valid run complete (rate printed vs G0 0.30);
exit 2 = aborted/invalid. Never edit a run directory by hand (H10/H12).

Usage (Windows, repo root, keyed env):
  .\\.venv\\Scripts\\python.exe scripts/run_g0_pilot.py --run-id g0-pilot-01
One-episode probe: temporarily set episodes: 1 in configs/gen.yaml (restore
after), then the same command with a fresh --run-id.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from closedloop.data import manifest as run_manifest  # noqa: E402
from closedloop.exec import pilot as pilot_mod  # noqa: E402
from closedloop.gen.generator import generate_task_program  # noqa: E402
from closedloop.llm.client import CODE_MODEL, LLMClient  # noqa: E402
from closedloop.llm.cost import BudgetExceeded, CostMeter, UnpricedModelError  # noqa: E402
from closedloop.exec.episode import POLICY_API_DOC  # noqa: E402

CACHE_PATH = ROOT / "runs" / "llm_cache.json"


def utcnow() -> str:
    """Current UTC timestamp (single clock for the run)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def git_head() -> str:
    """Repo HEAD SHA (H11 provenance); abort when unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        raise PilotAbortLocal(f"git unavailable: {exc}") from exc
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not sha:
        raise PilotAbortLocal("cannot determine git HEAD")
    return sha


class PilotAbortLocal(RuntimeError):
    """Local alias so helpers abort without importing pilot exceptions."""


def load_cache() -> dict:
    """Shared prompt-hash response cache (reruns must not respend)."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    """Persist the shared cache (best effort; spend safety first)."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (thin wiring; logic lives in testable functions)."""
    ap = argparse.ArgumentParser(description="Run the G0 pilot.")
    ap.add_argument("--run-id", required=True, help="fresh run identifier")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--configs", default=str(ROOT / "configs"))
    args = ap.parse_args(argv)
    configs = Path(args.configs)
    gen = yaml.safe_load((configs / "gen.yaml").read_text(encoding="utf-8"))
    tasks = yaml.safe_load((configs / "tasks.yaml").read_text(encoding="utf-8"))
    pricing_path = configs / "pricing.yaml"
    meter = CostMeter()
    try:
        pricing = meter.load_prices(pricing_path)
    except UnpricedModelError as exc:
        print(f"ABORTED (no spend): {exc}")
        return 2
    cfg_hash = run_manifest.config_hash(
        [configs / "gen.yaml", configs / "tasks.yaml", pricing_path])
    cache = load_cache()
    try:
        client = LLMClient(meter)
    except RuntimeError as exc:
        print(f"ABORTED (no spend): {exc}")
        return 2
    task_text = tasks["task_T1"]["description"] + " (tier-1 conditions)"

    def generate_fn():
        proposal = generate_task_program(
            client, task_text, POLICY_API_DOC,
            int(gen["max_output_tokens"]), model=gen["model"], cache=cache)
        entry = meter.ledger[-1]
        return proposal.code, {
            "model": proposal.model, "tokens_in": entry["tokens_in"],
            "tokens_out": entry["tokens_out"], "cost_usd": entry["cost_usd"],
            "prompt_hash": proposal.prompt_hash}

    def execute_fn(scenario, seed, policy_code):
        return pilot_mod.execute_episode(
            scenario, seed, policy_code, repo_root=str(ROOT),
            timeout_s=float(gen["timeout_s"]), memory_mb=int(gen["memory_mb"]))

    try:
        sha = git_head()
    except PilotAbortLocal as exc:
        print(f"ABORTED (no spend): {exc}")
        return 2
    try:
        summary = pilot_mod.run_pilot(
            args.run_id, runs_dir=args.runs_dir, gen=gen, pricing=pricing,
            budget_cap=meter.cap_usd, generate_fn=generate_fn,
            execute_fn=execute_fn, git_sha=sha, config_hash=cfg_hash,
            created_at=utcnow(), repo_root=str(ROOT))
    except pilot_mod.PilotAbort as exc:
        print(f"ABORTED (no spend): {exc}")
        return 2
    except pilot_mod.PilotInvalid as exc:
        print(f"INVALID RUN: {exc}")
        return 2
    except BudgetExceeded as exc:
        print(f"ABORTED at cap: {exc}")
        return 2
    finally:
        save_cache(cache)
    verdict = "PASS" if summary["rate"] >= pilot_mod.G0_THRESHOLD else "FAIL"
    print(f"G0: {summary['k']}/{summary['n']} = {summary['rate']:.3f} "
          f"(threshold {pilot_mod.G0_THRESHOLD:.2f}): {verdict}")
    print(f"cost this run: ${summary['cost_usd']:.4f} "
          f"(meter total ${meter.spent_usd:.4f} / cap ${meter.cap_usd:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
