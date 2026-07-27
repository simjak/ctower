"""Bounded verifier cleanup for descendants carrying an exact owner marker."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import errno
import math
import os
import re
import signal
from enum import IntEnum
from pathlib import Path

__all__ = [
    "TerminationOutcome",
    "owned_process_ids",
    "terminate_owned_processes",
]

_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_POLL_SECONDS = 0.02
_LIBC = ctypes.CDLL(None, use_errno=True)
_PIDFD_OPEN = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
    use_errno=True,
)(("pidfd_open", _LIBC))
_PIDFD_SEND_SIGNAL = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_uint,
    use_errno=True,
)(("pidfd_send_signal", _LIBC))


class TerminationOutcome(IntEnum):
    """Process-set termination result and CLI exit status."""

    GRACEFUL = 0
    SURVIVED = 1
    KILLED = 2


def owned_process_ids(environment_name: str, owner: str) -> tuple[int, ...]:
    """Return current numeric observations for an exact unique ownership marker."""

    return _owned_process_ids(_owner_entry(environment_name, owner))


async def terminate_owned_processes(
    environment_name: str,
    owner: str,
    *,
    term_grace_seconds: float,
    kill_grace_seconds: float,
) -> TerminationOutcome:
    """Signal a marker-owned set through pidfds and wait for bounded disappearance."""

    _validate_grace_seconds(term_grace_seconds)
    _validate_grace_seconds(kill_grace_seconds)
    owner_entry = _owner_entry(environment_name, owner)
    if not _owned_process_ids(owner_entry):
        return TerminationOutcome.GRACEFUL
    if await _signal_until_absent(owner_entry, signal.SIGTERM, grace_seconds=term_grace_seconds):
        return TerminationOutcome.GRACEFUL
    if await _signal_until_absent(owner_entry, signal.SIGKILL, grace_seconds=kill_grace_seconds):
        return TerminationOutcome.KILLED
    return TerminationOutcome.SURVIVED


async def _signal_until_absent(
    owner_entry: bytes,
    signal_number: signal.Signals,
    *,
    grace_seconds: float,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + grace_seconds
    while True:
        if not _owned_process_ids(owner_entry):
            return True
        _signal_owned_processes(owner_entry, signal_number)
        remaining = deadline - loop.time()
        if remaining <= 0:
            return not _owned_process_ids(owner_entry)
        await asyncio.sleep(min(_POLL_SECONDS, remaining))


def _signal_owned_processes(owner_entry: bytes, signal_number: signal.Signals) -> int:
    signalled = 0
    for pid in _owned_process_ids(owner_entry):
        try:
            process_fd = _open_pidfd(pid)
        except ProcessLookupError:
            continue
        try:
            if not _process_has_entry(pid, owner_entry):
                continue
            _send_pidfd_signal(process_fd, signal_number)
            signalled += 1
        except ProcessLookupError:
            continue
        finally:
            os.close(process_fd)
    return signalled


def _owned_process_ids(owner_entry: bytes) -> tuple[int, ...]:
    matches: list[int] = []
    for process_directory in Path("/proc").iterdir():
        if not process_directory.name.isdigit():
            continue
        pid = int(process_directory.name)
        if _process_has_entry(pid, owner_entry):
            matches.append(pid)
    return tuple(sorted(matches))


def _process_has_entry(pid: int, owner_entry: bytes) -> bool:
    try:
        environment = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False
    return owner_entry in environment


def _open_pidfd(pid: int) -> int:
    process_fd = int(_PIDFD_OPEN(pid, 0))
    if process_fd >= 0:
        return process_fd
    error_number = ctypes.get_errno()
    if error_number == errno.ESRCH:
        raise ProcessLookupError(error_number, os.strerror(error_number), pid)
    raise OSError(error_number, os.strerror(error_number), pid)


def _send_pidfd_signal(process_fd: int, signal_number: signal.Signals) -> None:
    if _PIDFD_SEND_SIGNAL(process_fd, signal_number, None, 0) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.ESRCH:
        raise ProcessLookupError(error_number, os.strerror(error_number))
    raise OSError(error_number, os.strerror(error_number))


def _owner_entry(environment_name: str, owner: str) -> bytes:
    if _ENVIRONMENT_NAME.fullmatch(environment_name) is None:
        raise ValueError("ownership environment name must be an uppercase identifier")
    if not owner or "\0" in owner:
        raise ValueError("ownership marker must be non-empty and contain no NUL")
    return os.fsencode(f"{environment_name}={owner}")


def _validate_grace_seconds(value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError("termination grace periods must be finite and non-negative")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment_name")
    parser.add_argument("owner")
    parser.add_argument("--term-grace-seconds", type=float, required=True)
    parser.add_argument("--kill-grace-seconds", type=float, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Terminate one exact owned set for shell-based verifier callers."""

    arguments = _parser().parse_args(argv)
    outcome = asyncio.run(
        terminate_owned_processes(
            arguments.environment_name,
            arguments.owner,
            term_grace_seconds=arguments.term_grace_seconds,
            kill_grace_seconds=arguments.kill_grace_seconds,
        )
    )
    return int(outcome)


if __name__ == "__main__":
    raise SystemExit(main())
