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
from ctower_kernel.projections import ProjectionHealth, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctowerctl import main

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNAUTHORIZED = 401
EXIT_SUCCESS = 0
_WORKFLOW_REF = "ctower.trust-spine-four-stage@1"
_CURSOR_ONE = 1
_CURSOR_LIMIT = 2
_CURSOR_LIMIT_PLUS_ONE = 3


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


def test_pre_enrichment_event_is_tolerated_by_rebuild_and_all_read_boundaries(
    tenant: TenantFixture,
) -> None:
    with running_api(tenant.database.runtime_dsn) as base_url:
        ticket_id = _exercise_transition(base_url, tenant, uuid4())
        _remove_transition_provenance(tenant, ticket_id)

        rebuilt = Projections(PostgresProjections(tenant.database.projection_dsn)).rebuild(
            tenant.tenant_id
        )
        assert rebuilt.health is ProjectionHealth.CURRENT

        headers = {
            "Authorization": f"Bearer {tenant.operator_credential}",
            **telemetry_headers(),
        }
        with httpx.Client(base_url=base_url) as http:
            project_events = http.get(
                "/v1/projects/ctower/events",
                params={"cursor": 0, "limit": 100},
                headers=headers,
            )
            assert project_events.status_code == HTTP_OK, project_events.text
            project_event = _workflow_event_from_page(project_events.json())
            project_payload = cast(dict[str, object], project_event["payload"])
            assert project_payload["source_stage"] == ""
            assert project_payload["evaluation_ref"] == ""

            audit = http.get(
                f"/v1/tickets/{ticket_id}/audit",
                params={"project_key": "ctower", "cursor": 0, "limit": 100},
                headers=headers,
            )
            assert audit.status_code == HTTP_OK, audit.text
            audit_event = _workflow_event_from_page(audit.json())
            audit_payload = cast(dict[str, object], audit_event["payload"])
            assert audit_payload["source_stage"] == ""
            assert audit_payload["evaluation_ref"] == ""

            timeline = http.get(
                f"/v1/tickets/{ticket_id}/timeline",
                params={"project_key": "ctower"},
                headers=headers,
            )
            assert timeline.status_code == HTTP_OK, timeline.text

            movement = http.get(
                "/v1/projects/ctower/movement",
                params={"cursor": 0, "limit": 100},
                headers=headers,
            )
            assert movement.status_code == HTTP_OK, movement.text
            movement_event = cast(list[dict[str, object]], movement.json()["events"])[0]
            assert movement_event["from_stage"] == ""
            assert movement_event["evaluation_ref"] == ""

            digest = http.get(
                "/v1/digests/morning",
                params={"date": "2026-08-10"},
                headers=headers,
            )
            assert digest.status_code == HTTP_OK, digest.text
            movement_summary = cast(dict[str, object], digest.json()["movement"])
            assert movement_summary["source_state"] == "partial"
            assert "movement:pre-enrichment-provenance" in cast(
                list[str], movement_summary["unreached_scopes"]
            )


def test_movement_cursor_zero_one_limit_limit_plus_one_and_rebuild_are_byte_stable(
    tenant: TenantFixture,
) -> None:
    with running_api(tenant.database.runtime_dsn) as base_url:
        _seed_transition_events(base_url, tenant, count=3)
        headers = {
            "Authorization": f"Bearer {tenant.operator_credential}",
            **telemetry_headers(),
        }
        with httpx.Client(base_url=base_url) as http:
            page_zero_one = _get_movement_page(http, headers, cursor=0, limit=1)
            first_position = cast(
                int,
                cast(list[dict[str, object]], page_zero_one["events"])[0]["record_position"],
            )
            page_after_first = _get_movement_page(http, headers, cursor=first_position, limit=1)
            page_limit = _get_movement_page(http, headers, cursor=0, limit=_CURSOR_LIMIT)
            page_limit_plus_one = _get_movement_page(
                http, headers, cursor=0, limit=_CURSOR_LIMIT_PLUS_ONE
            )

            assert len(cast(list[object], page_zero_one["events"])) == _CURSOR_ONE
            assert page_zero_one["next_cursor"] is not None
            assert len(cast(list[object], page_after_first["events"])) == _CURSOR_ONE
            assert page_after_first["next_cursor"] is not None
            assert len(cast(list[object], page_limit["events"])) == _CURSOR_LIMIT
            assert page_limit["next_cursor"] is not None
            assert len(cast(list[object], page_limit_plus_one["events"])) == _CURSOR_LIMIT_PLUS_ONE
            assert page_limit_plus_one["next_cursor"] is None

            before_rebuild_response = http.get(
                "/v1/projects/ctower/movement",
                params={"cursor": 0, "limit": _CURSOR_LIMIT},
                headers=headers,
            )
            assert before_rebuild_response.status_code == HTTP_OK, before_rebuild_response.text
            rebuilt = Projections(PostgresProjections(tenant.database.projection_dsn)).rebuild(
                tenant.tenant_id
            )
            assert rebuilt.health is ProjectionHealth.CURRENT
            after_rebuild_response = http.get(
                "/v1/projects/ctower/movement",
                params={"cursor": 0, "limit": _CURSOR_LIMIT},
                headers=headers,
            )
            assert after_rebuild_response.status_code == HTTP_OK, after_rebuild_response.text

    assert after_rebuild_response.content == before_rebuild_response.content


