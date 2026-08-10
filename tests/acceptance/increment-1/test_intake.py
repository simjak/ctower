"""Thread-first intake authority, provenance, replay, and projection acceptance."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.types.json import Jsonb
from support.acceptance import accept_pending_commands
from support.project_hierarchy import declare_ctower_project
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.projections import ProjectionHealth, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_PENDING = 202
HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
SECOND_VERSION = 2


@pytest.fixture(autouse=True)
def declared_project(tenant: TenantFixture) -> None:
    declare_ctower_project(tenant)


def test_thread_first_intake_is_atomic_replay_safe_and_board_neutral(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    body = _discussion("chat", f"message:{uuid4()}")
    with _client(tenant) as client:
        first = _submit(client, tenant, body, command_id)
        replay = _submit(client, tenant, body, command_id)
        changed = _submit(client, tenant, {**body, "content": "changed"}, command_id)

    assert first.status_code == HTTP_PENDING
    assert replay.json() == first.json()
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    result = first.json()
    assert result["outcome"] == "discussion"
    assert result["inbound_event_id"] == result["event_ids"][0]
    assert result["thread_version"] == 1

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    with _client(tenant) as client:
        accepted = _submit(client, tenant, body, command_id)
    assert accepted.status_code == HTTP_CREATED
    assert accepted.json() == {**result, "durability_state": "accepted"}
    board = Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(
        tenant.tenant_id
    )
    assert board.cards == ()
    assert _authority_counts(tenant) == (1, 1, 1, 0, 0, 0)


def test_create_link_promotion_cas_quarantine_and_restart_replay(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
) -> None:
    discussion, target_ticket = _seed_create_link_and_quarantine(tenant)
    _assert_promotion_restart_replay(tenant, discussion)
    _assert_link_promotion(tenant, target_ticket)
    _assert_target_refusals(tenant, second_tenant, target_ticket)


def test_authenticated_discussion_promotes_once_to_request_without_ticket(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        discussion = _submit(
            client,
            tenant,
            _discussion("native", f"request:{uuid4()}"),
            uuid4(),
        ).json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    inbound_event_id = UUID(discussion["inbound_event_id"])
    command_id = uuid4()
    body = {"expected_thread_version": 1, "intent": "create_request"}
    with _client(tenant) as client:
        promoted = _promote(client, tenant, inbound_event_id, body, command_id)
        replay = _promote(client, tenant, inbound_event_id, body, command_id)
        duplicate = _promote(
            client,
            tenant,
            inbound_event_id,
            {"expected_thread_version": 2, "intent": "create_request"},
            uuid4(),
        )
    payload = promoted.json()
    assert promoted.status_code == HTTP_PENDING
    assert replay.json() == payload
    assert payload["outcome"] == "request_created"
    assert payload["request_id"] is not None and payload["request_number"] == 1
    assert payload["ticket_id"] is None and len(payload["event_ids"]) == SECOND_VERSION
    assert duplicate.status_code == HTTP_CONFLICT
    assert duplicate.json()["code"] == "intake-already-promoted"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM requests WHERE tenant_id = %s),
              (SELECT count(*) FROM tickets WHERE tenant_id = %s),
              (SELECT count(*) FROM events
               WHERE tenant_id = %s AND kind = 'request.changed')
            """,
            (tenant.tenant_id, tenant.tenant_id, tenant.tenant_id),
        ).fetchone()
    assert counts == (1, 0, 1)


def _seed_create_link_and_quarantine(
    tenant: TenantFixture,
) -> tuple[dict[str, object], UUID]:
    with _client(tenant) as client:
        discussion = cast(
            dict[str, object],
            _submit(client, tenant, _discussion("mail", f"mail:{uuid4()}"), uuid4()).json(),
        )
        created = _submit(
            client,
            tenant,
            _create_body("chat", f"create:{uuid4()}", tenant.commander_id),
            uuid4(),
        )
        quarantined = _submit(
            client,
            tenant,
            {
                **_discussion("webhook", f"quarantine:{uuid4()}"),
                "taint": "quarantine_required",
            },
            uuid4(),
        )
    created_payload = cast(dict[str, object], created.json())
    target_ticket = UUID(str(created_payload["ticket_id"]))
    assert created.status_code == HTTP_PENDING
    assert created_payload["outcome"] == "ticket_created"
    assert len(cast(list[object], created_payload["event_ids"])) == SECOND_VERSION
    assert quarantined.json()["outcome"] == "quarantined"
    assert quarantined.json()["quarantine_reason"] == "structural-taint:quarantine_required"
    with _client(tenant) as client:
        initially_linked = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"initial-link:{uuid4()}"),
                "expected_ticket_version": 1,
                "intent": "link_ticket",
                "target_ticket_id": str(target_ticket),
            },
            uuid4(),
        )
        source = cast(dict[str, object], created_payload["source"])
        source_conflict = _submit(
            client,
            tenant,
            _discussion(str(source["kind"]), str(source["ref"])),
            uuid4(),
        )
    assert initially_linked.status_code == HTTP_PENDING
    assert initially_linked.json()["outcome"] == "ticket_linked"
    assert source_conflict.status_code == HTTP_CONFLICT
    assert source_conflict.json()["code"] == "intake-source-conflict"
    return discussion, target_ticket


