"""Append-only EpisodeResult log (H10): one JSON object per line, never edited.

Field set follows plan Sec 6 exactly. Readers validate strictly: a record
missing a field raises instead of silently defaulting (H11).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

STREAMS = ("repair", "calibration", "certification")
JUDGE_MODES = ("state", "camera")


@dataclass
class EpisodeResult:
    """One episode, as defined in plan Sec 6."""

    episode_id: str
    stream: str
    task: str
    program_id: str
    program_version: int
    scenario: dict
    seed: int
    truth_success: bool
    truth_success_alt: bool
    margin: float
    judge_mode: str
    judge_pass: bool | None
    judge_confidence: float | None
    trace_path: str
    frames_path: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    created_at: str

    def validate(self) -> None:
        """Reject records that violate the schema (no silent defaults)."""
        if self.stream not in STREAMS:
            raise ValueError(f"bad stream: {self.stream!r}")
        if self.judge_mode not in JUDGE_MODES:
            raise ValueError(f"bad judge_mode: {self.judge_mode!r}")


def append_episode(path: str | Path, result: EpisodeResult) -> None:
    """Append one record; creates parent dirs; never touches existing lines."""
    result.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result), sort_keys=True) + "\n")


def read_episodes(path: str | Path) -> list[EpisodeResult]:
    """Read all records; incomplete lines raise (KeyError/TypeError)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = EpisodeResult(**json.loads(line))
            record.validate()
            out.append(record)
    return out


class RunDataError(ValueError):
    """A run directory that must not become a number (B5)."""


def summarize_run(run_dir: str | Path) -> dict[str, float | int]:
    """Validate a completed run and return {n, k, rate}.

    Requires manifest.json with episodes_planned and exactly that many
    parseable episode lines. Failures (truth false) count toward the rate;
    malformed or missing data raises instead of a partial rate.
    """
    run_dir = Path(run_dir)
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RunDataError(f"unreadable manifest: {exc}") from exc
    planned = manifest.get("episodes_planned")
    if not isinstance(planned, int) or isinstance(planned, bool) or planned <= 0:
        raise RunDataError(f"bad episodes_planned: {planned!r}")
    try:
        episodes = read_episodes(run_dir / "episodes.jsonl")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError,
            ValueError) as exc:
        raise RunDataError(f"unreadable episodes: {exc}") from exc
    if len(episodes) != planned:
        raise RunDataError(f"episodes {len(episodes)} != planned {planned}")
    hits = sum(1 for e in episodes if e.truth_success)
    return {"n": planned, "k": hits, "rate": hits / planned}
