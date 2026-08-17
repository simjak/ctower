"""Ticket creation, replay, read, and timeline acceptance evidence."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeGuard, cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from jsonschema import Draft202012Validator
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_PENDING = 202
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
ROOT = Path(__file__).parents[3]


def test_project_scoped_ticket_reads_require_the_persisted_project_grant(
    tenant: TenantFixture,
) -> None:
    title = "R3002 cross-project Ticket text canary"
    with _client(tenant) as client:
        ticket_id, created = _create_project_read_ticket(client, tenant, title=title)
        authorized_credential, foreign_credential, revoked_credential, revoked_id = (
            _issue_project_read_credentials(client, tenant)
        )
        read_paths = _project_ticket_read_paths(ticket_id)
        authorized = _read_ticket_paths(client, read_paths, credential=authorized_credential)
        foreign = _read_ticket_paths(client, read_paths, credential=foreign_credential)
        anonymous = _read_ticket_paths(client, read_paths)
        query_token = _read_ticket_paths(
            client, read_paths, extra_params={"token": "r3002-query-token-canary"}
        )
        feed_token = _read_ticket_paths(
            client, read_paths, extra_params={"feed_token": "r3002-feed-token-canary"}
        )
        revoked_response = client.post(
            f"/v1/admin/seat-credentials/{revoked_id}/revocation",
            json={"reason": "R3002 read authorization probe"},
            headers={**_auth(tenant.operator_credential), "Idempotency-Key": str(uuid4())},
        )
        revoked_reads = _read_ticket_paths(client, read_paths, credential=revoked_credential)

    assert created.status_code == HTTP_PENDING
    assert revoked_response.status_code == HTTP_PENDING
    assert all(response.status_code == HTTP_OK for response in authorized)
    _assert_foreign_denied(foreign, ticket_id, title)
    _assert_unauthenticated(anonymous + query_token + feed_token + revoked_reads, ticket_id, title)


def test_persisted_operator_with_empty_binding_reads_all_ticket_surfaces(
    tenant: TenantFixture,
) -> None:
    record = PostgresRecord(tenant.database.runtime_dsn)
    with _client(tenant) as client:
        created = _create_ticket(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            custodian_id=tenant.commander_id,
            priority="P1",
            title="R3002 persisted operator canary",
        )
    assert created.status_code == HTTP_PENDING
    ticket_id = UUID(created.json()["ticket"]["ticket_id"])
    actor = _persisted_operator_session(record, tenant)
    work = Work(record, writer=PostgresWork(tenant.database.runtime_dsn))

    assert actor.kind is PrincipalKind.OPERATOR
    assert actor.project_grants == frozenset()
    for outcome in _record_ticket_read_surfaces(record, work, actor, ticket_id):
        assert not isinstance(outcome, RecordProblem), outcome


def test_disabled_persisted_operator_is_refused_on_all_ticket_surfaces(
    tenant: TenantFixture,
) -> None:
    record = PostgresRecord(tenant.database.runtime_dsn)
    with _client(tenant) as client:
        title = "R2-2 disabled operator canary"
        created = _create_ticket(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            custodian_id=tenant.commander_id,
            priority="P1",
            title=title,
        )
    assert created.status_code == HTTP_PENDING
    ticket_id = UUID(created.json()["ticket"]["ticket_id"])
    actor = _persisted_operator_session(record, tenant)
    assert actor.human_binding_id is not None
    assert actor.human_session_id is not None

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE principals SET disabled = true WHERE tenant_id = %s AND principal_id = %s",
            (tenant.tenant_id, actor.principal_id),
        )

    work = Work(record, writer=PostgresWork(tenant.database.runtime_dsn))
    outcomes = _record_ticket_read_surfaces(record, work, actor, ticket_id)
    for raw_outcome in outcomes:
        if not _is_record_problem(raw_outcome):
            raise AssertionError(raw_outcome)
        outcome = raw_outcome
        assert outcome.code == "project-scope-denied"
        assert outcome.status == HTTP_FORBIDDEN
        payload = json.dumps(outcome.response_payload())
        assert str(ticket_id) not in payload
        assert title not in payload


def test_p0_p1_p2_source_initial_custodian_reads_and_timeline(tenant: TenantFixture) -> None:
    with _client(tenant) as client:
        responses = tuple(
            _create_ticket(
                client,
                tenant.operator_credential,
                command_id=uuid4(),
                custodian_id=tenant.commander_id,
                priority=priority,
                title=f"{priority} durable ticket",
                source_ref=f"mission-control:{priority.lower()}",
            )
            for priority in ("P0", "P1", "P2")
        )
        for priority, response in zip(("P0", "P1", "P2"), responses, strict=True):
            assert response.status_code == HTTP_PENDING
            created = response.json()
            ticket = created["ticket"]
            assert created["durability_state"] == "durability_pending"
            assert ticket["priority"] == priority
            assert ticket["custodian_id"] == str(tenant.commander_id)
            assert ticket["source"] == {
                "kind": "mission-control",
                "ref": f"mission-control:{priority.lower()}",
            }
            shown = client.get(
                f"/v1/tickets/{ticket['ticket_id']}",
                params={"project_key": "ctower"},
                headers=_auth(tenant.operator_credential),
            )
            timeline = client.get(
                f"/v1/tickets/{ticket['ticket_id']}/timeline",
                params={"project_key": "ctower"},
                headers=_auth(tenant.operator_credential),
            )
            assert shown.status_code == HTTP_OK
            assert shown.json() == ticket
            assert timeline.status_code == HTTP_OK
            assert timeline.json()["durability_state"] == "durability_pending"
            assert [event["kind"] for event in timeline.json()["events"]] == ["ticket.created"]
            assert (
                timeline.json()["events"][0]["payload"]["source_kind"] == ticket["source"]["kind"]
            )
            assert timeline.json()["events"][0]["payload"]["source_ref"] == ticket["source"]["ref"]
    _assert_ticket_facts(tenant.database.admin_dsn, expected=3)


def test_exact_replay_changed_body_conflict_and_ineligible_custodian(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    with _client(tenant) as client:
        first = _create_ticket(
            client,
            tenant.operator_credential,
            command_id=command_id,
            custodian_id=tenant.commander_id,
            priority="P1",
            title="Replayable ticket",
        )
        replay = _create_ticket(
            client,
            tenant.operator_credential,
            command_id=command_id,
            custodian_id=tenant.commander_id,
            priority="P1",
            title="Replayable ticket",
        )
        changed = _create_ticket(
            client,
            tenant.operator_credential,
            command_id=command_id,
            custodian_id=tenant.commander_id,
            priority="P1",
            title="Changed body",
        )
        _assert_ineligible_refused(client, tenant)

    assert first.status_code == HTTP_PENDING
    assert replay.content == first.content
    assert replay.json()["event_ids"] == first.json()["event_ids"]
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    _assert_ticket_facts(tenant.database.admin_dsn, expected=1)


def test_p0_is_operator_only_while_commander_can_create_p1(tenant: TenantFixture) -> None:
    with _client(tenant) as client:
        refused = _create_ticket(
            client,
            tenant.commander_credential,
            command_id=uuid4(),
            custodian_id=tenant.commander_id,
            priority="P0",
            title="Commander P0 refused",
        )
        accepted = _create_ticket(
            client,
            tenant.commander_credential,
            command_id=uuid4(),
            custodian_id=tenant.commander_id,
            priority="P1",
            title="Commander P1 accepted",
        )

    assert refused.status_code == HTTP_FORBIDDEN
    assert refused.json()["code"] == "unauthorized"
    assert accepted.status_code == HTTP_PENDING
    _assert_ticket_facts(tenant.database.admin_dsn, expected=1)


def test_runtime_event_schema_hash_outbox_and_public_timeline_are_one_shape(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    with _client(tenant) as client:
        created = _create_ticket(
            client,
            tenant.operator_credential,
            command_id=command_id,
            custodian_id=tenant.commander_id,
            priority="P1",
            title="Canonical runtime event",
            source_ref="canonical:runtime",
        )
        ticket_id = UUID(created.json()["ticket"]["ticket_id"])
        timeline = client.get(
            f"/v1/tickets/{ticket_id}/timeline",
            params={"project_key": "ctower"},
            headers=_auth(tenant.operator_credential),
        )

    event_id = UUID(created.json()["event_ids"][0])
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT actor_principal_id, aggregate_id, causation_id, client_command_id,
                correlation_id, event_id, kind, origin, payload, prev_hash, request_sha256,
                schema_version, sequence, server_time, stream_id, tenant_id, event_hash
            FROM events WHERE event_id = %s
            """,
            (event_id,),
        ).fetchone()
        outbox = connection.execute(
            "SELECT payload FROM outbox WHERE event_id = %s", (event_id,)
        ).fetchone()
    assert row is not None and outbox is not None
    server_time = cast(datetime, row["server_time"])
    event: dict[str, object] = {
        "actor_principal_id": str(row["actor_principal_id"]),
        "aggregate_id": str(row["aggregate_id"]),
        "causation_id": str(row["causation_id"]) if row["causation_id"] is not None else None,
        "client_command_id": str(row["client_command_id"]),
        "correlation_id": str(row["correlation_id"]),
        "event_id": str(row["event_id"]),
        "kind": row["kind"],
        "origin": row["origin"],
        "payload": row["payload"],
        "prev_hash": f"sha256:{bytes(cast(bytes, row['prev_hash'])).hex()}",
        "request_sha256": f"sha256:{bytes(cast(bytes, row['request_sha256'])).hex()}",
        "schema_version": row["schema_version"],
        "sequence": row["sequence"],
        "server_time": server_time.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "stream_id": row["stream_id"],
        "tenant_id": str(row["tenant_id"]),
    }
    schema = json.loads(
        (ROOT / "contracts/domain/events/event-envelope.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(event)
    assert event["stream_id"] == f"ticket:{ticket_id}"
    canonical = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    assert hashlib.sha256(canonical.encode()).digest() == bytes(cast(bytes, row["event_hash"]))
    assert outbox["payload"] == event
    public_event = timeline.json()["events"][0]
    assert not {"event_hash", "prev_hash", "request_sha256"} & public_event.keys()


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(tenant.database.runtime_dsn)),
        ),
        client=("127.0.0.1", 51000),
    )


