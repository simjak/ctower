"""Real PostgreSQL/API/CLI/Atom proof for CT-I1-027."""

from __future__ import annotations

import io
import json
from typing import cast
from uuid import UUID, uuid4

import feedparser  # type: ignore[import-untyped]
import httpx
import psycopg
import pytest
from support.server import running_api, start_and_admit
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    Priority,
    SourceReference,
    TicketCreateRequest,
    WorkflowTransitionRequest,
)
from ctowerctl import main

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNAUTHORIZED = 401
EXIT_SUCCESS = 0
_WORKFLOW_REF = "ctower.trust-spine-four-stage@1"


def test_real_movement_api_cli_atom_replay_refusal_and_validator(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    with running_api(tenant.database.runtime_dsn) as base_url:
        ticket_id = _exercise_transition(base_url, tenant, command_id)
        json_payload = _assert_http_and_atom(base_url, tenant, ticket_id)
        _assert_cli(base_url, tenant, json_payload)
    _assert_persistence(tenant, ticket_id)

    event = cast(list[dict[str, object]], json_payload["events"])[0]
    print(
        "REAL_TICKET_MOVEMENT"
        f" ticket={ticket_id} event={event['event_id']} position={event['record_position']}"
        f" evaluation_ref={event['evaluation_ref']}"
        " api=200 cli=0 atom=200 feedparser_bozo=False replay=exact refusal=version-conflict"
        " event_count=1"
    )


def _exercise_transition(base_url: str, tenant: TenantFixture, command_id: UUID) -> UUID:
    with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
        ticket = commander.create_ticket(
            TicketCreateRequest(
                initial_custodian_id=tenant.commander_id,
                priority=Priority.P1,
                project_key="ctower",
                source=SourceReference(kind="test", ref=f"movement:{uuid4()}"),
                title="Movement feed acceptance ticket",
            ),
            command_id=uuid4(),
        ).ticket
        start_and_admit(commander, ticket.ticket_id)
        request = WorkflowTransitionRequest(
            expected_version=1,
            workflow_ref=_WORKFLOW_REF,
            source_stage="capture",
            destination_stage="frame",
        )
        first = commander.transition_workflow(ticket.ticket_id, request, command_id=command_id)
        replay = commander.transition_workflow(ticket.ticket_id, request, command_id=command_id)
        page = commander.list_ticket_movement("ctower", cursor=0, limit=1)
        assert len(page.events) == 1
        event = page.events[0]
        assert event.ticket_id == ticket.ticket_id
        assert event.from_stage == "capture"
        assert event.to_stage == "frame"
        assert event.evaluation_ref is not None
        assert first.event_ids == replay.event_ids

        with pytest.raises(CtowerProblemError) as refused:
            commander.transition_workflow(ticket.ticket_id, request, command_id=uuid4())
        assert refused.value.problem.code == "version-conflict"
    return ticket.ticket_id


def _assert_http_and_atom(
    base_url: str,
    tenant: TenantFixture,
    ticket_id: UUID,
) -> dict[str, object]:
    operator_headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        **telemetry_headers(),
    }
    with httpx.Client(base_url=base_url) as http:
        json_page = http.get(
            "/v1/projects/ctower/movement",
            params={"cursor": 0, "limit": 1},
            headers=operator_headers,
        )
        assert json_page.status_code == HTTP_OK, json_page.text
        json_payload = cast(dict[str, object], json_page.json())

        atom = http.get(
            "/v1/projects/ctower/movement.atom",
            params={"cursor": 0, "limit": 1},
            headers=operator_headers,
        )
        assert atom.status_code == HTTP_OK, atom.text
        assert atom.headers["content-type"].startswith("application/atom+xml")
        parsed = feedparser.parse(atom.content)
        assert parsed.bozo is False
        assert len(parsed.entries) == 1
        event = cast(list[dict[str, object]], json_payload["events"])[0]
        assert parsed.entries[0].id == f"urn:uuid:{event['event_id']}"
        assert parsed.entries[0].updated.endswith("Z")
        assert parsed.entries[0].links[0].href.endswith(f"/v1/tickets/{ticket_id}/timeline")

        query_credential = http.get(
            "/v1/projects/ctower/movement",
            params={"token": tenant.operator_credential},
        )
        assert query_credential.status_code == HTTP_UNAUTHORIZED
        assert "events" not in query_credential.json()

        foreign_project = http.get(
            "/v1/projects/manibo/movement",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
        )
        assert foreign_project.status_code == HTTP_FORBIDDEN
        assert foreign_project.json()["code"] == "project-scope-denied"
    return json_payload


def _assert_cli(base_url: str, tenant: TenantFixture, expected: dict[str, object]) -> None:
    output = io.StringIO()
    errors = io.StringIO()
    status = main(
        ["--base-url", base_url, "project", "movement", "ctower", "--limit", "1"],
        stdin=io.StringIO(f"{tenant.operator_credential}\n"),
        stdout=output,
        stderr=errors,
    )
    assert status == EXIT_SUCCESS
    assert errors.getvalue() == ""
    assert json.loads(output.getvalue()) == expected


def _assert_persistence(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        event_count = connection.execute(
            """
            SELECT count(*)
            FROM events AS event
            JOIN event_links AS link ON link.event_id = event.event_id
            WHERE event.tenant_id = %s
              AND link.subject_id = %s
              AND event.kind = 'workflow.changed'
              AND event.payload->>'operation' = 'transition'
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
        payload_row = connection.execute(
            """
            SELECT payload->>'source_stage', payload->>'stage', payload->>'evaluation_ref'
            FROM events AS event
            JOIN event_links AS link ON link.event_id = event.event_id
            WHERE event.tenant_id = %s
              AND link.subject_id = %s
              AND event.kind = 'workflow.changed'
              AND event.payload->>'operation' = 'transition'
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
        assert payload_row is not None
        transition_row = connection.execute(
            """
            SELECT source_stage, destination_stage
            FROM workflow_transition_facts
            WHERE transition_id = %s
            """,
            (UUID(str(payload_row[2])),),
        ).fetchone()

    assert event_count is not None and int(event_count[0]) == 1
    assert payload_row == ("capture", "frame", payload_row[2])
    assert transition_row == ("capture", "frame")
