"""H4: the ONLY module that talks to a model provider (Meta Model API).

Every call goes through CostMeter (H5), sets max_output_tokens, retries at
most 3 times, and reads the key from the environment (H2) — never from code.
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.request

BASE_URL = "https://api.meta.ai/v1"
CODE_MODEL = "muse-spark-1.3"
MAX_RETRIES = 3

from closedloop.llm.cost import CostMeter  # noqa: E402


class LLMClient:
    """Thin metered wrapper. Transport is stdlib urllib (no extra dependency)."""

    def __init__(self, meter: CostMeter, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("MODEL_API_KEY", "")
        if not key:
            raise RuntimeError("MODEL_API_KEY is not set (H2: read keys from env)")
        self._key = key
        self.meter = meter

    def complete(
        self,
        model: str,
        prompt: str,
        max_output_tokens: int,
        images_b64: list[str] | None = None,
    ) -> dict[str, object]:
        """POST one chat completion; returns a small dict (no key material)."""
        import json

        payload = {
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": self._message(prompt, images_b64)}],
        }
        body = json.dumps(payload).encode()
        last: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    BASE_URL + "/chat/completions",
                    data=body,
                    headers={
                        "Authorization": "Bearer " + self._key,
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = json.loads(resp.read().decode())
                return self._metered(model, payload, raw, max_output_tokens)
            except Exception as exc:  # noqa: BLE001 — counted, then reraised
                last = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"API call failed after {MAX_RETRIES} tries: {last}")

    @staticmethod
    def _message(prompt: str, images_b64: list[str] | None) -> object:
        if not images_b64:
            return prompt
        parts: list[object] = [{"type": "text", "text": prompt}]
        parts += [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b}}
            for b in images_b64
        ]
        return parts

    def _metered(
        self, model: str, payload: object, raw: dict[str, object], cap: int
    ) -> dict[str, object]:
        usage = raw.get("usage", {})
        assert isinstance(usage, dict)
        tin = int(usage.get("prompt_tokens", 0))
        tout = int(usage.get("completion_tokens", 0))
        assert tout <= cap, "model returned more tokens than max_output_tokens"
        phash = hashlib.sha256(
            __import__("json").dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]
        self.meter.charge(model, tin, tout, prompt_hash=phash)
        choices = raw.get("choices", [])
        assert isinstance(choices, list) and choices
        return {
            "model": model,
            "text": choices[0].get("message", {}).get("content", ""),
            "tokens_in": tin,
            "tokens_out": tout,
            "response_hash": hashlib.sha256(
                str(choices[0]).encode()
            ).hexdigest()[:16],
        }
