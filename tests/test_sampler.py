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


def test_certification_only_via_certify() -> None:
    """H9: only closedloop/certify/ may import the certification sampler."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if "sample_certification" in p.read_text()
        and "test_" not in p.name
        and "closedloop/data/sampler.py" not in str(p).replace("\\", "/")
        and "closedloop/certify" not in str(p).replace("\\", "/")
    ]
    assert offenders == [], f"certification sampler used outside certify/: {offenders}"
