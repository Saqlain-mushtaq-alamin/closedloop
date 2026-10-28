"""Phase 03 Task 3 tests: program generator gates (written first).

FakeLLMClient is a unit-test stand-in (H8): named Fake*, lives in tests/,
never imported by closedloop/. No network is touched by any test here.
"""

import json

import pytest

from closedloop.gen.generator import (
    DEFAULT_MODEL,
    InvalidProgram,
    build_prompt,
    generate_task_program,
)

TASK = "Pick up the cube and place it on the pad."
PRIMS = "move_to(pos), open_gripper(), close_gripper(force), get_object_pose(name)"
GOOD_CODE = "move_to(env, (0.0, 0.0, 0.15))\n"


class FakeLLMClient:
    """Stand-in for LLMClient: canned responses, call log, no network."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, model: str, prompt: str, max_output_tokens: int,
                 images_b64=None) -> dict:
        """Mimic LLMClient.complete's contract (model, text, token counts)."""
        self.calls.append({"model": model, "prompt": prompt,
                           "max_output_tokens": max_output_tokens})
        return {"model": model, "text": self.responses.pop(0),
                "tokens_in": 10, "tokens_out": 20, "response_hash": "f" * 16}


def test_generator_prompt_content() -> None:
    """Prompt carries task, primitives, feedback; token cap passes through."""
    prompt = build_prompt(TASK, PRIMS, feedback="too slow")
    assert TASK in prompt and PRIMS in prompt and "too slow" in prompt
    client = FakeLLMClient([json.dumps({"code": GOOD_CODE, "rationale": "ok"})])
    generate_task_program(client, TASK, PRIMS, max_output_tokens=512)
    assert client.calls[0]["max_output_tokens"] == 512  # H5: cap always set
    assert client.calls[0]["model"] == DEFAULT_MODEL


def test_generator_parse_gate() -> None:
    """Unparseable model output is rejected and never executed (H13/H15)."""
    client = FakeLLMClient(["this is not json"])
    with pytest.raises(InvalidProgram):
        generate_task_program(client, TASK, PRIMS, max_output_tokens=512)
    assert len(client.calls) == 1


def test_generator_syntax_gate() -> None:
    """Valid JSON with broken Python is rejected before any execution."""
    client = FakeLLMClient(
        [json.dumps({"code": "def broken(:", "rationale": "oops"})])
    with pytest.raises(InvalidProgram):
        generate_task_program(client, TASK, PRIMS, max_output_tokens=512)


def test_generator_schema_gate() -> None:
    """JSON missing code/rationale keys is rejected."""
    client = FakeLLMClient([json.dumps({"code": GOOD_CODE})])
    with pytest.raises(InvalidProgram):
        generate_task_program(client, TASK, PRIMS, max_output_tokens=512)


def test_generator_cache() -> None:
    """Identical prompts hit the cache: one client call, same proposal."""
    body = json.dumps({"code": GOOD_CODE, "rationale": "cached"})
    client = FakeLLMClient([body])
    cache: dict = {}
    first = generate_task_program(client, TASK, PRIMS, max_output_tokens=512,
                                  cache=cache)
    second = generate_task_program(client, TASK, PRIMS, max_output_tokens=512,
                                   cache=cache)
    assert len(client.calls) == 1, "cache miss re-spent a call"
    assert first == second


if __name__ == "__main__":
    pytest.main([__file__])
