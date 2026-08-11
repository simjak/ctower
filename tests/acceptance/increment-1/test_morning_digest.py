"""Real-PostgreSQL acceptance for the native morning digest read-model."""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
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
HTTP_FORBIDDEN = 403
EXIT_SUCCESS = 0
EXPECTED_DECISION_CHOICES = 3
EXPECTED_PROOF_ROWS = 2
MAX_REQUEST_CONTENT = 65536
_VILNIUS = ZoneInfo("Europe/Vilnius")


def test_real_morning_digest_composes_record_derived_briefs_and_links(
    tenant: TenantFixture,
) -> None:
    """AC-DIG-01/02/03: one live artifact composes every accepted typed fact."""

    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    open_request_id, open_ticket_id = _blocked_request_with_proof(
        tenant,
        operator,
        commander,
        "X" * MAX_REQUEST_CONTENT,
    )
    executed_request_id, executed_ticket_id = _blocked_request_with_proof(
        tenant,
        operator,
        commander,
        "Choose whether the reviewed rollout should proceed.",
    )
    duplicate_note = _open_duplicate_pair(tenant, operator)
    ruling_id, ruling_recorded_at = _accepted_ruling(tenant, commander, executed_request_id)
    digest_date = (ruling_recorded_at.astimezone(_VILNIUS).date() + timedelta(days=1)).isoformat()
    position_before = _record_position(tenant)
    response, denied = _digest_responses(tenant, digest_date)

    assert response.status_code == HTTP_OK
    assert denied.status_code == HTTP_FORBIDDEN
    payload = cast(dict[str, object], response.json())
    decisions = cast(dict[str, object], payload["open_decisions"])
    yesterday = cast(dict[str, object], payload["yesterday_rulings"])
    proof = cast(dict[str, object], payload["proof"])
    near_duplicates = cast(dict[str, object], payload["near_duplicates"])
    assert near_duplicates["total_count"] == near_duplicates["visible_count"] == 1
    assert cast(list[dict[str, object]], near_duplicates["items"])[0]["note"] == duplicate_note
    _assert_digest_payload(
        payload,
        decisions,
        yesterday,
        proof,
        open_request_id,
        executed_request_id,
        ruling_id,
        (open_ticket_id, executed_ticket_id),
    )
    _assert_cli_transcript(
        tenant, digest_date, (open_ticket_id, executed_ticket_id), duplicate_note
    )
    assert _record_position(tenant) == position_before
    print(
        "REAL_MORNING_DIGEST"
        f" artifact={payload['artifact_key']} sha={payload['artifact_sha256']}"
        f" open_request={open_request_id} executed_request={executed_request_id}"
        f" ruling={ruling_id} proof={open_ticket_id},{executed_ticket_id}"
        f" state=complete cli=0 record_position={position_before}:unchanged"
    )


def _record_position(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(record_position), 0) FROM events WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _digest_responses(tenant: TenantFixture, digest_date: str) -> tuple[Response, Response]:
    operator_headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        **telemetry_headers(),
    }
    commander_headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        **telemetry_headers(),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.get(
            "/v1/digests/morning", params={"date": digest_date}, headers=operator_headers
        )
        denied = client.get(
            "/v1/digests/morning", params={"date": digest_date}, headers=commander_headers
        )
    return response, denied


def _assert_cli_transcript(
    tenant: TenantFixture,
    digest_date: str,
    ticket_ids: tuple[UUID, UUID],
    duplicate_note: str,
) -> None:
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
    assert "Open decisions — 1; COMPLETE" in transcript
    assert "Near-duplicate requests — 1; COMPLETE" in transcript
    assert duplicate_note in transcript
    assert "Executions:" in transcript
    assert "Executions: UNKNOWN" not in transcript
    assert "Proof — 2; COMPLETE" in transcript
    for ticket_id in ticket_ids:
        assert f"required: {ticket_id} /v1/tickets/{ticket_id}/timeline" in transcript


def _open_duplicate_pair(tenant: TenantFixture, operator: Actor) -> str:
    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    first = _accepted_request_capture(
        tenant,
        authority,
        operator,
        "Please show near-duplicate Requests in the morning digest.",
    )
    second = _accepted_request_capture(
        tenant,
        authority,
        operator,
        "Please show near duplicate Requests within the morning digest.",
    )
    assert second.resemblance is not None
    return (
        f"{second.reference} resembles {first.reference} (NEW) — "
        f"say same on {second.reference} to merge."
    )


def _accepted_request_capture(
    tenant: TenantFixture,
    authority: Requests,
    actor: Actor,
    text: str,
) -> RequestCaptureResult:
    command = RequestCapture(uuid4(), "ctower", text)
    result = authority.capture(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert isinstance(result, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    replay = authority.capture(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert isinstance(replay, RequestCaptureResult)
    return replay


def _assert_digest_payload(
    payload: dict[str, object],
    decisions: dict[str, object],
    yesterday: dict[str, object],
    proof: dict[str, object],
    open_request_id: UUID,
    executed_request_id: UUID,
    ruling_id: UUID,
    ticket_ids: tuple[UUID, UUID],
) -> None:
    decision_rows = cast(list[dict[str, object]], decisions["items"])
    ruling_rows = cast(list[dict[str, object]], yesterday["items"])
    proof_rows = cast(list[dict[str, object]], proof["items"])
    assert payload["state"] == "complete"
    assert decisions["total_count"] == decisions["visible_count"] == 1
    assert decisions["state"] == "complete"
    assert decision_rows[0]["request_id"] == str(open_request_id)
    assert decision_rows[0]["unknown_reason"] is None
    brief = cast(dict[str, object], decision_rows[0]["brief"])
    assert brief["what"] == "This Request needs your decision before work can continue."
    assert len(cast(str, brief["origin"])) == MAX_REQUEST_CONTENT
    assert len(cast(list[object], brief["choices"])) == EXPECTED_DECISION_CHOICES
    assert yesterday["total_count"] == yesterday["visible_count"] == 1
    assert ruling_rows[0]["ruling_id"] == str(ruling_id)
    assert ruling_rows[0]["unknown_reason"] is None
    executions = cast(list[dict[str, object]], ruling_rows[0]["executions"])
    assert executions[0]["request_id"] == str(executed_request_id)
    assert proof["state"] == "complete"
    assert proof["total_count"] == proof["visible_count"] == EXPECTED_PROOF_ROWS
    assert all(row["current_proof_count"] == 0 for row in proof_rows)
    links = [link for row in proof_rows for link in cast(list[dict[str, object]], row["tickets"])]
    assert links == [
        {
            "href": f"/v1/tickets/{ticket_id}/timeline",
            "purpose": "required",
            "ticket_id": str(ticket_id),
        }
        for ticket_id in ticket_ids
    ]


def _blocked_request_with_proof(
    tenant: TenantFixture,
    operator: Actor,
    commander: Actor,
    content: str,
) -> tuple[UUID, UUID]:
    requests = Requests(PostgresRequests(tenant.database.runtime_dsn))
    capture = RequestCapture(uuid4(), "ctower", content)
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


def _accepted_ruling(
    tenant: TenantFixture, actor: Actor, request_id: UUID
) -> tuple[UUID, datetime]:
    authority = Rulings(PostgresRulings(tenant.database.runtime_dsn))
    command = RulingAppend(uuid4(), "Use the 09:00 Vilnius rollout window.", request_id=request_id)
    outcome = authority.append(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert not isinstance(outcome, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome.ruling_id, outcome.recorded_at


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
