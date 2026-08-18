"""Bounded retry policy for protected outbound mutations."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import Self, cast
from uuid import UUID, uuid4

import pytest

from ctower_client.models import InboxNotificationRequest
from ctower_client.operations import operation_for_cli
from ctowerctl import interface
from ctowerctl._command_types import MutationPayload
from ctowerctl._mutation_retry import MutationRetryResult, drain_with_retry
from ctowerctl._output import ExitCode
from ctowerctl.spool import (
    DrainReport,
    ReplayExecutor,
    Spool,
    SpoolCommand,
    SpoolEntry,
    SpoolState,
)

__all__: tuple[str, ...] = ()

_SEQUENCE = 17
_TRANSIENT_SUCCESS_ATTEMPTS = 3
_MAXIMUM_ATTEMPTS = 4
_ENTRY_SCAN_LIMIT = 10_000


def test_retry_accepts_after_transient_responses_with_capped_backoff() -> None:
    clock = _Clock()
    spool = _RetrySpool(
        (
            (SpoolState.PENDING, "temporary_server_response"),
            (SpoolState.PENDING, "durability_pending"),
            (SpoolState.ACCEPTED_ARCHIVE, "accepted"),
        )
    )

    result = drain_with_retry(
        cast(Spool, spool),
        cast(ReplayExecutor, object()),
        spool.command_id,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda ceiling: ceiling,
    )

    assert result.attempts == _TRANSIENT_SUCCESS_ATTEMPTS
    assert result.exhausted is False
    assert result.entry.state is SpoolState.ACCEPTED_ARCHIVE
    assert clock.delays == [0.25, 0.5]


def test_retry_stops_immediately_at_a_terminal_barrier() -> None:
    clock = _Clock()
    spool = _RetrySpool(((SpoolState.QUARANTINE, "permanent_server_rejection"),))

    result = drain_with_retry(
        cast(Spool, spool),
        cast(ReplayExecutor, object()),
        spool.command_id,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda ceiling: ceiling,
    )

    assert result.attempts == 1
    assert result.exhausted is False
    assert result.entry.state is SpoolState.QUARANTINE
    assert result.report.barrier_sequence == _SEQUENCE
    assert clock.delays == []


def test_retry_exhaustion_keeps_a_durable_reconcilable_pending_command() -> None:
    clock = _Clock()
    spool = _RetrySpool(((SpoolState.PENDING, "temporary_server_response"),))

    result = drain_with_retry(
        cast(Spool, spool),
        cast(ReplayExecutor, object()),
        spool.command_id,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda ceiling: ceiling,
    )

    assert result.attempts == _MAXIMUM_ATTEMPTS
    assert result.exhausted is True
    assert result.entry.state is SpoolState.PENDING
    assert result.entry.sequence == _SEQUENCE
    assert result.report.remaining_pending == 1
    assert clock.delays == [0.25, 0.5, 1.0]


def test_retry_rejects_jitter_outside_its_backoff_cap() -> None:
    spool = _RetrySpool(((SpoolState.PENDING, "temporary_server_response"),))

    with pytest.raises(RuntimeError, match="jitter escaped"):
        drain_with_retry(
            cast(Spool, spool),
            cast(ReplayExecutor, object()),
            spool.command_id,
            jitter=lambda ceiling: ceiling + 0.01,
        )


def test_interface_retries_only_notification_mutations_and_surfaces_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spool = _ExecutionSpool()
    retry_calls: list[UUID] = []

    def retry(
        _spool: Spool,
        _executor: ReplayExecutor,
        command_id: UUID,
    ) -> MutationRetryResult:
        retry_calls.append(command_id)
        entry = _entry(command_id, SpoolState.PENDING)
        spool.entry = entry
        return MutationRetryResult(
            _report(SpoolState.PENDING, "temporary_server_response"),
            entry,
            attempts=_MAXIMUM_ATTEMPTS,
            exhausted=True,
        )

    monkeypatch.setattr(Spool, "for_origin", staticmethod(lambda _origin: cast(Spool, spool)))
    monkeypatch.setattr(interface, "CtowerClient", lambda *_args, **_kwargs: _ClientContext())
    monkeypatch.setattr(interface, "GeneratedReplayExecutor", lambda _client: _Executor())
    monkeypatch.setattr(interface, "drain_with_retry", retry)
    monkeypatch.setattr(
        interface,
        "_build_mutation",
        lambda _arguments: MutationPayload(
            request=InboxNotificationRequest(
                project_key="ctower", severity="info", to="qa-agent", text="Bounded mirror."
            ),
            path_parameters={},
        ),
    )
    notify = operation_for_cli("inbox notify")
    ordinary = operation_for_cli("ticket create")
    assert notify is not None and ordinary is not None

    notify_id = uuid4()
    outcome, code = interface._execute_mutation(
        "https://ctower.example",
        "ephemeral-authority",
        _arguments(notify_id),
        notify,
    )
    assert outcome.reason_code == "retry_exhausted"
    assert outcome.sequence == _SEQUENCE
    assert code is ExitCode.TEMPORARY
    assert retry_calls == [notify_id]

    ordinary_id = uuid4()
    outcome, code = interface._execute_mutation(
        "https://ctower.example",
        "ephemeral-authority",
        _arguments(ordinary_id),
        ordinary,
    )
    assert outcome.reason_code == "temporary_server_response"
    assert code is ExitCode.TEMPORARY
    assert retry_calls == [notify_id]
    assert spool.drain_calls == 1


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.delays: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.now += delay


class _RetrySpool:
    def __init__(self, outcomes: tuple[tuple[SpoolState, str], ...]) -> None:
        self.command_id = uuid4()
        self._outcomes = outcomes
        self._index = 0
        self._entry = _entry(self.command_id, SpoolState.PENDING)

    def drain(self, _executor: object) -> DrainReport:
        state, reason = self._outcomes[min(self._index, len(self._outcomes) - 1)]
        self._index += 1
        self._entry = _entry(
            self.command_id, state, reason_code=reason if state is SpoolState.QUARANTINE else None
        )
        return DrainReport(
            attempted=1,
            accepted=1 if state is SpoolState.ACCEPTED_ARCHIVE else 0,
            quarantined=1 if state is SpoolState.QUARANTINE else 0,
            remaining_pending=1 if state is SpoolState.PENDING else 0,
            barrier_sequence=_SEQUENCE if state is SpoolState.QUARANTINE else None,
            reason_code=reason,
        )

    def list_entries(
        self,
        _state: SpoolState | None = None,
        *,
        limit: int,
    ) -> tuple[SpoolEntry, ...]:
        assert limit == _ENTRY_SCAN_LIMIT
        return (self._entry,)


class _ExecutionSpool:
    def __init__(self) -> None:
        self.entry = _entry(uuid4(), SpoolState.PENDING)
        self.drain_calls = 0

    def bind_credential(self, _credential: str) -> Self:
        return self

    def enqueue(self, command: SpoolCommand) -> SpoolEntry:
        self.entry = _entry(command.command_id, SpoolState.PENDING)
        return self.entry

    def drain(self, _executor: ReplayExecutor) -> DrainReport:
        self.drain_calls += 1
        return _report(SpoolState.PENDING, "temporary_server_response")

    def list_entries(
        self,
        _state: SpoolState | None = None,
        *,
        limit: int,
    ) -> tuple[SpoolEntry, ...]:
        assert limit == _ENTRY_SCAN_LIMIT
        return (self.entry,)


class _ClientContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(
        self,
        _exception_type: object,
        _exception: object,
        _traceback: object,
    ) -> None:
        return None


class _Executor:
    def __init__(self) -> None:
        self.observations: dict[UUID, object] = {}


def _arguments(command_id: UUID) -> argparse.Namespace:
    return argparse.Namespace(command_id=command_id)


def _report(state: SpoolState, reason: str) -> DrainReport:
    return DrainReport(
        attempted=1,
        accepted=1 if state is SpoolState.ACCEPTED_ARCHIVE else 0,
        quarantined=1 if state is SpoolState.QUARANTINE else 0,
        remaining_pending=1 if state is SpoolState.PENDING else 0,
        barrier_sequence=_SEQUENCE if state is SpoolState.QUARANTINE else None,
        reason_code=reason,
    )


def _entry(
    command_id: UUID,
    state: SpoolState,
    *,
    reason_code: str | None = None,
) -> SpoolEntry:
    now = datetime(2026, 8, 8, tzinfo=UTC)
    return SpoolEntry(
        sequence=_SEQUENCE,
        command_id=command_id,
        operation_id="notifyInbox",
        state=state,
        enqueued_at=now,
        expires_at=now + timedelta(days=1),
        bytes=128,
        reason_code=reason_code,
    )
