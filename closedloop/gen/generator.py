"""Muse Spark program generator: structured output, parse gate, cache.

Output contract: the model returns JSON {"code": ..., "rationale": ...}.
Anything else (non-JSON, missing keys, unparsable Python) raises
InvalidProgram, which callers count as a failure (H13) and never execute.
Prompt-hash caching avoids re-spending calls on reruns.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass

from closedloop.llm.cost import CostMeter

DEFAULT_MODEL = "muse-spark-1.3"


class InvalidProgram(ValueError):
    """Model output that must never reach the sandbox."""


@dataclass
class ProgramProposal:
    """One generated program plus the model's stated rationale."""

    code: str
    rationale: str
    model: str
    prompt_hash: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


def build_prompt(task: str, primitives_doc: str, feedback: str | None = None) -> str:
    """Assemble the generation prompt (pure; task + API + optional feedback)."""
    parts = [
        "Write a Python robot program using ONLY these primitives:",
        primitives_doc,
        "",
        "Task: " + task,
        "",
        "Reply with JSON object {\"code\": <python source>, \"rationale\": <text>}.",
        "The code defines policy(env, rng) using the primitives above.",
    ]
    if feedback:
        parts += ["", "Previous attempt feedback:", feedback]
    return "\n".join(parts)


def generate_task_program(
    client,  # LLMClient-shaped: complete(model, prompt, max_output_tokens)
    task: str,
    primitives_doc: str,
    max_output_tokens: int,
    model: str = DEFAULT_MODEL,
    feedback: str | None = None,
    cache: dict | None = None,
) -> ProgramProposal:
    """Generate, gate, and return one program proposal (H4/H5/H13)."""
    prompt = build_prompt(task, primitives_doc, feedback)
    prompt_hash = CostMeter.prompt_hash(
        {"model": model, "prompt": prompt, "max_output_tokens": max_output_tokens}
    )
    if cache is not None and prompt_hash in cache:
        return cache[prompt_hash]
    raw = client.complete(model, prompt, max_output_tokens)
    text = str(raw.get("text", "")).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise InvalidProgram(f"not JSON: {exc}") from exc
        else:
            raise InvalidProgram("not JSON: no JSON object found")
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("code"), str)
        or not isinstance(parsed.get("rationale"), str)
    ):
        raise InvalidProgram("missing string fields 'code'/'rationale'")
    try:
        ast.parse(parsed["code"])
    except SyntaxError as exc:
        raise InvalidProgram(f"unparsable code: {exc}") from exc
    proposal = ProgramProposal(
        code=parsed["code"],
        rationale=str(parsed.get("rationale", "")),
        model=model,
        prompt_hash=prompt_hash,
        tokens_in=int(raw.get("tokens_in", 0)),
        tokens_out=int(raw.get("tokens_out", 0)),
        cost_usd=float(raw.get("cost_usd", 0.0)),
    )
    if cache is not None:
        cache[prompt_hash] = proposal
    return proposal
