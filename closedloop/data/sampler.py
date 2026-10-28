"""Scenario sampler with enforced stream separation (H9).

Seed ranges (inclusive): repair 0-999999, calibration 1000000-1999999,
certification 2000000-2999999. Certification seeds are claimed once per
program through CertificationLedger, and only closedloop/certify/ may call
sample_certification (guarded by test_certification_only_via_certify).
"""

from __future__ import annotations

import numpy as np

STREAM_RANGES: dict[str, tuple[int, int]] = {
    "repair": (0, 999999),
    "calibration": (1000000, 1999999),
    "certification": (2000000, 2999999),
}

# Tier-2 scenario bounds for T1 (pose + mass + friction); tiers live in
# configs/tasks.yaml, defaults here so the sampler has no file dependency.
BOUNDS: dict[str, tuple[float, float]] = {
    "x": (-0.15, 0.15),
    "y": (-0.15, 0.15),
    "yaw": (-0.5, 0.5),
    "mass": (0.05, 0.6),
    "friction": (0.1, 1.0),
}


class LeakageError(RuntimeError):
    """Raised on any cross-stream seed misuse (H9)."""


def _check_range(stream: str, seed: int, n: int) -> tuple[int, int]:
    if stream not in STREAM_RANGES:
        raise LeakageError(f"unknown stream: {stream!r}")
    lo, hi = STREAM_RANGES[stream]
    if not (lo <= seed <= hi and seed + n - 1 <= hi):
        raise LeakageError(
            f"seed {seed}+{n} outside {stream} range [{lo}, {hi}]"
        )
    return lo, hi


def sample(stream: str, n: int, seed: int) -> list[dict[str, float | int]]:
    """Draw n deterministic scenarios; scenario seeds are seed..seed+n-1."""
    _check_range(stream, seed, n)
    rng = np.random.default_rng(seed)
    out: list[dict[str, float | int]] = []
    for i in range(n):
        scenario = {
            key: float(rng.uniform(low, high))
            for key, (low, high) in BOUNDS.items()
        }
        scenario["seed"] = seed + i
        out.append(scenario)
    return out


class CertificationLedger:
    """Tracks claimed certification seeds per program (single use each)."""

    def __init__(self) -> None:
        self.claimed: dict[str, set[int]] = {}

    def claim(self, program_id: str, seeds: list[int]) -> None:
        """Claim seeds for a program; re-claiming raises LeakageError."""
        lo, hi = STREAM_RANGES["certification"]
        for s in seeds:
            if not lo <= s <= hi:
                raise LeakageError(f"seed {s} outside certification range")
        used = self.claimed.setdefault(program_id, set())
        dupes = used.intersection(seeds)
        if dupes:
            raise LeakageError(
                f"seeds reused for {program_id}: {sorted(dupes)[:5]}"
            )
        used.update(seeds)


def sample_certification(
    program_id: str, n: int, seed: int, ledger: CertificationLedger
) -> list[dict[str, float | int]]:
    """Fresh i.i.d. certification scenarios; each seed claimed once (H9)."""
    scenarios = sample("certification", n, seed)
    ledger.claim(program_id, [int(s["seed"]) for s in scenarios])
    return scenarios
