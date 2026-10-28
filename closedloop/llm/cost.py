"""CostMeter (H5): every model call is logged and capped. No unbounded loops."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    """Raised when a charge would exceed the hard spend cap. Abort, do not retry."""


@dataclass
class CostMeter:
    """Tracks model spend; `charge` raises BudgetExceeded past the cap."""

    cap_usd: float = float(os.environ.get("BUDGET_USD_CAP", "60"))
    spent_usd: float = 0.0
    calls: int = 0
    ledger: list[dict[str, object]] = field(default_factory=list)
    prices_per_mtok: dict[str, tuple[float, float]] = field(default_factory=dict)

    def set_price(self, model: str, in_per_mtok: float, out_per_mtok: float) -> None:
        """Set $/Mtok (in, out) for a model. Prices are [VERIFY] until probed."""
        self.prices_per_mtok[model] = (in_per_mtok, out_per_mtok)

    def charge(
        self, model: str, tokens_in: int, tokens_out: int, prompt_hash: str = ""
    ) -> float:
        """Log one call and add its cost. Raises BudgetExceeded over the cap."""
        pin, pout = self.prices_per_mtok.get(model, (0.0, 0.0))
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
