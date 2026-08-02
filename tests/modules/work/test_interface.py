"""Work Module policy through its public Interface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

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
from ctower_kernel.work import (
    AssignmentInterval,
    AssignmentKind,
    ChangeAssignment,
    ChangePriority,
    SchedulingCandidate,
    Work,
    WorkReadiness,
    WorkReceipt,
)

__all__: tuple[str, ...] = ()
CHANGED_VERSION = 2


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
        policy_refusal: RecordProblem | None = None,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult:
        del actor, command, now, policy_refusal, telemetry
        self.create_digest = request_digest
        return self.result

    def transfer_custody(
        self,
        actor: Actor,
        command: CustodyCommand,
        *,
        request_digest: bytes,
        policy_refusal: RecordProblem | None = None,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult | RecordProblem:
        del actor, command, now, telemetry
        self.custody_digest = request_digest
        return policy_refusal or self.result


class _WorkWriter:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def execute_work(self, actor: Actor, command: object, **parameters: object) -> WorkReceipt:
        del actor, parameters
        self.commands.append(command)
        return WorkReceipt(
            command_id=command.client_command_id,  # type: ignore[attr-defined]
            event_ids=(uuid4(),),
            operation="changed",
            ticket_id=command.ticket_id,  # type: ignore[attr-defined]
            version=CHANGED_VERSION,
        )

    def assignments(
        self, actor: Actor, ticket_id: UUID
    ) -> tuple[AssignmentInterval, ...] | RecordProblem:
        del actor, ticket_id
        return ()

    def readiness(self, actor: Actor, ticket_id: UUID) -> WorkReadiness | RecordProblem:
        del actor, ticket_id
        return WorkReadiness(ready=True, unmet_facts=())


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


def test_priority_change_requires_operator_for_p0_before_persistence() -> None:
    commander = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    operator = Actor(uuid4(), commander.tenant_id, PrincipalKind.OPERATOR)
    writer = _WorkWriter()
    work = Work(cast(Record, _CommandRecord(_result(operator))), writer=writer)
    command = ChangePriority(
        client_command_id=uuid4(),
        ticket_id=uuid4(),
        expected_version=1,
        reason="Urgent",
        priority="P0",
    )

    denied = work.execute(commander, command, telemetry=_telemetry())
    accepted = work.execute(operator, command, telemetry=_telemetry())

    assert isinstance(denied, RecordProblem)
    assert denied.code == "unauthorized"
    assert isinstance(accepted, WorkReceipt)
    assert accepted.version == CHANGED_VERSION
    assert writer.commands == [command]


def test_generic_assignment_cannot_mutate_custody_or_runner_lease() -> None:
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    writer = _WorkWriter()
    work = Work(cast(Record, _CommandRecord(_result(operator))), writer=writer)

    for assignment_kind in (AssignmentKind.TICKET_CUSTODIAN, AssignmentKind.RUNNER_LEASE_OWNER):
        outcome = work.execute(
            operator,
            ChangeAssignment(
                client_command_id=uuid4(),
                ticket_id=uuid4(),
                expected_version=1,
                reason="Not this Interface",
                assignment_kind=assignment_kind,
                to_principal_id=uuid4(),
            ),
            telemetry=_telemetry(),
        )
        assert isinstance(outcome, RecordProblem)
        assert outcome.code == "work-assignment-kind-refused"
    assert writer.commands == []


def test_scheduler_is_restart_stable_and_excludes_hard_ineligible_work() -> None:
    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    aged_p2 = SchedulingCandidate(
        UUID(int=3), "P2", now - timedelta(days=2), checkpoint_verified=True
    )
    p0 = SchedulingCandidate(UUID(int=2), "P0", now - timedelta(minutes=1))
    excluded = SchedulingCandidate(
        UUID(int=1),
        "P2",
        now - timedelta(days=30),
        unmet_eligibility=("trust",),
        checkpoint_verified=True,
    )
    work = Work(
        cast(Record, _CommandRecord(_result(Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR))))
    )

    decision = work.schedule((excluded, p0, aged_p2), now=now)
    restarted = work.schedule((excluded, p0, aged_p2), now=now)

    assert decision == restarted
    assert decision.ordered_ticket_ids == (aged_p2.ticket_id, p0.ticket_id)
    assert decision.excluded_ticket_ids == (excluded.ticket_id,)
    assert decision.checkpoint_preemptible_ids == (aged_p2.ticket_id,)


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
