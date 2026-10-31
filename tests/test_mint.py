"""Mint-freeze validation tests (offline: no LLM, no simulator).

The Phase 08 certification input must be a persisted, hash-pinned program:
these tests guard the freeze/validate helpers so a truncated or tampered
source can never pass as the frozen program.
"""

import json
from typing import Any

import pytest

from experiments.run_mint_cert_program import (
    FreezeError,
    freeze_program,
    validate_freeze,
)
from pathlib import Path
import yaml

CODE = "def policy(env, rng):\n    env.open_gripper()\n"

def _get_mint_seeds():
    cfg = yaml.safe_load(Path("configs/mint.yaml").read_text(encoding="utf-8"))
    sb = cfg["seed_base"]
    is_b2 = cfg.get("arm") == "B2"
    fs = sb + (10000 if is_b2 else 100000)
    cs = sb + 30000 if is_b2 else fs + 10
    rs = sb + 40000 if is_b2 else sb + 200000
    return sb, fs, cs, rs



def _record(seed: int) -> dict:
    """One complete EpisodeResult record (readers reject partial lines)."""
    return {
        "episode_id": f"e{seed}", "stream": "repair", "task": "task_T1",
        "program_id": "p", "program_version": 0, "scenario": {"seed": seed},
        "seed": seed, "truth_success": True, "truth_success_alt": True,
        "margin": 0.1, "judge_mode": "state", "judge_pass": None,
        "judge_confidence": None, "trace_path": "t", "frames_path": None,
        "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        "created_at": "2026-10-30T00:00:00Z",
    }


def _good_freeze(path) -> dict:
    """Write a minimal valid freeze with 2 logged episodes."""
    import json as _json

    (path / "episodes.jsonl").write_text(
        "".join(_json.dumps(_record(s)) + "\n" for s in (60000, 60001)),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps({"episodes_planned": 2, "config_hash": "abc123"}),
        encoding="utf-8",
    )
    return freeze_program(
        path,
        CODE,
        rationale="test fix",
        seeds=[60000, 60001],
        acceptance={"reason": "accepted", "stage": 3},
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.01,
        model="muse-spark-1.3",
        config_hash="abc123",
    )


def test_freeze_roundtrip_validates(tmp_path) -> None:
    """A complete, honest freeze validates and returns its program_id."""
    freeze = _good_freeze(tmp_path)
    checked = validate_freeze(tmp_path)
    assert checked["program_id"] == freeze["program_id"]
    assert len(checked["program_id"]) == 16
    assert checked["acceptance"]["stage"] == 3


def test_freeze_rejects_tampered_source(tmp_path) -> None:
    """Appending one line after freezing breaks the hash pin."""
    _good_freeze(tmp_path)
    with open(tmp_path / "program_final.py", "a", encoding="utf-8") as f:
        f.write("    # sneaky edit\n")
    with pytest.raises(FreezeError):
        validate_freeze(tmp_path)


def test_freeze_rejects_unaccepted(tmp_path) -> None:
    """A freeze whose acceptance evidence is not an accept never validates."""
    import json as _json2

    (tmp_path / "episodes.jsonl").write_text(
        _json2.dumps(_record(60000)) + "\n", encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"episodes_planned": 1}), encoding="utf-8"
    )
    freeze_program(
        tmp_path,
        CODE,
        rationale="failed fix",
        seeds=[60000],
        acceptance={"reason": "Failed counterexample", "stage": 1},
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.01,
        model="muse-spark-1.3",
        config_hash="abc123",
    )
    with pytest.raises(FreezeError):
        validate_freeze(tmp_path)


class FakeMintClient:
    """Offline Fake client for mint unit tests (Rule H8: Fake*)."""

    def __init__(
        self,
        responses: list[tuple[str, str]],
        tokens_in: int = 120,
        tokens_out: int = 250,
        cost_usd: float = 0.003,
        meter: Any = None,
    ) -> None:
        self.responses = list(responses)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost_usd = cost_usd
        self.meter = meter
        self.prompts: list[str] = []

    def complete(
        self,
        model: str,
        prompt: str,
        max_output_tokens: int,
        images_b64: list[str] | None = None,
    ) -> dict:
        self.prompts.append(prompt)
        code, rationale = (
            self.responses.pop(0)
            if self.responses
            else ("def policy(env, rng):\n    pass\n", "default")
        )
        payload = json.dumps({"code": code, "rationale": rationale})
        cost = self.cost_usd
        if self.meter is not None:
            cost = self.meter.charge(model, self.tokens_in, self.tokens_out)
        return {
            "text": payload,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": cost,
        }