def _create_ticket(
    client: TestClient,
    credential: str,
    *,
    command_id: UUID,
    custodian_id: UUID,
    priority: str,
    title: str,
    source_ref: str = "mission-control:ticket",
) -> Response:
    response = client.post(
        "/v1/tickets",
        json={
            "initial_custodian_id": str(custodian_id),
            "priority": priority,
            "project_key": "ctower",
            "source": {"kind": "mission-control", "ref": source_ref},
            "title": title,
        },
        headers={**_auth(credential), "Idempotency-Key": str(command_id)},
    )
    return cast(Response, response)


def _issue_project_credential(
    client: TestClient,
    authority: str,
    *,
    credential: str,
    project_key: str,
    seat_key: str,
) -> Response:
    response = client.post(
        "/v1/admin/seat-credentials",
        json={
            "credential_digest": f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}",
            "credential_ref": f"secret-ref:test/{project_key}/{seat_key}",
            "display_name": f"{project_key.title()} Commander",
            "project_key": project_key,
            "scopes": ["capture", "transition", "evidence"],
            "seat_key": seat_key,
        },
        headers={**_auth(authority), "Idempotency-Key": str(uuid4())},
    )
    return cast(Response, response)


def _create_project_read_ticket(
    client: TestClient, tenant: TenantFixture, *, title: str
) -> tuple[UUID, Response]:
    created = _create_ticket(
        client,
        tenant.operator_credential,
        command_id=uuid4(),
        custodian_id=tenant.commander_id,
        priority="P1",
        title=title,
        source_ref="r3002:ticket-read-authz",
    )
    return UUID(created.json()["ticket"]["ticket_id"]), created


