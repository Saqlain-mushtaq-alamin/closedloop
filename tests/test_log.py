"""Phase 03 Task 2 tests: EpisodeResult JSONL log (written first)."""

import json

import pytest

from closedloop.data.log import EpisodeResult, append_episode, read_episodes


def _result(episode_id: str = "e1", **kw) -> EpisodeResult:
    base = dict(
        episode_id=episode_id, stream="repair", task="T1",
        program_id="abc123", program_version=0,
        scenario={"x": 0.0, "seed": 7}, seed=7,
        truth_success=True, truth_success_alt=True, margin=0.012,
        judge_mode="state", judge_pass=None, judge_confidence=None,
        trace_path="t.json", frames_path=None,
        tokens_in=0, tokens_out=0, cost_usd=0.0, created_at="2026-10-28T00:00:00Z",
    )
    base.update(kw)
    return EpisodeResult(**base)


def test_episode_roundtrip(tmp_path) -> None:
    """Every plan Sec 6 field survives a write/read cycle, Nones included."""
    path = tmp_path / "episodes.jsonl"
    append_episode(path, _result())
    (back,) = read_episodes(path)
    assert back == _result()
    assert back.judge_pass is None and back.frames_path is None


def test_jsonl_append_only(tmp_path) -> None:
    """H10: a second run appends lines; earlier bytes never change."""
    path = tmp_path / "episodes.jsonl"
    append_episode(path, _result("e1"))
    append_episode(path, _result("e2"))
    frozen = path.read_bytes()
    assert len(frozen.strip().splitlines()) == 2
    append_episode(path, _result("e3"))
    assert path.read_bytes().startswith(frozen)
    assert len(read_episodes(path)) == 3


def test_strict_schema(tmp_path) -> None:
    """Incomplete records are rejected, never silently defaulted (H10/H11)."""
    path = tmp_path / "episodes.jsonl"
    path.write_text(json.dumps({"episode_id": "bad"}) + "\n")
    with pytest.raises((KeyError, TypeError)):
        read_episodes(path)


if __name__ == "__main__":
    pytest.main([__file__])
