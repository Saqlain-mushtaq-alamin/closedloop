"""Phase 00 compliance tests (V13, V14, H4, H2). Written first, per phase file."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_env_ignored() -> None:
    """H2: .env must be git-ignored so keys can never be tracked."""
    r = subprocess.run(
        ["git", "check-ignore", "-q", ".env"], cwd=ROOT, capture_output=True
    )
    assert r.returncode == 0, ".env is not ignored by git"


def test_no_secrets() -> None:
    """V13: the secrets scanner must flag a planted fake key and pass clean."""
    script = ROOT / "scripts" / "check_no_secrets.sh"
    assert script.exists(), "check_no_secrets.sh missing"
    clean = subprocess.run(
        ["bash", str(script)], cwd=ROOT, capture_output=True, text=True
    )
    assert clean.returncode == 0, f"clean tree failed scan: {clean.stdout}"
    probe = Path(os.environ.get("TMPDIR", "/tmp")) / "secret_probe"
    probe.mkdir(exist_ok=True)
    planted = probe / "planted.txt"
    # Built at runtime so this test file itself never contains a key-like string.
    planted.write_text("MODEL_" + "API_KEY = 'sk" + "-test-plant-abcdef123456'\n")
    try:
        hit = subprocess.run(
            ["bash", str(script), str(probe)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert hit.returncode != 0, "scanner missed planted fake key"
    finally:
        planted.unlink(missing_ok=True)


def test_cost_meter_cap() -> None:
    """V14: CostMeter must abort once spend exceeds a tiny cap."""
    sys.path.insert(0, str(ROOT))
    from closedloop.llm.cost import BudgetExceeded, CostMeter

    meter = CostMeter(cap_usd=0.01)
    meter.set_price("probe", 1.25, 4.25)  # 10M in-tokens = $12.50 > $0.01 cap
    with pytest.raises(BudgetExceeded):
        meter.charge(model="probe", tokens_in=10_000_000, tokens_out=0)


def test_llm_client_only() -> None:
    """H4: only closedloop/llm/client.py may reference the model provider."""
    hits: list[str] = []
    for path in (ROOT / "closedloop").rglob("*.py"):
        if path.name == "client.py":
            continue
        text = path.read_text()
        if "api.meta.ai" in text or "MODEL_API_KEY" in text:
            hits.append(str(path.relative_to(ROOT)))
    for path in (ROOT / "experiments").rglob("*.py") if (
        ROOT / "experiments"
    ).exists() else []:
        text = path.read_text()
        if "api.meta.ai" in text or "MODEL_API_KEY" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"provider references outside client.py: {hits}"
