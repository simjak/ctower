"""Work intake capability and structural policy checks."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
)
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeCommandResult,
    IntakeIntent,
    IntakeOutcome,
    IntakePromotionCommand,
    IntakeSubmitCommand,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Intake

__all__: tuple[str, ...] = ()
TWO_CALLS = 2


class _Writer:
    def __init__(self) -> None:
        self.digests: list[bytes] = []

    def submit_intake(
        self,
        actor: Actor,
        command: IntakeSubmitCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult:
        del actor, now, telemetry
        self.digests.append(request_digest)
        event_id, thread_id = uuid4(), uuid4()
        return IntakeCommandResult(
            command.client_command_id,
            (event_id,),
            event_id,
            IntakeOutcome.DISCUSSION,
            command.project_key,
            command.source,
            thread_id,
            1,
        )

    def promote_intake(
        self,
        actor: Actor,
        command: IntakePromotionCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult:
        del actor, now, telemetry
        self.digests.append(request_digest)
        ticket_id, event_id, thread_id = uuid4(), uuid4(), uuid4()
        return IntakeCommandResult(
            command.client_command_id,
            (event_id,),
            command.inbound_event_id,
            IntakeOutcome.TICKET_LINKED,
            "ctower",
            InboundSource("test", "test:promotion"),
            thread_id,
            2,
            ticket_id,
            1,
        )


def test_discussion_defaults_reach_writer_with_stable_digest() -> None:
    writer = _Writer()
    actor = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    command = IntakeSubmitCommand(
        uuid4(),
        "ctower",
        InboundSource("chat", "chat:1"),
        "Durable discussion",
    )
    intake = Intake(writer, clock=lambda: datetime(2026, 7, 25, tzinfo=UTC))

    first = intake.submit(actor, command, telemetry=_telemetry())
    second = intake.submit(actor, command, telemetry=_telemetry())

    assert isinstance(first, IntakeCommandResult)
    assert isinstance(second, IntakeCommandResult)
    assert len(writer.digests) == TWO_CALLS
    assert writer.digests[0] == writer.digests[1]


def test_importer_p0_and_mixed_discussion_are_refused_before_record() -> None:
    writer = _Writer()
    tenant_id = uuid4()
    commander = Actor(uuid4(), tenant_id, PrincipalKind.COMMANDER)
    importer = Actor(uuid4(), tenant_id, PrincipalKind.MIGRATION_IMPORTER)
    intake = Intake(writer)
    discussion = IntakeSubmitCommand(
        uuid4(),
        "ctower",
        InboundSource("chat", "chat:2"),
        "Discussion",
        target_ticket_id=uuid4(),
    )
    p0 = IntakeSubmitCommand(
        uuid4(),
        "ctower",
        InboundSource("chat", "chat:3"),
        "Urgent",
        intent=IntakeIntent.CREATE_TICKET,
        initial_custodian_id=commander.principal_id,
        priority="P0",
        title="Urgent intake",
    )

    capability = intake.submit(importer, discussion, telemetry=_telemetry())
    mixed = intake.submit(commander, discussion, telemetry=_telemetry())
    urgent = intake.submit(commander, p0, telemetry=_telemetry())

    assert isinstance(capability, RecordProblem)
    assert capability.code == "migration-capability-denied"
    assert isinstance(mixed, RecordProblem)
    assert mixed.code == "validation-error"
    assert isinstance(urgent, RecordProblem)
    assert urgent.code == "unauthorized"
    assert writer.digests == []


def test_promotion_requires_actionable_intent() -> None:
    writer = _Writer()
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    outcome = Intake(writer).promote(
        actor,
        IntakePromotionCommand(uuid4(), uuid4(), 1, IntakeIntent.DISCUSSION),
        telemetry=_telemetry(),
    )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "validation-error"
    assert writer.digests == []


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
