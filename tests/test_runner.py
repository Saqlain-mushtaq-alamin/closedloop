"""Phase 03 Task 1 tests: sandbox runner mechanics (written first).

Mechanics tests inject a FakeApi namespace (unit-test-only stand-in, H8:
never imported by closedloop/). Live-simulation execution is covered by an
integration test that runs only where PyBullet is installed (Windows).
"""

import shutil

import pytest

from closedloop.exec.runner import RunOutcome, run_program

FakeApi = {"tick": lambda: None, "add": lambda a, b: a + b}


def run(code: str, **kw) -> RunOutcome:
    """Run with small deterministic limits; keep workdir for inspection."""
    return run_program(code, FakeApi, timeout_s=3, memory_mb=256,
                       keep_workdir=True, **kw)


def test_sandbox_timeout() -> None:
    """An infinite loop is killed and recorded as a timeout failure."""
    out = run("while True:\n    tick()")
    assert not out.ok and out.reason == "timeout"


def test_sandbox_memory() -> None:
    """A 2 GB allocation under a 256 MB cap fails (killed or MemoryError)."""
    out = run("x = bytearray(2 ** 31)")
    assert not out.ok and out.reason in ("memory", "error")
    assert out.memory_enforced, "no memory limit was enforced"


def test_sandbox_network() -> None:
    """Importing socket/urllib/subprocess is blocked (H15, import level)."""
    for stmt in ("import socket", "import urllib.request", "import subprocess",
                 "import ctypes"):
        out = run(stmt + "\n")
        assert not out.ok and out.reason == "blocked", stmt


def test_sandbox_write_escape() -> None:
    """Absolute paths and .. escapes are blocked; relative writes land inside."""
    for stmt in ('open("/tmp/evil_p03.txt", "w")',
                 'open("../evil_p03.txt", "w")'):
        out = run(stmt + "\n")
        assert not out.ok and out.reason == "blocked", stmt
    out = run('open("ok.txt", "w").write("hi")\n')
    assert out.ok, out.detail
    try:
        assert (out.workdir_path is not None)
        with open(out.workdir_path + "/ok.txt") as f:
            assert f.read() == "hi"
    finally:
        shutil.rmtree(out.workdir_path, ignore_errors=True)


def test_crash_accounting() -> None:
    """V7: exceptions, timeouts and invalid code are failures with reasons."""
    bad = run("raise ValueError('boom')\n")
    assert not bad.ok and bad.reason == "error"
    invalid = run("def broken(:\n")
    assert not invalid.ok and invalid.reason == "error"
    slow = run("while True:\n    pass")
    assert not slow.ok and slow.reason == "timeout"


def test_no_fake_imports() -> None:
    """H8: no Fake* names in closedloop/ or experiments/ (tests only)."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    hits = []
    for base in ("closedloop", "experiments"):
        d = root / base
        if not d.exists():
            continue
        for path in d.rglob("*.py"):
            for i, line in enumerate(path.read_text().splitlines(), 1):
                if "Fake" in line:
                    hits.append(f"{path.relative_to(root)}:{i}")
    assert hits == [], f"fake-science names in product code: {hits}"


def test_api_result() -> None:
    """The injected namespace is usable and results are reported."""
    out = run("result = add(20, 22)\n")
    assert out.ok, out.detail


if __name__ == "__main__":
    pytest.main([__file__])