def test_save_cache_safe(tmp_path) -> None:
    """Verify safe atomic persistence of cache containing dataclasses and dicts."""
    from experiments.run_mint_cert_program import save_cache_safe
    from closedloop.gen.generator import ProgramProposal

    cache_path = tmp_path / "llm_cache.json"
    prop = ProgramProposal(
        code="def policy(env, rng): pass\n",
        rationale="test proposal",
        model="muse-spark-1.3",
        prompt_hash="p123",
        tokens_in=50,
        tokens_out=100,
        cost_usd=0.001,
    )
    save_cache_safe({"hash1": prop, "hash2": {"plain": "dict"}}, cache_path)
    assert cache_path.exists()
    loaded = json.loads(cache_path.read_text(encoding="utf-8"))
    assert loaded["hash1"]["prompt_hash"] == "p123"
    assert loaded["hash2"]["plain"] == "dict"


def _get_mint_seeds():
    import yaml
    from pathlib import Path

    mint_cfg = yaml.safe_load(Path("configs/mint.yaml").read_text(encoding="utf-8"))
    s_base = mint_cfg["seed_base"]
    fals_seed = s_base + (10000 if mint_cfg.get("arm") == "B2" else 100000)
    ce_seed = s_base + 30000 if mint_cfg.get("arm") == "B2" else fals_seed + 10
    rerun_seed = s_base + 40000 if mint_cfg.get("arm") == "B2" else s_base + 200000
    return s_base, fals_seed, ce_seed, rerun_seed


def test_mint_preserves_sources_and_trace_on_rejection(tmp_path, monkeypatch) -> None:
    """On rejection: initial and candidate sources, trace, cache, and costs are preserved."""
    from closedloop.data import log as episode_log
    from closedloop.exec import pilot as pilot_mod
    from experiments.run_mint_cert_program import MintRejected, run_mint

    code_v0 = "def policy(env, rng):\n    # v0 initial\n    env.open_gripper()\n"
    code_v1 = "def policy(env, rng):\n    # v1 repair candidate\n    env.open_gripper()\n"
    fake_client = FakeMintClient(
        responses=[(code_v0, "v0 initial proposal"), (code_v1, "v1 candidate repair")],
        tokens_in=120,
        tokens_out=250,
    )

    s_base, fals_seed, ce_seed, rerun_seed = _get_mint_seeds()

    def fake_execute(scenario, seed, policy_code, **kwargs):
        # Initial policy v0 fails loop and search/minimizer scenario
        if policy_code == code_v0:
            if seed == s_base or seed == fals_seed or seed == ce_seed or (s_base + 20000 <= seed <= s_base + 20006):
                return ("sim", {"truth_success": False, "truth_success_alt": False, "margin": -0.20, "trace": []})
            return ("sim", {"truth_success": True, "truth_success_alt": True, "margin": 0.05, "trace": []})
        # Candidate v1 passes counterexample and nominal, but fails rerun
        if seed == rerun_seed:
            return ("sim", {"truth_success": False, "truth_success_alt": False, "margin": -0.28, "trace": []})
        return ("sim", {"truth_success": True, "truth_success_alt": True, "margin": 0.05, "trace": []})

    monkeypatch.setattr(pilot_mod, "execute_episode", fake_execute)

    run_id = "test-rej-run"
    with pytest.raises(MintRejected):
        run_mint(run_id=run_id, runs_dir=str(tmp_path), client=fake_client)

    run_dir = tmp_path / run_id
    assert run_dir.exists()
    assert (run_dir / "program_initial.py").read_text(encoding="utf-8") == code_v0
    assert (run_dir / "program_candidate_v1.py").read_text(encoding="utf-8") == code_v1
    assert not (run_dir / "program_final.py").exists()
    assert not (run_dir / "freeze.json").exists()

    expected_call_cost = (120 * 1.25 + 250 * 4.25) / 1_000_000
    expected_tot_cost = round(2 * expected_call_cost, 6)

    trace_file = run_dir / "mint_trace.json"
    assert trace_file.exists()
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    assert trace["acceptance"]["accepted"] is False
    assert trace["acceptance"]["details"]["stage"] == 3
    assert trace["initial_program"]["tokens_in"] == 120
    assert trace["initial_program"]["tokens_out"] == 250
    assert trace["initial_program"]["cost_usd"] == pytest.approx(expected_call_cost, abs=1e-6)
    assert trace["repair_proposal"]["source_file"] == "program_candidate_v1.py"
    assert trace["repair_proposal"]["tokens_in"] == 120

    cache_file = run_dir / "llm_cache.json"
    assert cache_file.exists()
    cache_loaded = json.loads(cache_file.read_text(encoding="utf-8"))
    assert len(cache_loaded) >= 2

    manifest_file = run_dir / "manifest.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["generation"]["accepted"] is False
    assert manifest["spent_usd"] == pytest.approx(expected_tot_cost, abs=1e-6)
    assert manifest["tokens_spent"]["tokens_in"] == 240  # 2 calls * 120
    assert manifest["tokens_spent"]["tokens_out"] == 500  # 2 calls * 250
    assert manifest["tokens_spent"]["total"] == 740

    episodes = episode_log.read_episodes(run_dir / "episodes.jsonl")
    assert len(episodes) == 29
    assert episodes[0].tokens_in == 120
    assert episodes[0].tokens_out == 250
    assert episodes[0].cost_usd == pytest.approx(expected_call_cost, abs=1e-6)
    assert episodes[18].tokens_in == 120
    assert episodes[18].cost_usd == pytest.approx(expected_call_cost, abs=1e-6)