def test_movement_api_cli_digest_atom_share_one_watermark_and_reject_stale_cursor(
    tenant: TenantFixture,
) -> None:
    with running_api(tenant.database.runtime_dsn) as base_url:
        _seed_transition_events(base_url, tenant, count=2)
        source_watermark, expected_event_ids = _movement_events_at_watermark(tenant)
        headers = {
            "Authorization": f"Bearer {tenant.operator_credential}",
            **telemetry_headers(),
        }
        with httpx.Client(base_url=base_url) as http:
            api_page = _get_movement_page(http, headers, cursor=0, limit=100)
            api_event_ids = tuple(
                str(event["event_id"])
                for event in cast(list[dict[str, object]], api_page["events"])
            )

            atom = http.get(
                "/v1/projects/ctower/movement.atom",
                params={"cursor": 0, "limit": 100},
                headers=headers,
            )
            assert atom.status_code == HTTP_OK, atom.text
            parsed = feedparser.parse(atom.content)
            assert parsed.bozo is False
            atom_event_ids = tuple(
                str(entry.id).removeprefix("urn:uuid:") for entry in parsed.entries
            )

            digest = http.get(
                "/v1/digests/morning",
                params={"date": "2026-08-10"},
                headers=headers,
            )
            assert digest.status_code == HTTP_OK, digest.text
            movement = cast(dict[str, object], digest.json()["movement"])
            assert movement["watermark"] == source_watermark

            stale = _get_movement_page(http, headers, cursor=source_watermark + 1, limit=100)
            assert stale["events"] == []
            assert stale["next_cursor"] is None

        cli_output = io.StringIO()
        cli_errors = io.StringIO()
        cli_status = main(
            ["--base-url", base_url, "project", "movement", "ctower", "--limit", "100"],
            stdin=io.StringIO(f"{tenant.operator_credential}\n"),
            stdout=cli_output,
            stderr=cli_errors,
        )
        assert cli_status == EXIT_SUCCESS
        assert cli_errors.getvalue() == ""
        cli_page = cast(dict[str, object], json.loads(cli_output.getvalue()))
        cli_event_ids = tuple(
            str(event["event_id"]) for event in cast(list[dict[str, object]], cli_page["events"])
        )

    assert api_event_ids == cli_event_ids == atom_event_ids == expected_event_ids


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


def _seed_transition_events(base_url: str, tenant: TenantFixture, *, count: int) -> None:
    with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
        for index in range(count):
            ticket = commander.create_ticket(
                TicketCreateRequest(
                    initial_custodian_id=tenant.commander_id,
                    priority=Priority.P1,
                    project_key="ctower",
                    source=SourceReference(kind="test", ref=f"movement-page:{index}:{uuid4()}"),
                    title=f"Movement page fixture {index}",
                ),
                command_id=uuid4(),
            ).ticket
            start_and_admit(commander, ticket.ticket_id)
            commander.transition_workflow(
                ticket.ticket_id,
                WorkflowTransitionRequest(
                    expected_version=1,
                    workflow_ref=_WORKFLOW_REF,
                    source_stage="capture",
                    destination_stage="frame",
                ),
                command_id=uuid4(),
            )


def _get_movement_page(
    http: httpx.Client,
    headers: dict[str, str],
    *,
    cursor: int,
    limit: int,
) -> dict[str, object]:
    response = http.get(
        "/v1/projects/ctower/movement",
        params={"cursor": cursor, "limit": limit},
        headers=headers,
    )
    assert response.status_code == HTTP_OK, response.text
    return cast(dict[str, object], response.json())


def _movement_events_at_watermark(tenant: TenantFixture) -> tuple[int, tuple[str, ...]]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        watermark_row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
        assert watermark_row is not None
        watermark = int(cast(int, watermark_row[0]))
        rows = connection.execute(
            """
            SELECT event.event_id
            FROM event_links AS link
            JOIN events AS event ON event.tenant_id = link.tenant_id
                AND event.event_id = link.event_id
            JOIN tickets AS ticket ON ticket.tenant_id = link.tenant_id
                AND ticket.ticket_id = link.subject_id
            WHERE link.tenant_id = %s
              AND link.subject_kind = 'ticket'
              AND ticket.project_key = 'ctower'
              AND event.kind = 'workflow.changed'
              AND event.payload->>'operation' = 'transition'
              AND event.record_position <= %s
            ORDER BY event.record_position
            """,
            (tenant.tenant_id, watermark),
        ).fetchall()
    return watermark, tuple(str(row[0]) for row in rows)


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
        assert b"<author><name>ctower</name></author>" in atom.content
        parsed = feedparser.parse(atom.content)
        assert parsed.bozo is False
        assert len(parsed.entries) == 1
        event = cast(list[dict[str, object]], json_payload["events"])[0]
        assert parsed.entries[0].id == f"urn:uuid:{event['event_id']}"
        assert parsed.entries[0].updated.endswith("Z")
        alternate = next(link.href for link in parsed.entries[0].links if link.rel == "alternate")
        assert alternate == f"/v1/tickets/{ticket_id}/timeline?project_key=ctower"
        linked = http.get(alternate, headers=operator_headers)
        assert linked.status_code == HTTP_OK, linked.text

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


def _remove_transition_provenance(tenant: TenantFixture, ticket_id: UUID) -> None:
    """Emulate a stored pre-enrichment event without changing its event identity."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE events AS event
            SET payload = event.payload - 'source_stage' - 'evaluation_ref'
            FROM event_links AS link
            WHERE link.tenant_id = event.tenant_id
              AND link.event_id = event.event_id
              AND link.subject_id = %s
              AND event.tenant_id = %s
              AND event.kind = 'workflow.changed'
              AND event.payload->>'operation' = 'transition'
            """,
            (ticket_id, tenant.tenant_id),
        )


def _workflow_event_from_page(payload: object) -> dict[str, object]:
    page = cast(dict[str, object], payload)
    events = cast(list[dict[str, object]], page["events"])
    return next(event for event in events if event["kind"] == "workflow.changed")
