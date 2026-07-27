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
import sys
from dataclasses import dataclass, replace
from enum import Enum, IntEnum
from pathlib import Path

__all__ = [
    "TerminationOutcome",
    "TerminationResult",
    "observe_owned_processes",
    "owned_process_ids",
    "terminate_owned_processes",
]

_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_POLL_SECONDS = 0.02
_PROCESS_STAT_MINIMUM_FIELDS = 4
_PROCESS_STAT_SESSION_INDEX = 3
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
    UNKNOWN = 3


@dataclass(frozen=True, slots=True)
class TerminationResult:
    """Typed cleanup outcome with its complete procfs observation denominator."""

    outcome: TerminationOutcome
    scanned: int
    readable: int
    unreadable_pids: tuple[int, ...]
    candidate_unreadable_pids: tuple[int, ...]
    owned_pids: tuple[int, ...]

    @property
    def unreadable(self) -> int:
        """Return the number of scanned entries whose environments were unreadable."""

        return len(self.unreadable_pids)

    def observation_summary(self) -> str:
        """Render stable, non-secret procfs completeness evidence."""

        unreadable = _format_pids(self.unreadable_pids)
        candidate_unreadable = _format_pids(self.candidate_unreadable_pids)
        return (
            f"scanned {self.scanned}, readable {self.readable}, "
            f"unreadable {self.unreadable}; unreadable pids: {unreadable}; "
            f"candidate unreadable pids: {candidate_unreadable}"
        )

    def with_outcome(self, outcome: TerminationOutcome) -> TerminationResult:
        """Return the same evidence with a caller-refined terminal outcome."""

        return replace(self, outcome=outcome)


class _EntryState(Enum):
    OWNED = "owned"
    NOT_OWNED = "not_owned"
    UNREADABLE = "unreadable"
    VANISHED = "vanished"


@dataclass(frozen=True, slots=True)
class _OwnershipObservation:
    scanned: int
    readable: int
    unreadable_pids: tuple[int, ...]
    candidate_unreadable_pids: tuple[int, ...]
    owned_pids: tuple[int, ...]

    @property
    def is_unknown(self) -> bool:
        return bool(self.candidate_unreadable_pids)

    def with_candidate_unreadable(self, unreadable_pids: tuple[int, ...]) -> _OwnershipObservation:
        newly_unreadable = tuple(pid for pid in unreadable_pids if pid not in self.unreadable_pids)
        return replace(
            self,
            readable=max(0, self.readable - len(newly_unreadable)),
            unreadable_pids=tuple(sorted((*self.unreadable_pids, *newly_unreadable))),
            candidate_unreadable_pids=tuple(
                sorted((*self.candidate_unreadable_pids, *unreadable_pids))
            ),
            owned_pids=tuple(pid for pid in self.owned_pids if pid not in unreadable_pids),
        )

    def result(self, outcome: TerminationOutcome) -> TerminationResult:
        return TerminationResult(
            outcome=outcome,
            scanned=self.scanned,
            readable=self.readable,
            unreadable_pids=self.unreadable_pids,
            candidate_unreadable_pids=self.candidate_unreadable_pids,
            owned_pids=self.owned_pids,
        )


def owned_process_ids(environment_name: str, owner: str) -> tuple[int, ...]:
    """Return current numeric observations for an exact unique ownership marker."""

    return _observe_owned_processes(
        _owner_entry(environment_name, owner),
        candidate_pids=(),
        candidate_session_ids=(),
    ).owned_pids


def observe_owned_processes(
    environment_name: str,
    owner: str,
    *,
    candidate_pids: tuple[int, ...] = (),
    candidate_session_ids: tuple[int, ...] = (),
) -> TerminationResult:
    """Observe marker ownership and surface incomplete candidate evidence."""

    _validate_candidate_ids(candidate_pids)
    _validate_candidate_ids(candidate_session_ids)
    observation = _observe_owned_processes(
        _owner_entry(environment_name, owner),
        candidate_pids=candidate_pids,
        candidate_session_ids=candidate_session_ids,
    )
    if observation.is_unknown:
        return observation.result(TerminationOutcome.UNKNOWN)
    outcome = TerminationOutcome.SURVIVED if observation.owned_pids else TerminationOutcome.GRACEFUL
    return observation.result(outcome)


