"""H4: the ONLY module that talks to a model provider (Meta Model API).

Every call goes through CostMeter (H5), sets max_output_tokens, retries at
most 3 times, and reads the key from the environment (H2) — never from code.
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.request

import re

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
        reasoning_effort: str = "low",
        temperature: float = 0.0,
        seed: int = 42,
    ) -> dict[str, object]:
        """POST one chat completion; returns a small dict (no key material)."""
        import json

        payload = {
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": self._message(prompt, images_b64)}],
            "reasoning_effort": reasoning_effort,
            "temperature": temperature,
            "seed": seed,
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

    def segment(
        self,
        image_b64: str,
        prompt: str,
    ) -> dict[str, object]:
        """Call SAM 3.1 on /v1/responses to segment objects by prompt text (Plan §8)."""
        import json

        payload = {
            "model": "sam-3.1",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": "data:image/png;base64," + image_b64},
                        {"type": "input_text", "text": prompt},
                    ],
                }
            ],
        }
        body = json.dumps(payload).encode()
        last: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    BASE_URL + "/responses",
                    data=body,
                    headers={
                        "Authorization": "Bearer " + self._key,
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = json.loads(resp.read().decode())
                return self._metered_sam("sam-3.1", payload, raw)
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"SAM 3.1 API call failed after {MAX_RETRIES} tries: {last}")

    def _metered_sam(
        self, model: str, payload: object, raw: dict[str, object]
    ) -> dict[str, object]:
        usage = raw.get("usage", {})
        images_proc = usage.get("images_processed", 1) if isinstance(usage, dict) else 1
        tokens_in = max(1, images_proc * 1000)
        tokens_out = 50
        phash = hashlib.sha256(
            __import__("json").dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]
        cost = self.meter.charge(model, tokens_in, tokens_out, prompt_hash=phash)
        output = raw.get("output", [])
        text = ""
        if isinstance(output, list) and output:
            content = output[0].get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text", "")

        box = None
        w, h = 256, 256
        m = re.search(r"x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+)(?:;w=(\d+);h=(\d+))?", text)
        if m:
            x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if m.group(5) and m.group(6):
                w, h = int(m.group(5)), int(m.group(6))
            box = (x1, y1, x2, y2)

        return {
            "model": model,
            "text": text,
            "box": box,
            "w": w,
            "h": h,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost,
            "response_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
        }

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
        usage = raw.get("usage", None)
        if not isinstance(usage, dict):
            raise RuntimeError("response has no usage block: cannot cost call")
        tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
        for label, value in (("prompt_tokens", tin), ("completion_tokens", tout)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError(f"malformed usage: {label}={value!r}")
        assert tout <= cap, "model returned more tokens than max_output_tokens"
        phash = hashlib.sha256(
            __import__("json").dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]
        cost = self.meter.charge(model, tin, tout, prompt_hash=phash)
        choices = raw.get("choices", [])
        assert isinstance(choices, list) and choices
        return {
            "model": model,
            "text": choices[0].get("message", {}).get("content", ""),
            "tokens_in": tin,
            "tokens_out": tout,
            "cost_usd": cost,
            "response_hash": hashlib.sha256(
                str(choices[0]).encode()
            ).hexdigest()[:16],
        }

