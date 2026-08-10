"""Generated histories for database-enforced fulfillment-Ticket exclusivity."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from support.acceptance import accept_pending_commands
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestCapture,
    RequestCaptureResult,
    RequestChangeResult,
    RequestPriority,
    Requests,
    RequestTicketRelation,
    RequestTriage,
)

__all__: tuple[str, ...] = ()


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )


def _accepted_change(tenant: TenantFixture, result: object) -> RequestChangeResult:
    assert isinstance(result, RequestChangeResult), result
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return result


def _accepted_capture(
    tenant: TenantFixture, authority: Requests, actor: Actor, text: str
) -> RequestCaptureResult:
    command = RequestCapture(uuid4(), "ctower", text)
    first = authority.capture(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert isinstance(first, RequestCaptureResult), first
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return first


def _accepted_ticket(tenant: TenantFixture, actor: Actor) -> UUID:
    command = TicketCommand(
        client_command_id=uuid4(),
        initial_custodian_id=tenant.commander_id,
        priority="P2",
        project_key="ctower",
        source=SourceReference("request-review", f"ticket:{uuid4()}"),
        title="Review fulfillment",
    )
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert not isinstance(outcome, RecordProblem), outcome
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome.ticket.ticket_id


def _accept_request(
    tenant: TenantFixture, authority: Requests, actor: Actor, text: str
) -> tuple[UUID, int]:
    captured = _accepted_capture(tenant, authority, actor, text)
    prioritized = _accepted_change(
        tenant,
        authority.prioritize(
            actor,
            RequestPriority(uuid4(), captured.request_id, 1, "P2", "reviewed default"),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    triaged = _accepted_change(
        tenant,
        authority.triage(
            actor,
            RequestTriage(uuid4(), captured.request_id, prioritized.version, "ACCEPTED"),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    return captured.request_id, triaged.version


def _relate(
    authority: Requests,
    actor: Actor,
    request_id: UUID,
    version: int,
    ticket_id: UUID,
    ticket_version: int,
    *,
    active: bool,
) -> object:
    return authority.relate_ticket(
        actor,
        RequestTicketRelation(
            uuid4(),
            request_id,
            version,
            ticket_version,
            ticket_id,
            "required",
            active=active,
            reason="review probe",
        ),
        telemetry=_telemetry(actor, uuid4()),
    )


@pytest.mark.parametrize("older_churn", range(6), ids=lambda value: f"older-v{value + 3}")
def test_fulfillment_ticket_exclusivity_across_generated_request_versions(
    tenant: TenantFixture,
    older_churn: int,
) -> None:
    """Every generated cross-Request version history has exactly one current holder."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    ticket_id = _accepted_ticket(tenant, actor)

    # Request A: raise its version above the others before it ever touches the ticket.
    older_id, older_version = _accept_request(tenant, authority, actor, "Older busy request")
    for index in range(older_churn):
        older_version = _accepted_change(
            tenant,
            authority.prioritize(
                actor,
                RequestPriority(uuid4(), older_id, older_version, "P1", f"churn {index}"),
                telemetry=_telemetry(actor, uuid4()),
            ),
        ).version
    linked = _accepted_change(
        tenant,
        _relate(authority, actor, older_id, older_version, ticket_id, 1, active=True),
    )
    unlinked = _accepted_change(
        tenant,
        _relate(authority, actor, older_id, linked.version, ticket_id, 1, active=False),
    )
    print(f"OLDER released the ticket at request_version={unlinked.version + 1}")

    # Request B: a fresh, lower-versioned Request takes the released ticket.
    first_id, first_version = _accept_request(tenant, authority, actor, "First new request")
    first_link = _relate(authority, actor, first_id, first_version, ticket_id, 1, active=True)
    assert isinstance(first_link, RequestChangeResult), first_link
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    print(f"FIRST linked at request_version={first_link.version}")

    # Request C: a second competing Request asks for the SAME ticket.
    second_id, second_version = _accept_request(tenant, authority, actor, "Second new request")
    second_link = _relate(authority, actor, second_id, second_version, ticket_id, 1, active=True)
    assert isinstance(second_link, RecordProblem), (
        f"two Requests actively claim one fulfillment Ticket: {second_link!r}"
    )
    assert second_link.code == "request-transition-forbidden"

    # The database projection is the final chokepoint even if a future caller
    # bypasses the Work pre-check and appends a competing active fact directly.
    with (
        psycopg.connect(tenant.database.admin_dsn) as connection,
        pytest.raises(psycopg.errors.UniqueViolation),
    ):
        connection.execute(
            """
                INSERT INTO request_ticket_relation_facts (
                    relation_fact_id, request_id, tenant_id, request_version, ticket_id,
                    purpose, active, reason, recorded_by, command_id, recorded_at
                ) VALUES (%s, %s, %s, %s, %s, 'required', true, %s, %s, %s, %s)
                """,
            (
                uuid4(),
                second_id,
                tenant.tenant_id,
                second_version + 1,
                ticket_id,
                "database chokepoint probe",
                actor.principal_id,
                uuid4(),
                datetime.now(UTC),
            ),
        )

    # And can the legitimate holder release its own ticket?
    release = _relate(authority, actor, first_id, first_link.version, ticket_id, 1, active=False)
    assert isinstance(release, RequestChangeResult), release
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    listed = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(listed, RecordProblem)
    holders = [
        row.request_number for row in listed.rows if UUID(str(ticket_id)) in row.required_ticket_ids
    ]
    assert holders == []


def test_waiting_fulfillment_ticket_does_not_make_request_wip(tenant: TenantFixture) -> None:
    """Deferred-for-capacity Tickets leave an accepted Request TRIAGED, not WIP."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    ticket_id = _accepted_ticket(tenant, actor)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE lifecycle_episodes SET state = 'active'
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        )
    request_id, request_version = _accept_request(
        tenant, authority, actor, "Waiting fulfillment intent"
    )
    linked = _accepted_change(
        tenant,
        _relate(
            authority,
            actor,
            request_id,
            request_version,
            ticket_id,
            1,
            active=True,
        ),
    )
    assert linked.state == "WIP"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE lifecycle_episodes SET state = 'waiting'
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        )

    listed = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))

    assert not isinstance(listed, RecordProblem)
    row = next(item for item in listed.rows if item.request_id == request_id)
    assert row.state == "TRIAGED"
    assert row.proof_coverage == 0