def _assert_promotion_restart_replay(
    tenant: TenantFixture,
    discussion: dict[str, object],
) -> None:
    inbound_event_id = UUID(str(discussion["inbound_event_id"]))
    promotion_id = uuid4()
    promotion_body: dict[str, object] = {
        "expected_thread_version": 1,
        "initial_custodian_id": str(tenant.commander_id),
        "intent": "create_ticket",
        "priority": "P2",
        "title": "Promoted discussion",
    }
    with _client(tenant) as client:
        promoted = _promote(
            client,
            tenant,
            inbound_event_id,
            promotion_body,
            promotion_id,
        )
    with _client(tenant) as restarted:
        replay = _promote(
            restarted,
            tenant,
            inbound_event_id,
            promotion_body,
            promotion_id,
        )
        duplicate = _promote(
            restarted,
            tenant,
            inbound_event_id,
            {**promotion_body, "expected_thread_version": 2},
            uuid4(),
        )
    assert promoted.status_code == HTTP_PENDING
    assert promoted.json() == replay.json()
    assert duplicate.status_code == HTTP_CONFLICT
    assert duplicate.json()["code"] == "intake-already-promoted"
    _assert_exact_provenance(tenant, inbound_event_id)


def _assert_link_promotion(tenant: TenantFixture, target_ticket: UUID) -> None:
    with _client(tenant) as client:
        discussion = _submit(
            client,
            tenant,
            _discussion("chat", f"link:{uuid4()}"),
            uuid4(),
        ).json()
        linked = _promote(
            client,
            tenant,
            UUID(discussion["inbound_event_id"]),
            {
                "expected_thread_version": 1,
                "expected_ticket_version": 1,
                "intent": "link_ticket",
                "target_ticket_id": str(target_ticket),
            },
            uuid4(),
        )
    assert linked.status_code == HTTP_PENDING
    assert linked.json()["ticket_id"] == str(target_ticket)


def _assert_target_refusals(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
    target_ticket: UUID,
) -> None:
    with _client(tenant) as client:
        stale_target = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"stale:{uuid4()}"),
                "expected_ticket_version": 2,
                "intent": "link_ticket",
                "target_ticket_id": str(target_ticket),
            },
            uuid4(),
        )
        missing = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"missing:{uuid4()}"),
                "expected_ticket_version": 1,
                "intent": "link_ticket",
                "target_ticket_id": str(uuid4()),
            },
            uuid4(),
        )
        wrong_project = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"wrong-project:{uuid4()}"),
                "expected_ticket_version": 1,
                "intent": "link_ticket",
                "project_key": "other",
                "target_ticket_id": str(target_ticket),
            },
            uuid4(),
        )
    assert stale_target.status_code == HTTP_CONFLICT
    assert stale_target.json()["code"] == "version-conflict"
    assert missing.status_code == HTTP_NOT_FOUND
    assert missing.json()["code"] == "tenant-scope-denied"
    assert wrong_project.status_code == HTTP_NOT_FOUND
    assert wrong_project.json()["code"] == "tenant-scope-denied"
    _assert_cross_tenant_target_hidden(second_tenant, target_ticket)


def test_intake_requires_authentication_and_rejects_stale_thread_cas(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        unauthenticated = client.post(
            "/v1/intake",
            json=_discussion("chat", f"unauthenticated:{uuid4()}"),
            headers={"Idempotency-Key": str(uuid4()), **telemetry_headers()},
        )
        first = _submit(
            client,
            tenant,
            _discussion("chat", f"thread:{uuid4()}"),
            uuid4(),
        ).json()
        appended = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"append:{uuid4()}"),
                "expected_thread_version": 1,
                "thread_id": first["thread_id"],
            },
            uuid4(),
        )
        stale = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"stale-thread:{uuid4()}"),
                "expected_thread_version": 1,
                "thread_id": first["thread_id"],
            },
            uuid4(),
        )

    assert unauthenticated.status_code == HTTP_UNAUTHORIZED
    assert appended.status_code == HTTP_PENDING
    assert appended.json()["thread_version"] == SECOND_VERSION
    assert stale.status_code == HTTP_CONFLICT
    assert stale.json()["code"] == "version-conflict"
    assert stale.json()["current_version"] == SECOND_VERSION


