"""General Work refuses migration-importer authority before persistence."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from ctower_kernel.record import (
    Actor,
    CustodyCommand,
    PrincipalKind,
    Record,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import ChangePriority, Work

__all__: tuple[str, ...] = ()


class _Record:
    def __init__(self) -> None:
        self.called = False

    def create_ticket(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.called = True

    def transfer_custody(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.called = True


class _Writer:
    def __init__(self) -> None:
        self.called = False

    def execute_work(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.called = True


def test_importer_cannot_create_or_mutate_general_work() -> None:
    importer = Actor(uuid4(), uuid4(), PrincipalKind.MIGRATION_IMPORTER)
    record = _Record()
    writer = _Writer()
    work = Work(cast(Record, record), writer=cast(Any, writer))
    create = TicketCommand(
        uuid4(),
        uuid4(),
        "P2",
        SourceReference("migration", "forbidden"),
        "Forbidden general ticket",
    )
    mutate = ChangePriority(uuid4(), uuid4(), 1, "forbidden", "P1")
    transfer = CustodyCommand(
        client_command_id=uuid4(),
        expected_version=1,
        from_custodian_id=uuid4(),
        protected_transfer=True,
        reason="forbidden",
        ticket_id=uuid4(),
        to_custodian_id=uuid4(),
    )

    create_outcome = work.create_ticket(importer, create, telemetry=_telemetry())
    mutate_outcome = work.execute(importer, mutate, telemetry=_telemetry())
    transfer_outcome = work.transfer_custody(importer, transfer, telemetry=_telemetry())

    assert isinstance(create_outcome, RecordProblem)
    assert isinstance(mutate_outcome, RecordProblem)
    assert isinstance(transfer_outcome, RecordProblem)
    assert (
        create_outcome.code
        == mutate_outcome.code
        == transfer_outcome.code
        == "migration-capability-denied"
    )
    assert not record.called
    assert not writer.called


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )
