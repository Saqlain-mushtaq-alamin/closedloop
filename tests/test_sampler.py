"""Phase 02 Task 1 tests: sampler streams + LeakageError (written first)."""

import pytest

from closedloop.data.sampler import (
    STREAM_RANGES,
    CertificationLedger,
    LeakageError,
    sample,
    sample_certification,
)


def test_stream_ranges_disjoint() -> None:
    """V4: the three seed streams must not overlap."""
    sets = [set(range(lo, hi + 1)) for lo, hi in STREAM_RANGES.values()]
    assert sets[0].isdisjoint(sets[1])
    assert sets[0].isdisjoint(sets[2])
    assert sets[1].isdisjoint(sets[2])
    assert STREAM_RANGES["repair"] == (0, 999999)
    assert STREAM_RANGES["calibration"] == (1000000, 1999999)
    assert STREAM_RANGES["certification"] == (2000000, 2999999)


def test_sample_deterministic() -> None:
    """Same (stream, n, seed) twice gives identical scenarios."""
    first = sample("repair", 10, 123)
    second = sample("repair", 10, 123)
    assert first == second
    assert [s["seed"] for s in first] == list(range(123, 133))


def test_sample_schema() -> None:
    """Scenarios carry the tier-2 keys within task bounds."""
    scenarios = sample("repair", 50, 500)
    for s in scenarios:
        assert set(s) >= {"x", "y", "yaw", "mass", "friction", "seed"}
        assert 0.0 <= s["mass"] <= 0.6
        assert 0.1 <= s["friction"] <= 1.0


def test_stream_disjoint() -> None:
    """V4: sampled seeds from each stream stay in their own range."""
    drawn = {
        stream: {s["seed"] for s in sample(stream, 20, lo)}
        for stream, (lo, _) in STREAM_RANGES.items()
    }
    assert drawn["repair"].isdisjoint(drawn["calibration"])
    assert drawn["repair"].isdisjoint(drawn["certification"])
    assert drawn["calibration"].isdisjoint(drawn["certification"])


def test_leakage_bad_stream() -> None:
    """Unknown stream names are rejected."""
    with pytest.raises(LeakageError):
        sample("nope", 5, 0)


def test_leakage_seed_out_of_range() -> None:
    """A repair seed may not come from the certification range and vv."""
    with pytest.raises(LeakageError):
        sample("repair", 5, 2000000)
    with pytest.raises(LeakageError):
        sample("calibration", 5, 42)


def test_certification_single_use() -> None:
    """V4: each certification seed is used once per program."""
    ledger = CertificationLedger()
    sample_certification("progA", 5, 2000000, ledger)
    with pytest.raises(LeakageError):
        sample_certification("progA", 5, 2000003, ledger)  # overlaps 2000000-4
    sample_certification("progB", 5, 2000000, ledger)  # other program: fine


_EXCLUDED_DIRS = frozenset(
    {
        ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".tox", "build", "dist",
    }
)


def _project_python_files(root):  # type: ignore[no-untyped-def]
    """Yield project-owned .py files (tracked or not), skipping env/caches.

    Directory names are filtered BEFORE any file is read, so third-party
    files (odd encodings, huge binaries) are never opened. Untracked project
    files are still covered: the walk is filesystem-based, not git-based.
    """
    for path in root.rglob("*.py"):
        if any(
            part in _EXCLUDED_DIRS or part.endswith(".egg-info")
            for part in path.parts
        ):
            continue
        yield path


def test_certification_only_via_certify() -> None:
    """H9: only closedloop/certify/ may import the certification sampler."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = [
        str(p.relative_to(root))
        for p in _project_python_files(root)
        # errors="replace" decodes ASCII needles identically; it only stops
        # a non-UTF-8 file from crashing the scan (cp1252 byte 0x81 on win).
        if "sample_certification" in p.read_text(encoding="utf-8", errors="replace")
        and "test_" not in p.name
        and "closedloop/data/sampler.py" not in p.as_posix()
        and "closedloop/certify" not in p.as_posix()
    ]
    assert offenders == [], f"certification sampler used outside certify/: {offenders}"