def test_poisoned_intake_outbox_fails_loud_with_state_unknown(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        result = _submit(
            client,
            tenant,
            _discussion("chat", f"poison:{uuid4()}"),
            uuid4(),
        ).json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT outbox_id, payload FROM outbox WHERE event_id = %s",
            (UUID(result["inbound_event_id"]),),
        ).fetchone()
        if row is None:
            raise RuntimeError("intake outbox row is unavailable")
        poisoned = {**cast(dict[str, object], row[1]), "schema_version": 99}
        connection.execute(
            "UPDATE outbox SET payload = %s WHERE outbox_id = %s",
            (Jsonb(poisoned), row[0]),
        )

    view = Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(
        tenant.tenant_id
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        poison = connection.execute(
            """
            SELECT count(*), min(reason) FROM outbox_poison
            WHERE tenant_id = %s
            """,
            (tenant.tenant_id,),
        ).fetchone()

    assert view.health is ProjectionHealth.STATE_UNKNOWN
    assert poison == (1, "schema-unknown: event version")


def test_service_role_cannot_rewrite_inbound_event_alias_or_provenance(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        created = _submit(
            client,
            tenant,
            _create_body("chat", f"immutable:{uuid4()}", tenant.commander_id),
            uuid4(),
        ).json()
    event_id = UUID(created["inbound_event_id"])
    statements = (
        ("UPDATE inbound_events SET content = 'rewrite' WHERE inbound_event_id = %s", event_id),
        (
            "UPDATE inbound_source_aliases SET source_ref = 'rewrite' WHERE inbound_event_id = %s",
            event_id,
        ),
        ("DELETE FROM inbound_ticket_links WHERE inbound_event_id = %s", event_id),
    )
    for statement, identity in statements:
        with (
            psycopg.connect(tenant.database.runtime_dsn) as connection,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            connection.execute("SET ROLE ctower_svc")
            connection.execute(statement, (identity,))


def _assert_cross_tenant_target_hidden(tenant: TenantFixture, ticket_id: UUID) -> None:
    with _client(tenant) as client:
        response = _submit(
            client,
            tenant,
            {
                **_discussion("chat", f"foreign:{uuid4()}"),
                "expected_ticket_version": 1,
                "intent": "link_ticket",
                "target_ticket_id": str(ticket_id),
            },
            uuid4(),
        )
    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["code"] == "tenant-scope-denied"


def _assert_exact_provenance(tenant: TenantFixture, inbound_event_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) AS count, min(link.link_kind) AS link_kind,
                min(ticket.source_kind), min(ticket.source_ref)
            FROM inbound_ticket_links AS link
            JOIN tickets AS ticket
              ON ticket.tenant_id = link.tenant_id AND ticket.ticket_id = link.ticket_id
            WHERE link.tenant_id = %s AND link.inbound_event_id = %s
            """,
            (tenant.tenant_id, inbound_event_id),
        ).fetchone()
        alias = connection.execute(
            """
            SELECT source_kind, source_ref FROM inbound_source_aliases
            WHERE tenant_id = %s AND inbound_event_id = %s
            """,
            (tenant.tenant_id, inbound_event_id),
        ).fetchone()
    assert alias is not None
    assert row == (1, "promotion_create", alias[0], alias[1])


def _authority_counts(tenant: TenantFixture) -> tuple[int, int, int, int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM inbound_threads WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_events WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_source_aliases WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_ticket_links WHERE tenant_id = %s),
              (SELECT count(*) FROM tickets WHERE tenant_id = %s),
              (SELECT count(*) FROM ticket_project_bindings WHERE tenant_id = %s)
            """,
            (tenant.tenant_id,) * 6,
        ).fetchone()
    if row is None:
        raise RuntimeError("authority count query returned no row")
    return cast(tuple[int, int, int, int, int, int], row)


def _client(tenant: TenantFixture) -> TestClient:
    return TestClient(
        create_app(PostgresRecord(tenant.database.runtime_dsn)),
        client=("127.0.0.1", 51000),
    )


def _submit(
    client: TestClient,
    tenant: TenantFixture,
    body: dict[str, object],
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/intake",
            json=body,
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        ),
    )


def _promote(
    client: TestClient,
    tenant: TenantFixture,
    inbound_event_id: UUID,
    body: dict[str, object],
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/intake/events/{inbound_event_id}/promotion",
            json=body,
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        ),
    )


def _discussion(kind: str, ref: str) -> dict[str, object]:
    return {
        "content": "Durable discussion",
        "project_key": "ctower",
        "source": {"kind": kind, "ref": ref},
    }


def _create_body(kind: str, ref: str, custodian_id: UUID) -> dict[str, object]:
    return {
        **_discussion(kind, ref),
        "initial_custodian_id": str(custodian_id),
        "intent": "create_ticket",
        "priority": "P2",
        "title": "Created from intake",
    }
