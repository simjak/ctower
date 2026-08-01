"""Ticket creation, replay, read, and timeline acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from jsonschema import Draft202012Validator
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_PENDING = 202
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
ROOT = Path(__file__).parents[3]


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
    return TestClient(
        create_app(PostgresRecord(tenant.database.runtime_dsn)), client=("127.0.0.1", 51000)
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
