"""Bounded retry orchestration for durable protected mutations."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from random import SystemRandom
from uuid import UUID

from ctowerctl.spool import DrainReport, ReplayExecutor, Spool, SpoolEntry, SpoolError, SpoolState

__all__: tuple[str, ...] = ()

_MAXIMUM_ATTEMPTS = 4
_MAXIMUM_ELAPSED_SECONDS = 10.0
_INITIAL_BACKOFF_SECONDS = 0.25
_MAXIMUM_BACKOFF_SECONDS = 2.0
_RANDOM = SystemRandom()
_RETRYABLE_REASONS = frozenset(
    {
        "ambiguous_protocol_response",
        "durability_pending",
        "malformed_success",
        "mismatched_success",
        "temporary_server_response",
    }
)


@dataclass(frozen=True, slots=True)
class MutationRetryResult:
    """Last replay observation plus its durable target disposition."""

    report: DrainReport
    entry: SpoolEntry
    attempts: int
    exhausted: bool


def drain_with_retry(
    spool: Spool,
    executor: ReplayExecutor,
    command_id: UUID,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    jitter: Callable[[float], float] | None = None,
) -> MutationRetryResult:
    """Retry only pending transient outcomes; never remove an exhausted command."""

    deadline = monotonic() + _MAXIMUM_ELAPSED_SECONDS
    random_delay = jitter or (lambda ceiling: _RANDOM.uniform(ceiling / 2, ceiling))
    for attempt in range(1, _MAXIMUM_ATTEMPTS + 1):
        report = spool.drain(executor)
        entry = _current_entry(spool, command_id)
        terminal = (
            entry.state is not SpoolState.PENDING
            or report.barrier_sequence is not None
            or report.reason_code not in _RETRYABLE_REASONS
        )
        if terminal:
            return MutationRetryResult(report, entry, attempt, exhausted=False)
        if attempt == _MAXIMUM_ATTEMPTS or not _back_off(
            deadline,
            attempt,
            sleep=sleep,
            monotonic=monotonic,
            jitter=random_delay,
        ):
            return MutationRetryResult(report, entry, attempt, exhausted=True)
    raise AssertionError("bounded mutation retry loop did not return")


def _back_off(
    deadline: float,
    attempt: int,
    *,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
    jitter: Callable[[float], float],
) -> bool:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return False
    ceiling = min(
        _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
        _MAXIMUM_BACKOFF_SECONDS,
        remaining,
    )
    delay = jitter(ceiling)
    if not 0 <= delay <= ceiling:
        raise RuntimeError("mutation retry jitter escaped its bounded interval")
    sleep(delay)
    return monotonic() < deadline


def _current_entry(spool: Spool, command_id: UUID) -> SpoolEntry:
    entry = next(
        (item for item in spool.list_entries(limit=10_000) if item.command_id == command_id),
        None,
    )
    if entry is None:
        raise SpoolError("local_failure", "spooled command disappeared")
    return entry