def test_mint_persists_sources_and_freeze_on_acceptance(tmp_path, monkeypatch) -> None:
    """On acceptance: initial, candidate, and program_final.py all exist, and freeze validates."""
    from closedloop.exec import pilot as pilot_mod
    from experiments.run_mint_cert_program import run_mint, validate_freeze

    code_v0 = "def policy(env, rng):\n    # v0\n    env.open_gripper()\n"
    code_v1 = "def policy(env, rng):\n    # v1 clean fix\n    env.open_gripper()\n"
    fake_client = FakeMintClient(
        responses=[(code_v0, "v0 initial"), (code_v1, "v1 clean accepted fix")],
        tokens_in=110,
        tokens_out=220,
    )

    s_base, fals_seed, ce_seed, rerun_seed = _get_mint_seeds()

    def fake_execute_accepted(scenario, seed, policy_code, **kwargs):
        if policy_code == code_v0:
            if seed == s_base or seed == fals_seed or seed == ce_seed or (s_base + 20000 <= seed <= s_base + 20006):
                return ("sim", {"truth_success": False, "truth_success_alt": False, "margin": -0.15, "trace": []})
            return ("sim", {"truth_success": True, "truth_success_alt": True, "margin": 0.05, "trace": []})
        # Candidate code_v1 passes everything
        return ("sim", {"truth_success": True, "truth_success_alt": True, "margin": 0.08, "trace": []})

    monkeypatch.setattr(pilot_mod, "execute_episode", fake_execute_accepted)

    run_id = "test-acc-run"
    outcome = run_mint(run_id=run_id, runs_dir=str(tmp_path), client=fake_client)

    run_dir = tmp_path / run_id
    assert outcome["accepted"] is True
    assert (run_dir / "program_initial.py").exists()
    assert (run_dir / "program_candidate_v1.py").exists()
    assert (run_dir / "program_final.py").exists()
    assert (run_dir / "program_final.py").read_text(encoding="utf-8") == code_v1
    assert (run_dir / "freeze.json").exists()

    validated = validate_freeze(run_dir)
    assert validated["program_id"] == outcome["program_id"]
    assert validated["acceptance"]["details"]["stage"] == 3

    expected_tot_cost = round(2 * ((110 * 1.25 + 220 * 4.25) / 1_000_000), 6)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["generation"]["accepted"] is True
    assert manifest["spent_usd"] == pytest.approx(expected_tot_cost, abs=1e-6)
    assert manifest["tokens_spent"]["total"] == 660


def test_repair_prompt_uses_actual_margin(tmp_path, monkeypatch) -> None:
    """Verify that the actual measured margin of the counterexample is passed to the repair prompt."""
    from closedloop.exec import pilot as pilot_mod
    from experiments.run_mint_cert_program import MintRejected, run_mint

    fake_client = FakeMintClient(
        responses=[
            ("def policy(env, rng):\n    pass\n", "v0"),
            ("def policy(env, rng):\n    pass\n", "v1"),
        ]
    )

    s_base, fals_seed, ce_seed, rerun_seed = _get_mint_seeds()
    measured_margin = -0.2958

    def fake_execute(scenario, seed, policy_code, **kwargs):
        if seed == s_base:
            return ("sim", {"truth_success": False, "truth_success_alt": False, "margin": -0.10, "trace": []})
        if seed == ce_seed or (s_base + 20000 <= seed <= s_base + 20006) or seed == fals_seed:
            return ("sim", {"truth_success": False, "truth_success_alt": False, "margin": measured_margin, "trace": []})
        return ("sim", {"truth_success": False, "truth_success_alt": False, "margin": -0.20, "trace": []})

    monkeypatch.setattr(pilot_mod, "execute_episode", fake_execute)

    with pytest.raises(MintRejected):
        run_mint(run_id="test-margin-run", runs_dir=str(tmp_path), client=fake_client)

    assert len(fake_client.prompts) == 2
    repair_prompt = fake_client.prompts[1]
    assert "-0.2958" in repair_prompt
    assert "Margin: -0.2958" in repair_prompt