def _issue_project_read_credentials(
    client: TestClient, tenant: TenantFixture
) -> tuple[str, str, str, UUID]:
    credentials = tuple(secrets.token_urlsafe(32) for _ in range(3))
    issues = (
        _issue_project_credential(
            client,
            tenant.operator_credential,
            credential=credentials[0],
            project_key="ctower",
            seat_key="ctower-commander",
        ),
        _issue_project_credential(
            client,
            tenant.operator_credential,
            credential=credentials[1],
            project_key="manibo",
            seat_key="manibo-commander",
        ),
        _issue_project_credential(
            client,
            tenant.operator_credential,
            credential=credentials[2],
            project_key="bhloop",
            seat_key="bhloop-commander",
        ),
    )
    assert all(response.status_code == HTTP_PENDING for response in issues)
    return credentials[0], credentials[1], credentials[2], UUID(issues[2].json()["credential_id"])


def _persisted_operator_session(record: PostgresRecord, tenant: TenantFixture) -> Actor:
    now = datetime.now(UTC)
    issuer = "https://fake-idp.example.test"
    subject = f"operator-{uuid4().hex}"
    binding = record.human_identity.bind_role(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name=f"Acceptance Operator {uuid4().hex[:8]}",
            oidc_issuer=issuer,
            oidc_subject=subject,
            project_keys=(),
            role="operator",
        ),
        request_digest=hashlib.sha256(b"r3002-operator-binding").digest(),
        now=now,
        telemetry=_record_telemetry(),
    )
    assert not isinstance(binding, RecordProblem)
    resolved = record.human_identity.resolve_role_binding(issuer, subject)
    assert resolved is not None
    binding_id, bound_actor = resolved
    session_digest = hashlib.sha256(uuid4().bytes).digest()
    session = record.human_identity.issue_session(
        bound_actor.principal_id,
        bound_actor.tenant_id,
        binding_id,
        "operator",
        session_digest=session_digest,
        csrf_digest=hashlib.sha256(b"r3002-operator-csrf").digest(),
        now=now,
        ttl_seconds=3600,
    )
    assert session.role == "operator"
    actor = record.human_identity.actor_for_session(session_digest, now=now)
    assert isinstance(actor, Actor)
    assert actor.human_binding_id == binding_id
    assert actor.human_session_id is not None
    return actor