async def terminate_owned_processes(
    environment_name: str,
    owner: str,
    *,
    term_grace_seconds: float,
    kill_grace_seconds: float,
    candidate_pids: tuple[int, ...] = (),
    candidate_session_ids: tuple[int, ...] = (),
) -> TerminationResult:
    """Signal a marker-owned set through pidfds and wait for bounded disappearance."""

    _validate_grace_seconds(term_grace_seconds)
    _validate_grace_seconds(kill_grace_seconds)
    _validate_candidate_ids(candidate_pids)
    _validate_candidate_ids(candidate_session_ids)
    owner_entry = _owner_entry(environment_name, owner)
    candidate_scope = (candidate_pids, candidate_session_ids)
    observation = _observe_owned_processes(
        owner_entry,
        candidate_pids=candidate_pids,
        candidate_session_ids=candidate_session_ids,
    )
    result = _settled_result(observation, absent_outcome=TerminationOutcome.GRACEFUL)
    if result is not None:
        return result
    observation = await _signal_until_absent(
        owner_entry,
        signal.SIGTERM,
        grace_seconds=term_grace_seconds,
        candidate_scope=candidate_scope,
    )
    result = _settled_result(observation, absent_outcome=TerminationOutcome.GRACEFUL)
    if result is not None:
        return result
    observation = await _signal_until_absent(
        owner_entry,
        signal.SIGKILL,
        grace_seconds=kill_grace_seconds,
        candidate_scope=candidate_scope,
    )
    result = _settled_result(observation, absent_outcome=TerminationOutcome.KILLED)
    if result is not None:
        return result
    return observation.result(TerminationOutcome.SURVIVED)


def _settled_result(
    observation: _OwnershipObservation, *, absent_outcome: TerminationOutcome
) -> TerminationResult | None:
    if observation.is_unknown:
        return observation.result(TerminationOutcome.UNKNOWN)
    if not observation.owned_pids:
        return observation.result(absent_outcome)
    return None


async def _signal_until_absent(
    owner_entry: bytes,
    signal_number: signal.Signals,
    *,
    grace_seconds: float,
    candidate_scope: tuple[tuple[int, ...], tuple[int, ...]],
) -> _OwnershipObservation:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + grace_seconds
    candidate_pids, candidate_session_ids = candidate_scope
    while True:
        observation = _observe_owned_processes(
            owner_entry,
            candidate_pids=candidate_pids,
            candidate_session_ids=candidate_session_ids,
        )
        if observation.is_unknown or not observation.owned_pids:
            return observation
        unreadable_pids = _signal_owned_processes(
            observation.owned_pids, owner_entry, signal_number
        )
        if unreadable_pids:
            return observation.with_candidate_unreadable(unreadable_pids)
        remaining = deadline - loop.time()
        if remaining <= 0:
            return _observe_owned_processes(
                owner_entry,
                candidate_pids=candidate_pids,
                candidate_session_ids=candidate_session_ids,
            )
        await asyncio.sleep(min(_POLL_SECONDS, remaining))


def _signal_owned_processes(
    owned_pids: tuple[int, ...],
    owner_entry: bytes,
    signal_number: signal.Signals,
) -> tuple[int, ...]:
    unreadable_pids: list[int] = []
    for pid in owned_pids:
        try:
            process_fd = _open_pidfd(pid)
        except ProcessLookupError:
            continue
        try:
            entry_state = _process_entry_state(pid, owner_entry)
            if entry_state is _EntryState.UNREADABLE:
                unreadable_pids.append(pid)
                continue
            if entry_state is not _EntryState.OWNED:
                continue
            _send_pidfd_signal(process_fd, signal_number)
        except ProcessLookupError:
            continue
        finally:
            os.close(process_fd)
    return tuple(sorted(unreadable_pids))


