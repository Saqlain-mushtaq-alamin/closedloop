"""Run manifests: provenance for a run directory (H11/H12).

A manifest records everything needed to reproduce and audit a run: code
version, frozen configuration, seeds, pricing, and budget. It never holds
secrets or prompt contents (hashes only). Written once; overwrite refused.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def config_hash(paths: list[str | Path]) -> str:
    """sha256 over the concatenated bytes of the given config files."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(Path(path).read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


def build_manifest(
    *,
    run_id: str,
    git_sha: str,
    config_hash: str,
    model: str,
    pricing: dict,
    budget_cap_usd: float,
    episodes_planned: int,
    seeds: list[int],
    generation: dict,
    created_at: str,
    status: str = "valid",
) -> dict:
    """Assemble the manifest record (pure; caller writes it)."""
    return {
        "run_id": run_id,
        "created_at": created_at,
        "git_sha": git_sha,
        "config_hash": config_hash,
        "model": model,
        "pricing_per_mtok": pricing,
        "budget_cap_usd": budget_cap_usd,
        "episodes_planned": episodes_planned,
        "seeds": list(seeds),
        "generation": generation,
        "status": status,
    }


def write_manifest(run_dir: str | Path, manifest: dict) -> Path:
    """Write manifest.json once; refuse to overwrite an existing one."""
    path = Path(run_dir) / "manifest.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path
