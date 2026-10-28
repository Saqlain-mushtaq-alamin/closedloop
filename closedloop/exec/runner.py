"""Subprocess sandbox for LLM-written programs (H15).

A fresh interpreter child runs the program with: wall-clock timeout
(parent join/kill, all platforms), address-space cap (RLIMIT_AS after
fork on POSIX, memory-capped Job Object on Windows; fail-closed when
neither applies), closedloop modules purged except the injected API's own,
import-level network/process/native block, tempdir-confined file writes,
scrubbed API keys and proxy vars. Abnormal ends are recorded failures
(H13), never silent passes.

POSIX uses fork (the api dict is inherited, no pickling); Windows uses
spawn (api values must be picklable top-level callables; enforced loudly).
"""

from __future__ import annotations

import io
import multiprocessing as mp
import os
import pickle
import shutil
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MEMORY_MB = 1024

# Importable inside the sandbox: network, process-spawning, native escape.
_BLOCKED_IMPORTS = frozenset(
    {
        "socket", "ssl", "urllib", "http", "requests", "httpx", "urllib3",
        "ftplib", "smtplib", "telnetlib", "subprocess", "multiprocessing",
        "concurrent", "ctypes", "cffi",
    }
)

# os.* entry points that escape the sandbox even without imports.
_BLOCKED_OS_FUNCS = (
    "system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe",
    "spawnv", "spawnve", "spawnvp", "spawnvpe", "execv", "execve",
    "execl", "execle", "execlp", "execlpe", "fork", "forkpty", "kill",
)


@dataclass
class RunOutcome:
    """One sandboxed run: ok only on clean return."""

    ok: bool
    reason: str  # ok | timeout | memory | blocked | error | sandbox_unsupported
    detail: str
    seconds: float
    memory_enforced: bool
    workdir_path: str | None = None


def _install_guards(api: dict) -> None:
    """In-child restrictions: module purge, import hook, os/open patches."""
    import importlib.abc

    allowed = {getattr(v, "__module__", "") for v in api.values()}
    for mod in [m for m in sys.modules if m == "closedloop" or m.startswith("closedloop.")]:
        if mod not in allowed:
            del sys.modules[mod]
    # Already-imported modules bypass find_spec via sys.modules: evict the
    # blocked ones so the hook fires on re-import (fork inherits everything).
    for mod in [m for m in sys.modules if m.split(".")[0] in _BLOCKED_IMPORTS]:
        del sys.modules[mod]

    class _Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in _BLOCKED_IMPORTS:
                raise ImportError("blocked in sandbox: " + name)

    sys.meta_path.insert(0, _Guard())

    def _deny(*a, **k):
        raise PermissionError("blocked in sandbox")

    for _fn in _BLOCKED_OS_FUNCS:
        if hasattr(os, _fn):
            setattr(os, _fn, _deny)

    cwd = os.getcwd()

    def _confine(p):
        if not isinstance(p, str):
            raise PermissionError("non-str path blocked")
        full = os.path.realpath(os.path.join(cwd, p))
        try:
            ok = os.path.commonpath([full, cwd]) == cwd
        except ValueError:
            ok = False
        if not ok:
            raise PermissionError("write outside tempdir blocked: " + p)
        return full

    _real_open, _real_io_open, _real_os_open = open, io.open, os.open
    import builtins

    builtins.open = lambda f, *a, **k: _real_open(_confine(f), *a, **k)
    io.open = lambda f, *a, **k: _real_io_open(_confine(f), *a, **k)

    def _os_open(p, flags, *a, **k):
        return _real_os_open(_confine(p), flags, *a, **k)

    os.open = _os_open