def _observe_owned_processes(
    owner_entry: bytes,
    *,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
) -> _OwnershipObservation:
    readable = 0
    scanned = 0
    owned_pids: list[int] = []
    unreadable_pids: list[int] = []
    candidate_unreadable_pids: list[int] = []
    has_explicit_scope = bool(candidate_pids or candidate_session_ids)
    for process_directory in Path("/proc").iterdir():
        if not process_directory.name.isdigit():
            continue
        pid = int(process_directory.name)
        is_candidate = not has_explicit_scope or _is_candidate(
            pid,
            candidate_pids=candidate_pids,
            candidate_session_ids=candidate_session_ids,
        )
        entry_state = _process_entry_state(pid, owner_entry)
        if entry_state is _EntryState.VANISHED:
            continue
        if not is_candidate and entry_state is not _EntryState.OWNED:
            continue
        scanned += 1
        if entry_state is _EntryState.UNREADABLE:
            unreadable_pids.append(pid)
            candidate_unreadable_pids.append(pid)
            continue
        readable += 1
        if entry_state is _EntryState.OWNED:
            owned_pids.append(pid)
    return _OwnershipObservation(
        scanned=scanned,
        readable=readable,
        unreadable_pids=tuple(sorted(unreadable_pids)),
        candidate_unreadable_pids=tuple(sorted(candidate_unreadable_pids)),
        owned_pids=tuple(sorted(owned_pids)),
    )


def _process_entry_state(pid: int, owner_entry: bytes) -> _EntryState:
    try:
        environment = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except PermissionError:
        return _EntryState.UNREADABLE
    except (FileNotFoundError, ProcessLookupError):
        return _EntryState.VANISHED
    return _EntryState.OWNED if owner_entry in environment else _EntryState.NOT_OWNED


def _is_candidate(
    pid: int,
    *,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
) -> bool:
    if pid in candidate_pids:
        return True
    if not candidate_session_ids:
        return False
    try:
        process_stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False
    closing_parenthesis = process_stat.rfind(")")
    fields_after_name = process_stat[closing_parenthesis + 2 :].split()
    return (
        len(fields_after_name) >= _PROCESS_STAT_MINIMUM_FIELDS
        and int(fields_after_name[_PROCESS_STAT_SESSION_INDEX]) in candidate_session_ids
    )


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


def _validate_candidate_ids(values: tuple[int, ...]) -> None:
    if any(value <= 0 for value in values):
        raise ValueError("candidate process and session IDs must be positive")


def _format_pids(pids: tuple[int, ...]) -> str:
    return ",".join(str(pid) for pid in pids) if pids else "none"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment_name")
    parser.add_argument("owner")
    parser.add_argument("--term-grace-seconds", type=float, required=True)
    parser.add_argument("--kill-grace-seconds", type=float, required=True)
    parser.add_argument("--candidate-pid", action="append", type=int, default=[])
    parser.add_argument("--candidate-session-id", action="append", type=int, default=[])
    parser.add_argument("--observe-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Terminate one exact owned set for shell-based verifier callers."""

    arguments = _parser().parse_args(argv)
    candidate_pids = tuple(arguments.candidate_pid)
    candidate_session_ids = tuple(arguments.candidate_session_id)
    if arguments.observe_only:
        outcome = observe_owned_processes(
            arguments.environment_name,
            arguments.owner,
            candidate_pids=candidate_pids,
            candidate_session_ids=candidate_session_ids,
        )
    else:
        outcome = asyncio.run(
            terminate_owned_processes(
                arguments.environment_name,
                arguments.owner,
                term_grace_seconds=arguments.term_grace_seconds,
                kill_grace_seconds=arguments.kill_grace_seconds,
                candidate_pids=candidate_pids,
                candidate_session_ids=candidate_session_ids,
            )
        )
    if arguments.observe_only or outcome.outcome is TerminationOutcome.UNKNOWN:
        print(
            f"owned process cleanup {outcome.outcome.name}: {outcome.observation_summary()}",
            file=sys.stderr,
        )
    return int(outcome.outcome)


if __name__ == "__main__":
    raise SystemExit(main())
