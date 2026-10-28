"""Subprocess sandbox for LLM-written programs (H15).

A fresh interpreter child runs the program with: wall-clock timeout
(parent join/kill, all platforms), address-space cap (RLIMIT_AS after
fork on POSIX, memory-capped Job Object on Windows; fail-closed when
neither applies), closedloop modules purged except the injected API's own,
import-level network/process/native block, tempdir-confined file writes,
scrubbed API keys and proxy vars. Abnormal ends are recorded failures
(H13), never silent passes.

The api dict travels as marshalled code (self-contained top-level
functions and lambdas only; closures and module-global users are rejected
loudly at pack time). Every run spawns a FRESH interpreter and the manifest
is plain picklable data: fork is deliberately avoided because a forked
child inherits the parent's address space, which already counts against an
RLIMIT_AS cap and makes enforcement parent-footprint-dependent (flaky).
One identical path on every platform.
"""

from __future__ import annotations

import builtins
import ctypes
import dis
import io
import marshal
import multiprocessing as mp
import os
import pickle
import shutil
import sys
import tempfile
import time
import traceback
import types
from contextlib import redirect_stdout
from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MEMORY_MB = 1024

# Importable inside the sandbox: network, process-spawning, native escape,
# plus anything that breaks determinism or reaches the physics engine
# directly (policies drive episodes only through the provided namespace).
_BLOCKED_IMPORTS = frozenset(
    {
        "socket", "ssl", "urllib", "http", "requests", "httpx", "urllib3",
        "ftplib", "smtplib", "telnetlib", "subprocess", "multiprocessing",
        "concurrent", "ctypes", "cffi",
        "pybullet", "random", "numpy",
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
    data: object = None  # trusted harness payload (setup_code's __result__)


def _covered(name: str, allow: frozenset) -> bool:
    """Exact allow-list entry, or a parent package the import system needs."""
    return any(name == entry or entry.startswith(name + ".") for entry in allow)


def _install_guards(api: dict, allow_modules: frozenset = frozenset()) -> None:
    """In-child restrictions: module purge, import hook, os/open patches.

    closedloop.* imports are denied except the allow-list. Everything else
    follows the block-list.
    """
    import importlib.abc

    allowed = {getattr(v, "__module__", "") for v in api.values()}
    for mod in [m for m in sys.modules if m == "closedloop" or m.startswith("closedloop.")]:
        if mod not in allowed and not _covered(mod, allow_modules):
            del sys.modules[mod]
    # Already-imported modules bypass find_spec via sys.modules: evict the
    # blocked ones so the hook fires on re-import (spawn pulls in stdlib).
    for mod in [m for m in sys.modules if m.split(".")[0] in _BLOCKED_IMPORTS]:
        del sys.modules[mod]

    class _Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            top = name.split(".")[0]
            if top in _BLOCKED_IMPORTS:
                raise ImportError("blocked in sandbox: " + name)
            if top == "closedloop" and not _covered(name, allow_modules):
                raise ImportError("not importable in sandbox: " + name)

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


def _code_uses_only_builtins(code: object) -> bool:
    """True when a code tree reads no closure cells and no module globals."""
    stack = [code]
    while stack:
        node = stack.pop()
        for ins in dis.get_instructions(node):
            if ins.opname in ("LOAD_DEREF", "LOAD_CLOSURE", "LOAD_CLASSDEREF"):
                return False
            if ins.opname == "LOAD_GLOBAL":
                if ins.argval not in dir(builtins):
                    return False
        stack.extend(
            const for const in node.co_consts if isinstance(const, types.CodeType)
        )
    return True


def _pack_api(api: dict) -> dict[str, tuple[bytes, tuple | None, tuple | None, str]]:
    """Serialize api callables as code (plain data: picklable everywhere).

    Each value must be a self-contained plain function (lambdas included):
    no closures, no module-global reads, picklable defaults. Anything else
    raises TypeError with the offending name: a loud refusal, never a
    silently different function in the child.
    """
    manifest: dict[str, tuple[bytes, tuple | None, tuple | None, str]] = {}
    for name, fn in api.items():
        if not isinstance(fn, types.FunctionType):
            raise TypeError(f"api[{name!r}] is not a plain function")
        code = fn.__code__
        if fn.__closure__ is not None or not _code_uses_only_builtins(code):
            raise TypeError(
                f"api[{name!r}] is not self-contained "
                "(closures and module-global reads cannot cross processes)"
            )
        defaults = fn.__defaults__
        kwdefaults = fn.__kwdefaults__
        try:
            pickle_check = pickle.dumps((defaults, kwdefaults))
            _ = pickle_check
        except Exception as exc:  # noqa: BLE001
            raise TypeError(f"api[{name!r}] defaults do not travel: {exc}") from exc
        manifest[name] = (marshal.dumps(code), defaults, kwdefaults, fn.__name__)
    return manifest


def _unpack_api(manifest: dict) -> dict:
    """Rebuild functions from _pack_api output (builtins-only globals)."""
    api: dict = {}
    for name, (blob, defaults, kwdefaults, fname) in manifest.items():
        fn = types.FunctionType(
            marshal.loads(blob), {"__builtins__": builtins}, fname
        )
        if defaults is not None:
            fn.__defaults__ = defaults
        if kwdefaults is not None:
            fn.__kwdefaults__ = kwdefaults
        api[name] = fn
    return api


def _child_main(conn, payload) -> None:  # type: ignore[no-untyped-def]
    """Child entry point (must stay importable for Windows spawn)."""
    code, manifest, workdir, memory_mb, allow_modules = payload
    try:
        for key in list(os.environ):
            if "API_KEY" in key.upper() or "PROXY" in key.upper():
                os.environ.pop(key, None)
        os.chdir(workdir)
        if os.name == "posix":
            import resource

            cap = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        api = _unpack_api(manifest)
        _install_guards(api, frozenset(allow_modules))
        namespace = dict(api)
        buf = io.StringIO()
        with redirect_stdout(buf):
            exec(compile(code, "<program>", "exec"), namespace)  # noqa: S102
        conn.send(("ok", buf.getvalue()[-500:], namespace.get("__result__")))
    except BaseException as exc:  # noqa: BLE001 -- every crash is a report
        tail = "".join(traceback.format_exception(exc))[-1500:]
        conn.send(("error", tail, None))
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# --- Windows Job Object ABI: exact documented layout (guarded by tests) ---
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
_JobObjectExtendedLimitInformation = 9
_PROCESS_ALL_ACCESS = 0x001F0FFF


class _BasicLimitInformation(ctypes.Structure):
    """JOBOBJECT_BASIC_LIMIT_INFORMATION: 64 bytes on 64-bit Windows."""

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    """IO_COUNTERS: 6 x 8 bytes."""

    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION: 144 bytes on 64-bit."""

    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _windows_job_limit(pid: int, memory_mb: int) -> tuple[bool, str]:
    """Apply a memory-capped Job Object to pid and verify it stuck.

    Returns (applied, detail). Detail names the failing call plus its
    Win32 error code (codes only, no secrets). Fail-closed: anything but
    a verified limit is (False, ...). HANDLE/restype declarations are
    explicit: an undeclared 64-bit HANDLE truncates to 32 bits and every
    later call fails with ERROR_INVALID_HANDLE (the previous bug).
    """
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError as exc:
        return False, f"no win32 api: {exc}"
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
    ]
    kernel32.QueryInformationJobObject.restype = ctypes.c_int
    kernel32.QueryInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_void_p,
    ]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.GetLastError.restype = ctypes.c_uint32

    def _fail(api: str) -> tuple[bool, str]:
        return False, f"{api} failed (winerr {kernel32.GetLastError()})"

    try:
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return _fail("CreateJobObjectW")
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_PROCESS_MEMORY
        limits.ProcessMemoryLimit = memory_mb * 1024 * 1024
        if not kernel32.SetInformationJobObject(
            job, _JobObjectExtendedLimitInformation,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            detail = _fail("SetInformationJobObject")
            kernel32.CloseHandle(job)
            return False, detail
        proc = kernel32.OpenProcess(_PROCESS_ALL_ACCESS, False, pid)
        if not proc:
            detail = _fail("OpenProcess")
            kernel32.CloseHandle(job)
            return False, detail
        assigned = kernel32.AssignProcessToJobObject(job, proc)
        kernel32.CloseHandle(proc)
        if not assigned:
            detail = _fail("AssignProcessToJobObject")
            kernel32.CloseHandle(job)
            return False, detail
        check = _ExtendedLimitInformation()
        ret_len = ctypes.c_uint32(0)
        if not kernel32.QueryInformationJobObject(
            job, _JobObjectExtendedLimitInformation,
            ctypes.byref(check), ctypes.sizeof(check), ctypes.byref(ret_len),
        ):
            detail = _fail("QueryInformationJobObject")
            kernel32.CloseHandle(job)
            return False, detail
        kernel32.CloseHandle(job)
        want = memory_mb * 1024 * 1024
        if check.ProcessMemoryLimit != want:
            return False, (
                "limit mismatch: job reports "
                f"{check.ProcessMemoryLimit}, want {want}"
            )
        return True, f"job-object {memory_mb} MB cap applied and verified"
    except Exception as exc:  # noqa: BLE001 -- any failure means unenforced
        return False, f"exception in job setup: {type(exc).__name__}: {exc}"


def run_program(
    code: str,
    api: dict,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_mb: int = DEFAULT_MEMORY_MB,
    keep_workdir: bool = False,
    allow_modules: frozenset = frozenset(),
) -> RunOutcome:
    """Execute code in a sandbox; abnormal ends are failures with reasons.

    allow_modules names the only closedloop.* modules importable in the
    child (plus their parent packages, which the import system needs).
    Trusted harness preambles live inside `code` itself and isolate the
    untrusted policy in a sub-namespace; a __result__ value left in the
    top namespace is returned on RunOutcome.data.
    """
    try:
        compile(code, "<program>", "exec")
    except SyntaxError as exc:
        return RunOutcome(False, "error", f"invalid code: {exc}", 0.0, False)
    try:
        manifest = _pack_api(api)
    except TypeError as exc:
        return RunOutcome(False, "error", f"api not portable: {exc}", 0.0, False)
    if os.name == "posix":
        try:
            import resource  # noqa: F401
        except ImportError:
            return RunOutcome(False, "sandbox_unsupported",
                              "no memory-limit mechanism", 0.0, False)
        memory_enforced = True  # RLIMIT_AS applied in the fresh child
    else:
        memory_enforced = False  # decided after start (job assignment below)
    ctx = mp.get_context("spawn")
    workdir = tempfile.mkdtemp(prefix="closedloop_run_")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child_main,
        args=(child_conn, (code, manifest, workdir, memory_mb,
                           tuple(allow_modules))),
    )
    start = time.perf_counter()
    proc.start()
    child_conn.close()
    if os.name != "posix":
        applied, job_detail = _windows_job_limit(proc.pid, memory_mb)
        memory_enforced = applied
        if not applied:
            proc.terminate()
            proc.join(5)
            shutil.rmtree(workdir, ignore_errors=True)
            return RunOutcome(False, "sandbox_unsupported",
                              f"job-object limit failed: {job_detail}",
                              0.0, False)
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
    result = (parent_conn.recv() if parent_conn.poll(10)
              else ("error", "no result", None))
    parent_conn.close()
    if not keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)
        workdir = None  # type: ignore[assignment]
    status, detail, data = result
    if status == "ok":
        return RunOutcome(True, "ok", detail, seconds, memory_enforced,
                          workdir, data)
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