def _child_main(conn, payload) -> None:  # type: ignore[no-untyped-def]
    """Child entry point (must stay importable for Windows spawn)."""
    code, api, workdir, memory_mb = payload
    try:
        for key in list(os.environ):
            if "API_KEY" in key.upper() or "PROXY" in key.upper():
                os.environ.pop(key, None)
        os.chdir(workdir)
        if os.name == "posix":
            import resource

            cap = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        _install_guards(api)
        namespace = dict(api)
        buf = io.StringIO()
        with redirect_stdout(buf):
            exec(compile(code, "<program>", "exec"), namespace)  # noqa: S102
        conn.send(("ok", buf.getvalue()[-500:]))
    except BaseException as exc:  # noqa: BLE001 -- every crash is a report
        tail = "".join(traceback.format_exception(exc))[-1500:]
        conn.send(("error", tail))
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _windows_job_limit(pid: int, memory_mb: int) -> bool:
    """Assign a Windows pid to a memory-capped Job Object (best effort)."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False

        class _Limits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", wintypes.DWORD * 12),
                ("IoInfo", wintypes.DWORD * 12),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        limits = _Limits()
        limits.BasicLimitInformation[1] = 0x100  # PROCESS_MEMORY
        limits.ProcessMemoryLimit = memory_mb * 1024 * 1024
        if not kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            kernel32.CloseHandle(job)
            return False
        proc = kernel32.OpenProcess(0x001F0FFF, False, pid)
        assigned = kernel32.AssignProcessToJobObject(job, proc) if proc else False
        kernel32.CloseHandle(proc)
        return bool(assigned)
    except Exception:  # noqa: BLE001 -- any failure means unenforced
        return False


def run_program(
    code: str,
    api: dict,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_mb: int = DEFAULT_MEMORY_MB,
    keep_workdir: bool = False,
) -> RunOutcome:
    """Execute code in a sandbox; abnormal ends are failures with reasons."""
    try:
        compile(code, "<program>", "exec")
    except SyntaxError as exc:
        return RunOutcome(False, "error", f"invalid code: {exc}", 0.0, False)
    if os.name == "posix":
        try:
            import resource  # noqa: F401
        except ImportError:
            return RunOutcome(False, "sandbox_unsupported",
                              "no memory-limit mechanism", 0.0, False)
        ctx = mp.get_context("fork")
        memory_enforced = True
    else:
        try:
            pickle.dumps(api)
        except Exception as exc:  # noqa: BLE001
            return RunOutcome(False, "error",
                              f"api not picklable for spawn: {exc}", 0.0, False)
        ctx = mp.get_context("spawn")
        memory_enforced = False  # decided after start (job assignment below)
    workdir = tempfile.mkdtemp(prefix="closedloop_run_")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_main,
                       args=(child_conn, (code, api, workdir, memory_mb)))
    start = time.perf_counter()
    proc.start()
    child_conn.close()
    if os.name != "posix":
        memory_enforced = _windows_job_limit(proc.pid, memory_mb)
        if not memory_enforced:
            proc.terminate()
            proc.join(5)
            shutil.rmtree(workdir, ignore_errors=True)
            return RunOutcome(False, "sandbox_unsupported",
                              "job-object limit failed", 0.0, False)
    proc.join(timeout_s)
    seconds = time.perf_counter() - start
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
            workdir = None  # type: ignore[assignment]
        return RunOutcome(False, "timeout", f"killed after {timeout_s}s",
                          seconds, memory_enforced, workdir)
    result = parent_conn.recv() if parent_conn.poll(10) else ("error", "no result")
    parent_conn.close()
    if not keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)
        workdir = None  # type: ignore[assignment]
    status, detail = result
    if status == "ok":
        return RunOutcome(True, "ok", detail, seconds, memory_enforced, workdir)
    if "MemoryError" in detail or proc.exitcode in (-9, -24):
        return RunOutcome(False, "memory", detail, seconds,
                          memory_enforced, workdir)
    if "blocked in sandbox" in detail:
        return RunOutcome(False, "blocked", detail, seconds,
                          memory_enforced, workdir)
    if "blocked" in detail and "PermissionError" in detail:
        return RunOutcome(False, "blocked", detail, seconds,
                          memory_enforced, workdir)
    return RunOutcome(False, "error", detail, seconds, memory_enforced, workdir)
