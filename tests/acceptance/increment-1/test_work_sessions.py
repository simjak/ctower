"""Recorded work sessions: the fact the ticket timeline, workspace, and feed wait on.

Every assertion here is behavioral: a ticket with real sessions returns them ordered with
seat, model, duration, tokens, and outcome; a foreign project cannot read them; and a
session payload carrying prohibited content never reaches the Record.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from itertools import permutations
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
_PROJECTS = ("ctower", "manibo", "bh-loop")

# Each probe carries a canary that exists nowhere else, so a durable-byte scan proves the
# whole session command was dropped rather than only its recognized fragment.
_PROHIBITED_PROBES: tuple[tuple[str, str, str, str], ...] = (
    (
        "credential_material",
        "worktree_ref",
        "/srv/worktrees/session-canary-6f70 password = notarealsecret",
        "session-canary-6f70",
    ),
    (
        "phi_hipaa_covered",
        "branch_ref",
        "feat/session-canary-7a81-patient-intake-clinical-export",
        "session-canary-7a81",
    ),
)


def test_ticket_returns_its_sessions_ordered_with_seat_model_duration_tokens_and_outcome(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ticket_id = _seat_ticket(client, tenant, "ctower", credential, "R2698-G5")
        first = _start(client, credential, ticket_id, crew_name="engineer-g5-sessions")
        _fact(
            client,
            credential,
            ticket_id,
            first,
            {"kind": "transition", "reason": "Brief read", "to_state": "briefed"},
        )
        _fact(
            client,
            credential,
            ticket_id,
            first,
            {"kind": "transition", "reason": "Building", "to_state": "working"},
        )
        closed = _fact(
            client,
            credential,
            ticket_id,
            first,
            {
                "kind": "close",
                "evidence_ref": "pr:simjak/ctower#200",
                "input_tokens": 412_000,
                "outcome": "delivered",
                "output_tokens": 38_500,
            },
        )
        second = _start(client, credential, ticket_id, crew_name="review-g5-sessions")
        listed = _ticket_sessions(client, credential, ticket_id, "ctower")

    assert closed.status_code == HTTP_PENDING
    assert listed.status_code == HTTP_OK
    sessions = cast(list[dict[str, object]], listed.json()["sessions"])
    assert [session["session_id"] for session in sessions] == [str(first), str(second)]
    assert sessions[0] == _delivered_session(
        sessions[0],
        session_id=first,
        ticket_id=ticket_id,
        duration_seconds=_recorded_duration(tenant, first),
    )
    assert sessions[1]["state"] == "dispatched"
    assert (
        sessions[1]["outcome"],
        sessions[1]["duration_seconds"],
        sessions[1]["tokens"],
        sessions[1]["closed_at"],
    ) == (None, None, None, None)
    assert _session_event_kinds(tenant, first) == [
        "session.started",
        "session.transitioned",
        "session.transitioned",
        "session.closed",
    ]


def test_session_events_reach_the_ticket_audit_stream(tenant: TenantFixture) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ticket_id = _seat_ticket(client, tenant, "ctower", credential, "R2698-G5-audit")
        session_id = _start(client, credential, ticket_id, crew_name="engineer-g5-sessions")
        audit = cast(
            Response,
            client.get(
                f"/v1/tickets/{ticket_id}/audit",
                params={"project_key": "ctower"},
                headers=_auth(credential),
            ),
        )

    assert audit.status_code == HTTP_OK
    events = cast(list[dict[str, object]], audit.json()["events"])
    started = next(event for event in events if event["kind"] == "session.started")
    assert started["stream_id"] == f"session:{session_id}"
    assert cast(dict[str, object], started["payload"])["crew_name"] == "engineer-g5-sessions"


def test_all_three_project_pairs_refuse_a_foreign_session_read_by_name(
    tenant: TenantFixture,
) -> None:
    credentials = {project: secrets.token_urlsafe(32) for project in _PROJECTS}
    with _client(tenant) as client:
        tickets = {
            project: _seat_ticket(client, tenant, project, credentials[project], f"{project}-R200")
            for project in _PROJECTS
        }
        for project in _PROJECTS:
            _start(client, credentials[project], tickets[project], crew_name=f"{project}-crew")
        ticket_reads = {
            (source, target): _ticket_sessions(client, credentials[source], tickets[target], source)
            for source, target in permutations(_PROJECTS, 2)
        }
        project_reads = {
            (source, target): cast(
                Response,
                client.get(
                    f"/v1/projects/{target}/sessions",
                    headers=_auth(credentials[source]),
                ),
            )
            for source, target in permutations(_PROJECTS, 2)
        }
        own = {
            project: cast(
                Response,
                client.get(
                    f"/v1/projects/{project}/sessions",
                    headers=_auth(credentials[project]),
                ),
            )
            for project in _PROJECTS
        }

    assert {
        pair: (response.status_code, response.json().get("code"))
        for pair, response in ticket_reads.items()
    } == dict.fromkeys(ticket_reads, (HTTP_NOT_FOUND, "tenant-scope-denied"))
    assert {
        pair: (response.status_code, response.json().get("code"))
        for pair, response in project_reads.items()
    } == dict.fromkeys(project_reads, (HTTP_FORBIDDEN, "project-scope-denied"))
    for project, response in own.items():
        assert response.status_code == HTTP_OK, response.text
        page = response.json()
        assert page["project_key"] == project
        assert {session["project_key"] for session in page["sessions"]} == {project}
        assert page["next_cursor"] is None


@pytest.mark.parametrize(("prohibited_class", "field", "value", "canary"), _PROHIBITED_PROBES)
def test_a_session_payload_carrying_a_prohibited_class_is_refused_by_name(
    tenant: TenantFixture,
    prohibited_class: str,
    field: str,
    value: str,
    canary: str,
) -> None:
    credential = secrets.token_urlsafe(32)
    command_id = uuid4()
    with _client(tenant) as client:
        ticket_id = _seat_ticket(client, tenant, "ctower", credential, f"R200-{field}")
        refused = cast(
            Response,
            client.post(
                f"/v1/tickets/{ticket_id}/sessions",
                json={**_start_body("engineer-g5-sessions"), field: value},
                headers={**_auth(credential), "Idempotency-Key": str(command_id)},
            ),
        )

    problem = cast(dict[str, object], refused.json())
    assert refused.status_code == HTTP_UNPROCESSABLE
    assert problem["code"] == "prohibited-data-class"
    assert problem["prohibited_classes"] == [prohibited_class]
    assert problem["command_id"] == str(command_id)
    assert _durable_occurrences(tenant, canary) == 0


def test_a_prohibited_transition_reason_never_reaches_a_live_session(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ticket_id = _seat_ticket(client, tenant, "ctower", credential, "R200-reason")
        session_id = _start(client, credential, ticket_id, crew_name="engineer-g5-sessions")
        refused = _fact(
            client,
            credential,
            ticket_id,
            session_id,
            {
                "kind": "transition",
                "reason": "session-canary-8b92 the patient export blocked the run",
                "to_state": "briefed",
            },
        )
        listed = _ticket_sessions(client, credential, ticket_id, "ctower")

    assert refused.status_code == HTTP_UNPROCESSABLE
    assert refused.json()["prohibited_classes"] == ["phi_hipaa_covered"]
    assert cast(list[dict[str, object]], listed.json()["sessions"])[0]["transition_count"] == 0
    assert _durable_occurrences(tenant, "session-canary-8b92") == 0


def test_the_session_lifecycle_refuses_an_unauthored_move_and_a_post_close_fact(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ticket_id = _seat_ticket(client, tenant, "ctower", credential, "R200-lifecycle")
        session_id = _start(client, credential, ticket_id, crew_name="engineer-g5-sessions")
        skipped = _fact(
            client,
            credential,
            ticket_id,
            session_id,
            {"kind": "transition", "reason": "Skip the brief", "to_state": "working"},
        )
        unknown = _fact(
            client,
            credential,
            ticket_id,
            uuid4(),
            {"kind": "transition", "reason": "No such session", "to_state": "briefed"},
        )
        _fact(
            client,
            credential,
            ticket_id,
            session_id,
            {
                "kind": "close",
                "evidence_ref": None,
                "input_tokens": 0,
                "outcome": "abandoned",
                "output_tokens": 0,
            },
        )
        after_close = _fact(
            client,
            credential,
            ticket_id,
            session_id,
            {"kind": "transition", "reason": "Late move", "to_state": "briefed"},
        )
        listed = _ticket_sessions(client, credential, ticket_id, "ctower")

    assert (skipped.status_code, skipped.json()["code"]) == (
        HTTP_CONFLICT,
        "session-transition-invalid",
    )
    assert (unknown.status_code, unknown.json()["code"]) == (HTTP_NOT_FOUND, "session-not-found")
    assert (after_close.status_code, after_close.json()["code"]) == (
        HTTP_CONFLICT,
        "session-ineligible",
    )
    session = cast(list[dict[str, object]], listed.json()["sessions"])[0]
    assert (session["state"], session["outcome"], session["transition_count"]) == (
        "dispatched",
        "abandoned",
        0,
    )


def test_the_project_page_cursors_without_repeating_or_skipping_a_session(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ticket_id = _seat_ticket(client, tenant, "ctower", credential, "R200-cursor")
        started = [
            _start(client, credential, ticket_id, crew_name=f"engineer-page-{index}")
            for index in range(3)
        ]
        pages: list[dict[str, object]] = []
        cursor: int | None = 0
        while cursor is not None:
            response = cast(
                Response,
                client.get(
                    "/v1/projects/ctower/sessions",
                    params={"cursor": cursor, "limit": 1},
                    headers=_auth(credential),
                ),
            )
            assert response.status_code == HTTP_OK, response.text
            page = cast(dict[str, object], response.json())
            pages.append(page)
            cursor = cast(int | None, page["next_cursor"])
        invalid = cast(
            Response,
            client.get(
                "/v1/projects/ctower/sessions",
                params={"limit": 101},
                headers=_auth(credential),
            ),
        )

    walked = [
        session["session_id"]
        for page in pages
        for session in cast(list[dict[str, object]], page["sessions"])
    ]
    assert walked == [str(session_id) for session_id in started]
    assert (invalid.status_code, invalid.json()["code"]) == (HTTP_UNPROCESSABLE, "validation-error")


def _delivered_session(
    observed: dict[str, object],
    *,
    session_id: UUID,
    ticket_id: UUID,
    duration_seconds: int,
) -> dict[str, object]:
    """The exact body a closed session must return, cost facts and all.

    Only the two Record-owned timestamps are read back from the observed body; every
    other member is stated here, so a dropped or invented field fails the comparison.
    """

    return {
        "branch_ref": "feat/200-session-facts",
        "closed_at": observed["closed_at"],
        "crew_name": "engineer-g5-sessions",
        "duration_seconds": duration_seconds,
        "evidence_ref": "pr:simjak/ctower#200",
        "harness_ref": "claude-code",
        "model_ref": "claude-opus-5",
        "outcome": "delivered",
        "project_key": "ctower",
        "seat_key": "engineer",
        "session_id": str(session_id),
        "started_at": observed["started_at"],
        "state": "working",
        "ticket_id": str(ticket_id),
        "tokens": {"input_tokens": 412_000, "output_tokens": 38_500, "total_tokens": 450_500},
        "transition_count": 2,
        "worktree_ref": "/srv/projects/ctower/.worktrees/g5-sessions",
    }


def _seat_ticket(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
    credential: str,
    source_ref: str,
) -> UUID:
    issued = cast(
        Response,
        client.post(
            "/v1/admin/seat-credentials",
            json={
                "credential_digest": f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}",
                "credential_ref": f"secret-ref:test/{project_key}/session-seat",
                "display_name": f"{project_key.title()} Session Commander",
                "project_key": project_key,
                "scopes": ["capture", "transition", "evidence"],
                "seat_key": f"{project_key}-session-seat",
            },
            headers={
                **_auth(tenant.operator_credential),
                "Idempotency-Key": str(uuid4()),
            },
        ),
    )
    assert issued.status_code == HTTP_PENDING, issued.text
    created = cast(
        Response,
        client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": issued.json()["principal_id"],
                "priority": "P1",
                "source": {"kind": "dogfood-gap", "ref": source_ref},
                "title": f"{project_key} work-session target",
            },
            headers={
                **_auth(tenant.operator_credential),
                "Idempotency-Key": str(uuid4()),
            },
        ),
    )
    assert created.status_code == HTTP_PENDING, created.text
    return UUID(str(created.json()["ticket"]["ticket_id"]))


def _start_body(crew_name: str) -> dict[str, str]:
    return {
        "branch_ref": "feat/200-session-facts",
        "crew_name": crew_name,
        "harness_ref": "claude-code",
        "model_ref": "claude-opus-5",
        "seat_key": "engineer",
        "worktree_ref": "/srv/projects/ctower/.worktrees/g5-sessions",
    }


def _start(client: TestClient, credential: str, ticket_id: UUID, *, crew_name: str) -> UUID:
    response = cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/sessions",
            json=_start_body(crew_name),
            headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
        ),
    )
    assert response.status_code == HTTP_PENDING, response.text
    assert response.json()["state"] == "dispatched"
    return UUID(str(response.json()["session_id"]))


def _fact(
    client: TestClient,
    credential: str,
    ticket_id: UUID,
    session_id: UUID,
    body: dict[str, object],
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/sessions/{session_id}/facts",
            json={"fact": body},
            headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
        ),
    )


def _ticket_sessions(
    client: TestClient, credential: str, ticket_id: UUID, project_key: str
) -> Response:
    return cast(
        Response,
        client.get(
            f"/v1/tickets/{ticket_id}/sessions",
            params={"project_key": project_key},
            headers=_auth(credential),
        ),
    )


def _recorded_duration(tenant: TenantFixture, session_id: UUID) -> int:
    """The Record's own duration: the committed close time minus the committed start."""

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT kind, server_time FROM events
            WHERE stream_id = %s ORDER BY sequence
            """,
            (f"session:{session_id}",),
        ).fetchall()
    times = {str(row["kind"]): cast(datetime, row["server_time"]) for row in rows}
    return int((times["session.closed"] - times["session.started"]).total_seconds())


def _session_event_kinds(tenant: TenantFixture, session_id: UUID) -> list[str]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT kind FROM events WHERE stream_id = %s ORDER BY sequence",
            (f"session:{session_id}",),
        ).fetchall()
    return [str(row["kind"]) for row in rows]


def _durable_occurrences(tenant: TenantFixture, canary: str) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counted = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM events WHERE payload::text LIKE %s)
                + (SELECT count(*) FROM outbox WHERE payload::text LIKE %s)
                + (SELECT count(*) FROM ticket_work_sessions
                   WHERE worktree_ref LIKE %s OR branch_ref LIKE %s)
                + (SELECT count(*) FROM ticket_work_session_transitions WHERE reason LIKE %s)
            """,
            (f"%{canary}%",) * 5,
        ).fetchone()
    assert counted is not None
    return int(counted[0])


def _auth(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}", **telemetry_headers()}


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(tenant.database.runtime_dsn)),
        ),
        client=("127.0.0.1", 51000),
    )
