"""G0 pilot harness tests (written first; no network, no simulator).

generate_fn/execute_fn stand-ins drive run_pilot; the real episode path
(runner + trusted preamble + physics) is covered by construction elsewhere
and executes only on a simulator machine.
"""

import json

import pytest

from closedloop.data.log import RunDataError, append_episode, summarize_run
from closedloop.data.manifest import write_manifest
from closedloop.exec.pilot import PilotAbort, PilotInvalid, run_pilot
from closedloop.gen.generator import InvalidProgram

GEN = {"model": "muse-spark-1.3", "max_output_tokens": 1024, "tier": 1,
       "episodes": 3, "seed": 100, "timeout_s": 120, "memory_mb": 1024}
PRICING = {"muse-spark-1.3": [1.0, 2.0]}
GEN_RECORD = {"model": "muse-spark-1.3", "tokens_in": 80, "tokens_out": 100,
              "cost_usd": 0.00028, "prompt_hash": "h" * 16}
POLICY = "def policy(env, rng):\n    pass\n"


def _sim(ok=True):
    return {"truth_success": ok, "truth_success_alt": ok,
            "margin": 0.01 if ok else -0.02,
            "final_pos": [0.25, 0.0, 0.03], "steps": 300, "agreed": True,
            "trace": [[i, [0.0, 0.0, 0.02]] for i in range(1, 301)]}


def _run(tmp_path, outcomes, gen=None):
    calls = {"generate": 0}

    def generate_fn():
        calls["generate"] += 1
        if gen is not None:
            raise gen
        return POLICY, dict(GEN_RECORD)

    it = iter(outcomes)

    def execute_fn(scenario, seed, policy_code):
        assert policy_code == POLICY
        return next(it)

    summary = run_pilot(  # noqa: E501
        "r1", runs_dir=str(tmp_path), gen=dict(GEN), pricing=dict(PRICING),
        budget_cap=5.0, generate_fn=generate_fn, execute_fn=execute_fn,
        git_sha="abc", config_hash="cfg", created_at="2026-10-28T00:00:00Z",
        repo_root="/repo")
    return summary, calls


def test_full_run_counts_failures(tmp_path) -> None:
    """1 pass + 1 sim-fail + 1 infra-fail: n=3, k=1, all logged."""
    summary, _ = _run(tmp_path, [("sim", _sim(True)), ("sim", _sim(False)),
                                  ("infra", {"reason": "timeout"})])
    assert summary == {"run_id": "r1", "n": 3, "k": 1,
                       "rate": pytest.approx(1 / 3), "cost_usd": 0.00028,
                       "status": "valid"}
    assert len((tmp_path / "r1" / "episodes.jsonl").read_text().splitlines()) == 3
    assert len(list((tmp_path / "r1" / "traces").iterdir())) == 3
    manifest = json.loads((tmp_path / "r1" / "manifest.json").read_text())
    assert manifest["seeds"] == [100, 101, 102]
    assert manifest["status"] == "valid" and manifest["budget_cap_usd"] == 5.0
    assert "MODEL_API_KEY" not in json.dumps(manifest)


def test_invalid_generation_aborts_run(tmp_path) -> None:
    """Unparseable program: invalid manifest, zero episodes, no rate."""
    with pytest.raises(PilotInvalid):
        _run(tmp_path, [], gen=InvalidProgram("not JSON"))
    manifest = json.loads((tmp_path / "r1" / "manifest.json").read_text())
    assert manifest["status"] == "invalid_generation"
    assert not (tmp_path / "r1" / "episodes.jsonl").exists()


def test_existing_dir_refused_before_spend(tmp_path) -> None:
    """An existing run dir aborts before generate is ever called."""
    (tmp_path / "r1").mkdir()
    with pytest.raises(PilotAbort):
        _run(tmp_path, [])
    # only the pre-existing dir; no manifest written by us
    assert not (tmp_path / "r1" / "manifest.json").exists()


def test_bad_run_id_rejected(tmp_path) -> None:
    """Path-unsafe run IDs never become directories."""
    from closedloop.exec.pilot import run_pilot as rp

    with pytest.raises(PilotAbort):
        rp("a/b", runs_dir=str(tmp_path), gen=dict(GEN), pricing=dict(PRICING),
           budget_cap=5.0, generate_fn=lambda: (POLICY, dict(GEN_RECORD)),
           execute_fn=lambda *a: ("sim", _sim(True)),
           git_sha="abc", config_hash="cfg", created_at="t", repo_root="/repo")
    assert not (tmp_path / "a").exists()


def test_summarize_rejects_partial_and_garbled(tmp_path) -> None:
    """B5: fewer lines than planned, or a bad line, raises RunDataError."""
    from closedloop.data.log import EpisodeResult, append_episode
    from closedloop.data.manifest import build_manifest

    run = tmp_path / "r9"
    run.mkdir()
    manifest = build_manifest(
        run_id="r9", git_sha="g", config_hash="c", model="m",
        pricing=dict(PRICING), budget_cap_usd=5.0, episodes_planned=3,
        seeds=[1, 2, 3], generation=dict(GEN_RECORD), created_at="t")
    write_manifest(run, manifest)
    base = dict(episode_id="e", stream="repair", task="T1", program_id="p",
                program_version=0, scenario={}, seed=1, truth_success=True,
                truth_success_alt=True, margin=0.1, judge_mode="state",
                judge_pass=None, judge_confidence=None, trace_path="t",
                frames_path=None, tokens_in=0, tokens_out=0, cost_usd=0.0,
                created_at="t")
    append_episode(run / "episodes.jsonl", EpisodeResult(**{**base, "episode_id": "e1"}))
    append_episode(run / "episodes.jsonl", EpisodeResult(**{**base, "episode_id": "e2"}))
    with pytest.raises(RunDataError):
        summarize_run(run)
    with open(run / "episodes.jsonl", "a") as f:
        f.write("{not json\n")
    with pytest.raises(RunDataError):
        summarize_run(run)


if __name__ == "__main__":
    pytest.main([__file__])
