"""Fail-closed cost accounting tests (written first; no network, no keys)."""

import pytest

from closedloop.llm.cost import BudgetExceeded, CostMeter, UnpricedModelError


def priced(cap: float = 1.0) -> CostMeter:
    """Meter with a verified test-only price (fictional numbers, never billed)."""
    meter = CostMeter(cap_usd=cap)
    meter.set_price("test-model", 2.0, 8.0)
    return meter


def test_unknown_model_fails_closed() -> None:
    """A model with no verified price can never record a successful charge."""
    meter = CostMeter(cap_usd=100.0)
    with pytest.raises(UnpricedModelError):
        meter.charge("muse-spark-1.3", 80, 400)
    assert meter.spent_usd == 0.0 and meter.calls == 0


def test_pricing_math() -> None:
    """(2.0/M in, 8.0/M out): 1M in + 0.5M out = $6.00 exactly."""
    meter = priced(cap=100.0)
    assert meter.charge("test-model", 1_000_000, 500_000) == pytest.approx(6.0)
    assert meter.spent_usd == pytest.approx(6.0)


def test_cumulative_cap_exhaustion() -> None:
    """Charges accumulate; the crossing charge is rejected and not recorded."""
    meter = priced(cap=10.0)
    meter.charge("test-model", 1_000_000, 0)  # $2.00, spent $2.00
    with pytest.raises(BudgetExceeded):
        meter.charge("test-model", 1_000_000, 4_000_000)  # $34, over cap
    assert meter.spent_usd == pytest.approx(2.0)
    assert meter.calls == 1


def test_missing_usage_rejected() -> None:
    """Responses without token usage cannot be costed: fail, don't $0-log."""
    from closedloop.llm.client import LLMClient

    client = LLMClient.__new__(LLMClient)
    client.meter = priced()
    with pytest.raises(RuntimeError):
        client._metered("test-model", {}, {"choices": [{"message": {}}]}, 100)


def test_negative_usage_rejected() -> None:
    """Negative token counts are malformed: fail, don't charge."""
    from closedloop.llm.client import LLMClient

    client = LLMClient.__new__(LLMClient)
    client.meter = priced()
    raw = {"usage": {"prompt_tokens": -5, "completion_tokens": 10},
           "choices": [{"message": {"content": "x"}}]}
    with pytest.raises(RuntimeError):
        client._metered("test-model", {}, raw, 100)
    assert client.meter.calls == 0


def test_zero_usage_allowed_and_logged() -> None:
    """Explicit zeros are costed as $0.00 (pinned semantics, not an error)."""
    from closedloop.llm.client import LLMClient

    client = LLMClient.__new__(LLMClient)
    client.meter = priced()
    raw = {"usage": {"prompt_tokens": 0, "completion_tokens": 0},
           "choices": [{"message": {"content": "x"}}]}
    out = client._metered("test-model", {}, raw, 100)
    assert out["tokens_in"] == 0 and client.meter.spent_usd == 0.0


def test_retry_accounting() -> None:
    """Two failed attempts then success: 3 urlopen calls, exactly 1 charge."""
    import urllib.request

    from closedloop.llm.client import LLMClient

    calls = {"n": 0}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            import json
            return json.dumps({
                "usage": {"prompt_tokens": 80, "completion_tokens": 100},
                "choices": [{"message": {"content": "ok"}}],
            }).encode()

    real = urllib.request.urlopen

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("down")
        return FakeResp()

    urllib.request.urlopen = flaky
    try:
        client = LLMClient.__new__(LLMClient)
        client.meter = priced(cap=100.0)
        client._key = "x"
        out = client.complete("test-model", "hi", 1024)
    finally:
        urllib.request.urlopen = real
    assert calls["n"] == 3 and out["tokens_in"] == 80
    assert client.meter.calls == 1  # only the successful response is costed


def test_ledger_holds_no_secrets() -> None:
    """Ledger entries carry counts/costs/hashes only: no prompt text, no keys."""
    import json

    meter = priced()
    meter.charge("test-model", 80, 100, prompt_hash="ab12")
    blob = json.dumps(meter.ledger)
    assert set(meter.ledger[0]) == {
        "model", "tokens_in", "tokens_out", "cost_usd", "prompt_hash", "at",
    }
    assert "MODEL_API_KEY" not in blob and "sk-" not in blob


if __name__ == "__main__":
    pytest.main([__file__])