def _record_telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=0,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test",
        actor_id="test",
        command_id=command_id,
    )


def _record_ticket_read_surfaces(
    record: PostgresRecord, work: Work, actor: Actor, ticket_id: UUID
) -> tuple[object, ...]:
    return (
        _read_record_ticket(record, actor, ticket_id),
        _read_record_timeline(record, actor, ticket_id),
        _read_record_sessions(record, actor, ticket_id),
        _read_record_audit(record, actor, ticket_id),
        _read_record_assignments(work, actor, ticket_id),
    )


def _read_record_ticket(record: PostgresRecord, actor: Actor, ticket_id: UUID) -> object:
    return record.tickets.get(actor, ticket_id, "ctower", telemetry=_record_telemetry())


def _read_record_timeline(record: PostgresRecord, actor: Actor, ticket_id: UUID) -> object:
    return record.tickets.timeline(actor, ticket_id, "ctower", telemetry=_record_telemetry())


def _read_record_sessions(record: PostgresRecord, actor: Actor, ticket_id: UUID) -> object:
    return record.work_sessions.for_ticket(
        actor, ticket_id, "ctower", telemetry=_record_telemetry()
    )


def _read_record_audit(record: PostgresRecord, actor: Actor, ticket_id: UUID) -> object:
    return record.event_audit.ticket_audit(
        actor, ticket_id, "ctower", cursor=0, limit=100, telemetry=_record_telemetry()
    )


def _read_record_assignments(work: Work, actor: Actor, ticket_id: UUID) -> object:
    return work.assignments(actor, ticket_id, "ctower")


def _is_record_problem(value: object) -> TypeGuard[RecordProblem]:
    return isinstance(value, RecordProblem)


def _project_ticket_read_paths(ticket_id: UUID) -> tuple[tuple[str, dict[str, str]], ...]:
    return (
        (f"/v1/tickets/{ticket_id}", {"project_key": "ctower"}),
        (f"/v1/tickets/{ticket_id}/timeline", {"project_key": "ctower"}),
        (f"/v1/tickets/{ticket_id}/sessions", {"project_key": "ctower"}),
        (f"/v1/tickets/{ticket_id}/audit", {"project_key": "ctower"}),
        (f"/v1/tickets/{ticket_id}/assignments", {"project_key": "ctower"}),
    )


def _read_ticket_paths(
    client: TestClient,
    read_paths: tuple[tuple[str, dict[str, str]], ...],
    *,
    credential: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> tuple[Response, ...]:
    headers = _auth(credential) if credential is not None else telemetry_headers()
    params_extra = extra_params or {}
    return tuple(
        client.get(path, params={**params, **params_extra}, headers=headers)
        for path, params in read_paths
    )


def _assert_foreign_denied(responses: tuple[Response, ...], ticket_id: UUID, title: str) -> None:
    for response in responses:
        assert response.status_code == HTTP_FORBIDDEN
        assert response.json()["code"] == "project-scope-denied"
        assert str(ticket_id) not in response.text
        assert title not in response.text


def _assert_unauthenticated(responses: tuple[Response, ...], ticket_id: UUID, title: str) -> None:
    for response in responses:
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["code"] in {"unauthorized", "credential-revoked"}
        assert str(ticket_id) not in response.text
        assert title not in response.text


def _auth(credential: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        **telemetry_headers(),
    }


def _assert_ineligible_refused(client: TestClient, tenant: TenantFixture) -> None:
    response = _create_ticket(
        client,
        tenant.operator_credential,
        command_id=uuid4(),
        custodian_id=uuid4(),
        priority="P2",
        title="No eligible custodian",
    )
    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["code"] == "tenant-scope-denied"


def _assert_ticket_facts(dsn: str, *, expected: int) -> None:
    with psycopg.connect(dsn) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM tickets),
                (SELECT count(*) FROM lifecycle_episodes),
                (SELECT count(*) FROM assignment_intervals),
                (SELECT count(*) FROM priority_facts),
                (SELECT count(*) FROM events WHERE kind = 'ticket.created'),
                (SELECT count(*) FROM outbox WHERE topic = 'record.events') - 1
            """
        ).fetchone()
    assert counts == (expected, expected, expected, expected, expected, expected)
