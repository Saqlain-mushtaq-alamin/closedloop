"""CostMeter (H5): every model call is logged and capped. No unbounded loops."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    """Raised when a charge would exceed the hard spend cap. Abort, do not retry."""


class UnpricedModelError(RuntimeError):
    """Raised when a model has no verified price: charging is blocked.

    Prices enter only through set_price()/load_prices() after verification
    against an authoritative source. Unknown pricing never records $0.00.
    """


@dataclass
class CostMeter:
    """Tracks model spend; `charge` raises BudgetExceeded past the cap."""

    cap_usd: float = float(os.environ.get("BUDGET_USD_CAP", "60"))
    spent_usd: float = 0.0
    calls: int = 0
    ledger: list[dict[str, object]] = field(default_factory=list)
    prices_per_mtok: dict[str, tuple[float, float]] = field(default_factory=dict)

    def set_price(self, model: str, in_per_mtok: float, out_per_mtok: float) -> None:
        """Set verified $/Mtok (in, out) for a model. Never guess a price."""
        if in_per_mtok < 0 or out_per_mtok < 0:
            raise ValueError("prices must be non-negative")
        self.prices_per_mtok[model] = (in_per_mtok, out_per_mtok)

    def load_prices(self, path: object) -> dict[str, list[float]]:
        """Load verified prices from a pricing file (fail-closed).

        The file must declare pricing_verified: true with a models mapping;
        anything else raises and prices nothing.
        """
        import yaml

        with open(str(path), encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if not isinstance(doc, dict) or doc.get("pricing_verified") is not True:
            raise UnpricedModelError(f"{path}: pricing not verified")
        models = doc.get("models") or {}
        if not isinstance(models, dict) or not models:
            raise UnpricedModelError(f"{path}: no verified model prices")
        for model, rates in models.items():
            pin, pout = rates
            self.set_price(model, float(pin), float(pout))
        return {m: list(map(float, r)) for m, r in models.items()}

    def charge(
        self, model: str, tokens_in: int, tokens_out: int, prompt_hash: str = ""
    ) -> float:
        """Log one call and add its cost.

        Unknown model: UnpricedModelError, nothing recorded. Over the cap:
        BudgetExceeded, nothing recorded. Spend therefore never exceeds the
        cap, and no successful call is ever logged at $0.00 by default.
        Only a successful response is charged, so transport retries that
        never return usage cost nothing here (limitation: server-side work
        for failed attempts is unknowable client-side and uncharged).
        """
        if model not in self.prices_per_mtok:
            raise UnpricedModelError(
                f"no verified price for {model!r}: live calls blocked"
            )
        pin, pout = self.prices_per_mtok[model]
        cost = (tokens_in * pin + tokens_out * pout) / 1_000_000
        if self.spent_usd + cost > self.cap_usd:
            raise BudgetExceeded(
                f"cap ${self.cap_usd:.2f} would be exceeded "
                f"(spent ${self.spent_usd:.4f} + ${cost:.4f})"
            )
        self.spent_usd += cost
        self.calls += 1
        self.ledger.append(
            {
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": round(cost, 6),
                "prompt_hash": prompt_hash or None,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        return cost

    @staticmethod
    def prompt_hash(payload: object) -> str:
        """Stable hash of a request payload, for the response cache (Phase 03+)."""
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
