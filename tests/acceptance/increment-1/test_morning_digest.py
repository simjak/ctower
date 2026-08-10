"""Real-PostgreSQL acceptance for the native morning digest read-model."""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application, running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestBlocker,
    RequestCapture,
    RequestCaptureResult,
    RequestPriority,
    Requests,
    RequestTicketRelation,
    RequestTriage,
)
from ctower_kernel.work.rulings import PostgresRulings, RulingAppend, Rulings
from ctowerctl import main

__all__: tuple[str, ...] = ()

HTTP_OK = 200
EXIT_SUCCESS = 0
_VILNIUS = ZoneInfo("Europe/Vilnius")


def test_real_morning_digest_composes_live_records_and_renders_unknowns(
    tenant: TenantFixture,
) -> None:
    """AC-DIG-01/02/03: one live artifact has decisions, rulings, proof, and honest gaps."""

    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    request_id, ticket_id = _blocked_request_with_proof(tenant, operator, commander)
    ruling_id = _accepted_ruling(tenant, commander)
    digest_date = (datetime.now(_VILNIUS).date() + timedelta(days=1)).isoformat()
    headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        **telemetry_headers(),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.get("/v1/digests/morning", params={"date": digest_date}, headers=headers)

    assert response.status_code == HTTP_OK
    payload = cast(dict[str, object], response.json())
    decisions = cast(dict[str, object], payload["open_decisions"])
    yesterday = cast(dict[str, object], payload["yesterday_rulings"])
    proof = cast(dict[str, object], payload["proof"])
    _assert_digest_payload(payload, decisions, yesterday, proof, request_id, ruling_id, ticket_id)

    output = io.StringIO()
    errors = io.StringIO()
    with running_api(tenant.database.runtime_dsn) as base_url:
        status = main(
            ["--base-url", base_url, "digest", "morning", "--date", digest_date],
            stdin=io.StringIO(f"{tenant.operator_credential}\n"),
            stdout=output,
            stderr=errors,
        )
    transcript = output.getvalue()
    assert status == EXIT_SUCCESS
    assert errors.getvalue() == ""
    assert "Open decisions — 1; PARTIAL" in transcript
    assert "Executions: UNKNOWN (execution-link-not-recorded)" in transcript
    assert f"required: {ticket_id} /v1/tickets/{ticket_id}/timeline" in transcript
    print(
        "REAL_MORNING_DIGEST"
        f" artifact={payload['artifact_key']} sha={payload['artifact_sha256']}"
        f" request={request_id} ruling={ruling_id} proof={ticket_id}"
        " state=partial cli=0"
    )


def _assert_digest_payload(
    payload: dict[str, object],
    decisions: dict[str, object],
    yesterday: dict[str, object],
    proof: dict[str, object],
    request_id: UUID,
    ruling_id: UUID,
    ticket_id: UUID,
) -> None:
    decision_rows = cast(list[dict[str, object]], decisions["items"])
    ruling_rows = cast(list[dict[str, object]], yesterday["items"])
    proof_rows = cast(list[dict[str, object]], proof["items"])
    assert payload["state"] == "partial"
    assert decisions["total_count"] == decisions["visible_count"] == 1
    assert decision_rows[0]["request_id"] == str(request_id)
    assert decision_rows[0]["unknown_reason"] == "decision-brief-not-recorded"
    assert yesterday["total_count"] == yesterday["visible_count"] == 1
    assert ruling_rows[0]["ruling_id"] == str(ruling_id)
    assert ruling_rows[0]["unknown_reason"] == "execution-link-not-recorded"
    assert proof["total_count"] == proof["visible_count"] == 1
    links = cast(list[dict[str, object]], proof_rows[0]["tickets"])
    assert links == [
        {
            "href": f"/v1/tickets/{ticket_id}/timeline",
            "purpose": "required",
            "ticket_id": str(ticket_id),
        }
    ]


def _blocked_request_with_proof(
    tenant: TenantFixture, operator: Actor, commander: Actor
) -> tuple[UUID, UUID]:
    requests = Requests(PostgresRequests(tenant.database.runtime_dsn))
    capture = RequestCapture(uuid4(), "ctower", "Choose the production rollout window.")
    captured = requests.capture(
        operator, capture, telemetry=_telemetry(operator, capture.client_command_id)
    )
    assert isinstance(captured, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    priority = RequestPriority(
        uuid4(), captured.request_id, 1, "P2", "This Request needs operator review."
    )
    prioritized = requests.prioritize(
        commander, priority, telemetry=_telemetry(commander, priority.client_command_id)
    )
    assert not isinstance(prioritized, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    triage = RequestTriage(uuid4(), captured.request_id, 2, "ACCEPTED")
    triaged = requests.triage(
        commander, triage, telemetry=_telemetry(commander, triage.client_command_id)
    )
    assert not isinstance(triaged, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    ticket_id = _accepted_ticket(tenant, commander)
    relation = RequestTicketRelation(
        uuid4(),
        captured.request_id,
        3,
        1,
        ticket_id,
        "required",
        active=True,
        reason="This ticket executes the selected rollout.",
    )
    related = requests.relate_ticket(
        commander, relation, telemetry=_telemetry(commander, relation.client_command_id)
    )
    assert not isinstance(related, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    blocker = RequestBlocker(
        uuid4(),
        captured.request_id,
        4,
        "operator-decision-required",
        active=True,
        reason="The operator must select the rollout window.",
    )
    blocked = requests.set_blocker(
        commander, blocker, telemetry=_telemetry(commander, blocker.client_command_id)
    )
    assert not isinstance(blocked, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return captured.request_id, ticket_id


def _accepted_ticket(tenant: TenantFixture, actor: Actor) -> UUID:
    command = TicketCommand(
        client_command_id=uuid4(),
        initial_custodian_id=tenant.commander_id,
        priority="P2",
        project_key="ctower",
        source=SourceReference("morning-digest-test", f"ticket:{uuid4()}"),
        title="Execute the selected rollout window",
    )
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert not isinstance(outcome, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome.ticket.ticket_id


def _accepted_ruling(tenant: TenantFixture, actor: Actor) -> UUID:
    authority = Rulings(PostgresRulings(tenant.database.runtime_dsn))
    command = RulingAppend(uuid4(), "Use the 09:00 Vilnius rollout window.")
    outcome = authority.append(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert not isinstance(outcome, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome.ruling_id


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
