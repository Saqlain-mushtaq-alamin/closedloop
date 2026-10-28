"""Windows Job Object ABI guards (run on every platform; no live API).

The first implementation used DWORD*12 (48 bytes) for a 64-byte structure
and wrote LimitFlags at byte 4 instead of 16, and left HANDLE returns
undeclared (truncated to 32 bits). These tests pin the documented layout
so that bug class fails here, not on Windows.
"""

import ctypes
import os

import pytest

from closedloop.exec import runner


def test_job_struct_layout() -> None:
    """Exact documented sizes and the LimitFlags offset."""
    basic = runner._BasicLimitInformation
    assert ctypes.sizeof(basic) == 64
    assert basic.LimitFlags.offset == 16
    assert ctypes.sizeof(runner._IoCounters) == 48
    assert ctypes.sizeof(runner._ExtendedLimitInformation) == 144


def test_job_constants() -> None:
    """Flag and info-class constants pinned to documented values."""
    assert runner._JOB_OBJECT_LIMIT_PROCESS_MEMORY == 0x100
    assert runner._JobObjectExtendedLimitInformation == 9


@pytest.mark.skipif(
    os.name == "nt", reason="off-Windows graceful-failure path only"
)
def test_job_limit_graceful_off_windows() -> None:
    """Off Windows the limiter reports (False, reason) instead of raising."""
    applied, detail = runner._windows_job_limit(0, 256)
    assert applied is False
    assert isinstance(detail, str) and detail, "diagnostic must be non-empty"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
