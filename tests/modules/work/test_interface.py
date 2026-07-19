"""Work Module policy through its public Interface."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from ctower_kernel.record import (
    Actor,
    CustodyCommand,
    PrincipalKind,
    Record,
    RecordProblem,
    SourceReference,
    Ticket,
    TicketCommand,
    TicketCommandResult,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

__all__: tuple[str, ...] = ()


class _CommandRecord:
    def __init__(self, result: TicketCommandResult) -> None:
        self.result = result
        self.create_digest: bytes | None = None
        self.custody_digest: bytes | None = None

    def create_ticket(
        self,
        actor: Actor,
        command: TicketCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult:
        del actor, command, now, telemetry
        self.create_digest = request_digest
        return self.result

    def transfer_custody(
        self,
        actor: Actor,
        command: CustodyCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult:
        del actor, command, now, telemetry
        self.custody_digest = request_digest
        return self.result


def test_p0_requires_operator_but_p1_reaches_record_with_digest() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    record = _CommandRecord(_result(actor))
    work = Work(cast(Record, record))
    refused = work.create_ticket(
        actor, _ticket_command(actor, priority="P0"), telemetry=_telemetry()
    )
    accepted = work.create_ticket(
        actor, _ticket_command(actor, priority="P1"), telemetry=_telemetry()
    )

    assert isinstance(refused, RecordProblem)
    assert refused.code == "unauthorized"
    assert accepted == record.result
    assert record.create_digest is not None


def test_custody_requires_protected_operator_authority() -> None:
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    commander = Actor(uuid4(), operator.tenant_id, PrincipalKind.COMMANDER)
    record = _CommandRecord(_result(operator))
    work = Work(cast(Record, record))

    denied_actor = work.transfer_custody(
        commander, _custody_command(protected=True), telemetry=_telemetry()
    )
    denied_flag = work.transfer_custody(
        operator, _custody_command(protected=False), telemetry=_telemetry()
    )
    accepted = work.transfer_custody(
        operator, _custody_command(protected=True), telemetry=_telemetry()
    )

    assert isinstance(denied_actor, RecordProblem)
    assert isinstance(denied_flag, RecordProblem)
    assert accepted == record.result
    assert record.custody_digest is not None


def _ticket_command(actor: Actor, *, priority: str) -> TicketCommand:
    return TicketCommand(
        client_command_id=uuid4(),
        initial_custodian_id=actor.principal_id,
        priority=priority,
        source=SourceReference("test", "test:work"),
        title="Work policy",
    )


def _custody_command(*, protected: bool) -> CustodyCommand:
    return CustodyCommand(
        client_command_id=uuid4(),
        expected_version=1,
        from_custodian_id=uuid4(),
        protected_transfer=protected,
        reason="Protected handoff",
        ticket_id=uuid4(),
        to_custodian_id=uuid4(),
    )


def _result(actor: Actor) -> TicketCommandResult:
    return TicketCommandResult(
        command_id=uuid4(),
        event_ids=(uuid4(),),
        ticket=Ticket(
            ticket_id=uuid4(),
            title="Result",
            source=SourceReference("test", "test:result"),
            priority="P1",
            custodian_id=actor.principal_id,
            version=1,
            created_at=datetime.now(UTC),
        ),
    )


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
