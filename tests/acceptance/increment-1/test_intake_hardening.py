"""Adversarial authority, promotion, project, and body-bound intake evidence."""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from support.project_hierarchy import declare_ctower_project
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

BODY_LIMIT_BYTES = 512 * 1024
HTTP_UNAUTHORIZED = 401
HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_TOO_LARGE = 413


@pytest.fixture(autouse=True)
def declared_project(tenant: TenantFixture) -> None:
    declare_ctower_project(tenant)


def test_create_intake_authorizes_custody_before_source_existence(
    tenant: TenantFixture,
) -> None:
    submit_ref = f"custody-submit:{uuid4()}"
    promotion_ref = f"custody-promotion:{uuid4()}"
    _direct_ticket_for_source(tenant, "chat", submit_ref)
    _direct_ticket_for_source(tenant, "chat", promotion_ref)

    with _client(tenant) as client:
        submit = _submit(
            client,
            tenant,
            _create("chat", submit_ref, tenant.operator_id),
            uuid4(),
        )
        discussion = _submit(
            client,
            tenant,
            _discussion("chat", promotion_ref),
            uuid4(),
        )
        promotion = _promote(
            client,
            tenant,
            UUID(str(discussion.json()["inbound_event_id"])),
            {
                "expected_thread_version": discussion.json()["thread_version"],
                "initial_custodian_id": str(tenant.operator_id),
                "intent": "create_ticket",
                "priority": "P2",
                "title": "Unauthorized promotion custody",
            },
            uuid4(),
        )

    assert discussion.status_code == HTTP_PENDING
    for refusal in (submit, promotion):
        assert refusal.status_code == HTTP_FORBIDDEN
        assert refusal.json()["code"] == "unauthorized"
        assert "unmet_facts" not in refusal.json()
    assert _source_ticket_count(tenant, "chat", submit_ref) == 1
    assert _source_ticket_count(tenant, "chat", promotion_ref) == 1


def test_create_intake_defaults_only_authorized_commander_custody(
    tenant: TenantFixture,
) -> None:
    commander_ref = f"commander-default:{uuid4()}"
    operator_ref = f"operator-default:{uuid4()}"
    create_fields = {
        "intent": "create_ticket",
        "priority": "P2",
        "title": "Defaulted intake custody",
    }
    with _client(tenant) as client:
        commander_default = _submit(
            client,
            tenant,
            {**_discussion("chat", commander_ref), **create_fields},
            uuid4(),
        )
        operator_command_id = uuid4()
        operator_default = client.post(
            "/v1/intake",
            json={**_discussion("chat", operator_ref), **create_fields},
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(operator_command_id),
                **telemetry_headers(operator_command_id),
            },
        )

    assert commander_default.status_code == HTTP_PENDING
    assert (
        _ticket_custodian(
            tenant,
            UUID(str(commander_default.json()["ticket_id"])),
        )
        == tenant.commander_id
    )
    assert operator_default.status_code == HTTP_FORBIDDEN
    assert operator_default.json()["code"] == "unauthorized"
    assert _source_ticket_count(tenant, "chat", operator_ref) == 0


def test_every_refused_first_submit_has_zero_authority_delta_and_exact_replay(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
) -> None:
    local_ineligible = _add_ineligible_principal(tenant)
    with _client(tenant) as client:
        source = _discussion("chat", f"occupied:{uuid4()}")
        _submit(client, tenant, source, uuid4())
        target = _submit(
            client,
            tenant,
            _create("chat", f"target:{uuid4()}", tenant.commander_id),
            uuid4(),
        ).json()
    foreign_ticket = _unbound_ticket(second_tenant, "Foreign target")

    target_id = str(target["ticket_id"])
    cases = (
        (source, HTTP_CONFLICT, "intake-source-conflict"),
        (_link(f"missing:{uuid4()}", uuid4(), version=1), HTTP_NOT_FOUND, "tenant-scope-denied"),
        (_link(f"stale:{uuid4()}", UUID(target_id), version=2), HTTP_CONFLICT, "version-conflict"),
        (
            {
                **_link(f"wrong-project:{uuid4()}", UUID(target_id), version=1),
                "project_key": "other",
            },
            HTTP_NOT_FOUND,
            "tenant-scope-denied",
        ),
        (
            {**_discussion("chat", f"absent-project:{uuid4()}"), "project_key": "ghost-project"},
            HTTP_NOT_FOUND,
            "tenant-scope-denied",
        ),
        (
            _create("chat", f"ineligible:{uuid4()}", local_ineligible),
            HTTP_FORBIDDEN,
            "unauthorized",
        ),
        (
            _create("chat", f"foreign-custodian:{uuid4()}", second_tenant.commander_id),
            HTTP_FORBIDDEN,
            "unauthorized",
        ),
        (
            _link(f"foreign-target:{uuid4()}", foreign_ticket, version=1),
            HTTP_NOT_FOUND,
            "tenant-scope-denied",
        ),
    )
    with _client(tenant) as client:
        for body, status, code in cases:
            _assert_zero_delta_refusal(client, tenant, body, status=status, code=code)

    assert _thread_versions(tenant)
    assert 0 not in _thread_versions(tenant)


def test_canonical_imported_binding_is_linkable_and_conflicts_cannot_coexist(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
) -> None:
    imported = _unbound_ticket(tenant, "Imported canonical target")
    run_id = _migration_run(tenant, "imported")
    _insert_import_binding(tenant, imported, run_id, "imported")

    with _client(tenant) as client:
        linked = _submit(
            client,
            tenant,
            _link(f"import-link:{uuid4()}", imported, version=1),
            uuid4(),
        )
    assert linked.status_code == HTTP_PENDING
    assert linked.json()["ticket_id"] == str(imported)

    conflicted = _unbound_ticket(tenant, "Concurrent binding target")
    first_run = _migration_run(tenant, "conflict-a")
    second_run = _migration_run(tenant, "conflict-b")
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda pair: _try_insert_binding(tenant, conflicted, pair[0], pair[1]),
                ((first_run, "conflict-a"), (second_run, "conflict-b")),
            )
        )
    assert sorted(outcomes) == ["bound", "conflict"]
    assert _binding_count(tenant, conflicted) == 1

    with (
        psycopg.connect(tenant.database.admin_dsn) as connection,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        connection.execute(
            """
            INSERT INTO ticket_project_bindings (
                ticket_id, tenant_id, project_key, run_id, source_namespace,
                immutable_source_id, bound_at, inbound_event_id
            ) VALUES (%s, %s, 'ctower', %s, 'cross-tenant', 'foreign', %s, NULL)
            """,
            (
                _unbound_ticket(second_tenant, "Foreign binding target"),
                tenant.tenant_id,
                first_run,
                datetime.now(UTC),
            ),
        )


def test_quarantined_tainted_and_governed_events_cannot_be_promoted(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        quarantined = _submit(
            client,
            tenant,
            {
                **_discussion("webhook", f"quarantine:{uuid4()}"),
                "taint": "quarantine_required",
            },
            uuid4(),
        ).json()
        tainted = _submit(
            client,
            tenant,
            {
                **_discussion("mail", f"tainted:{uuid4()}"),
                "taint": "external_untrusted",
            },
            uuid4(),
        ).json()
        target = _submit(
            client,
            tenant,
            _create("chat", f"promotion-target:{uuid4()}", tenant.commander_id),
            uuid4(),
        ).json()

        create = {
            "expected_thread_version": 1,
            "initial_custodian_id": str(tenant.commander_id),
            "intent": "create_ticket",
            "priority": "P2",
            "title": "Forbidden promotion",
        }
        link = {
            "expected_thread_version": 1,
            "expected_ticket_version": 1,
            "intent": "link_ticket",
            "target_ticket_id": target["ticket_id"],
        }
        for event, body in (
            (quarantined, create),
            (quarantined, link),
            (tainted, create),
        ):
            before = _authority_snapshot(tenant)
            command_id = uuid4()
            first = _promote(client, tenant, UUID(str(event["inbound_event_id"])), body, command_id)
            replay = _promote(
                client,
                tenant,
                UUID(str(event["inbound_event_id"])),
                body,
                command_id,
            )
            assert first.status_code == HTTP_CONFLICT
            assert first.json()["code"] == "intake-promotion-ineligible"
            assert replay.content == first.content
            assert _authority_snapshot(tenant) == before


@pytest.mark.parametrize("route", ("submit", "promotion"))
def test_authenticated_intake_body_limit_precedes_full_buffering(
    tenant: TenantFixture,
    route: str,
) -> None:
    path = "/v1/intake" if route == "submit" else f"/v1/intake/events/{uuid4()}/promotion"
    before = _authority_snapshot(tenant)
    with _client(tenant) as client:
        declared = client.post(
            path,
            content=b"{}",
            headers={
                **_headers(tenant, uuid4()),
                "Content-Length": str(BODY_LIMIT_BYTES + 1),
                "Content-Type": "application/json",
            },
        )
        streamed = client.post(
            path,
            content=_oversized_chunks(b'{"content":"', b'"}'),
            headers={**_headers(tenant, uuid4()), "Content-Type": "application/json"},
        )
        malformed = client.post(
            path,
            content=_oversized_chunks(b"{", b""),
            headers={**_headers(tenant, uuid4()), "Content-Type": "application/json"},
        )
        unknown = client.post(
            path,
            content=_oversized_chunks(b'{"unknown":"', b'"}'),
            headers={**_headers(tenant, uuid4()), "Content-Type": "application/json"},
        )
    for response in (declared, streamed, malformed, unknown):
        assert response.status_code == HTTP_TOO_LARGE
        assert response.json()["code"] == "request-body-too-large"
        assert response.json()["status"] == HTTP_TOO_LARGE
    assert _authority_snapshot(tenant) == before


def test_oversized_unauthenticated_body_is_rejected_before_size_disclosure(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        response = client.post(
            "/v1/intake",
            content=b"{}",
            headers={
                "Content-Length": str(BODY_LIMIT_BYTES + 1),
                "Content-Type": "application/json",
                "Idempotency-Key": str(uuid4()),
                **telemetry_headers(),
            },
        )
    assert response.status_code == HTTP_UNAUTHORIZED


def _assert_zero_delta_refusal(
    client: TestClient,
    tenant: TenantFixture,
    body: dict[str, object],
    *,
    status: int,
    code: str,
) -> None:
    before = _authority_snapshot(tenant)
    command_id = uuid4()
    first = _submit(client, tenant, body, command_id)
    replay = _submit(client, tenant, body, command_id)
    assert first.status_code == status
    assert first.json()["code"] == code
    assert replay.content == first.content
    assert _authority_snapshot(tenant) == before


def _authority_snapshot(tenant: TenantFixture) -> tuple[object, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM inbound_threads WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_events WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_source_aliases WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_ticket_links WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_quarantines WHERE tenant_id = %s),
              (SELECT count(*) FROM tickets WHERE tenant_id = %s),
              (SELECT count(*) FROM ticket_project_bindings WHERE tenant_id = %s),
              (SELECT count(*) FROM events WHERE tenant_id = %s),
              (SELECT count(*) FROM outbox WHERE tenant_id = %s),
              (SELECT array_agg(version ORDER BY thread_id)
                 FROM inbound_threads WHERE tenant_id = %s)
            """,
            (tenant.tenant_id,) * 10,
        ).fetchone()
    if row is None:
        raise RuntimeError("authority snapshot query returned no row")
    return cast(tuple[object, ...], row)


def _thread_versions(tenant: TenantFixture) -> tuple[int, ...]:
    snapshot = _authority_snapshot(tenant)
    return tuple(cast(list[int] | None, snapshot[-1]) or ())


def _client(tenant: TenantFixture) -> TestClient:
    return TestClient(
        create_app(PostgresRecord(tenant.database.runtime_dsn)),
        client=("127.0.0.1", 51001),
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
            headers=_headers(tenant, command_id),
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
            headers=_headers(tenant, command_id),
        ),
    )


def _headers(tenant: TenantFixture, command_id: UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }


def _discussion(kind: str, ref: str) -> dict[str, object]:
    return {
        "content": "Durable discussion",
        "project_key": "ctower",
        "source": {"kind": kind, "ref": ref},
    }


def _create(kind: str, ref: str, custodian_id: UUID) -> dict[str, object]:
    return {
        **_discussion(kind, ref),
        "initial_custodian_id": str(custodian_id),
        "intent": "create_ticket",
        "priority": "P2",
        "title": "Created from intake",
    }


def _link(ref: str, target: UUID, *, version: int) -> dict[str, object]:
    return {
        **_discussion("chat", ref),
        "expected_ticket_version": version,
        "intent": "link_ticket",
        "target_ticket_id": str(target),
    }


def _oversized_chunks(prefix: bytes, suffix: bytes) -> Iterable[bytes]:
    yield prefix
    yield b"x" * BODY_LIMIT_BYTES
    yield suffix


def _add_ineligible_principal(tenant: TenantFixture) -> UUID:
    principal_id = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled,
                credential_ref, vault_ref, created_at
            ) VALUES (%s, %s, 'agent', %s, false, NULL, NULL, %s)
            """,
            (principal_id, tenant.tenant_id, f"ineligible-{principal_id}", datetime.now(UTC)),
        )
    return principal_id


def _unbound_ticket(tenant: TenantFixture, title: str) -> UUID:
    command_id = uuid4()
    with _client(tenant) as client:
        response = client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P2",
                "source": {"kind": "fixture", "ref": f"unbound:{command_id}"},
                "title": title,
            },
            headers=_headers(tenant, command_id),
        )
    assert response.status_code == HTTP_PENDING
    return UUID(str(response.json()["ticket"]["ticket_id"]))


def _direct_ticket_for_source(tenant: TenantFixture, kind: str, ref: str) -> UUID:
    command_id = uuid4()
    with _client(tenant) as client:
        response = client.post(
            "/v1/tickets",
            json={
                "priority": "P2",
                "source": {"kind": kind, "ref": ref},
                "title": "Existing source",
            },
            headers=_headers(tenant, command_id),
        )
    assert response.status_code == HTTP_PENDING
    return UUID(str(response.json()["ticket"]["ticket_id"]))


def _source_ticket_count(tenant: TenantFixture, source_kind: str, source_ref: str) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM tickets
            WHERE tenant_id = %s AND source_kind = %s AND source_ref = %s
            """,
            (tenant.tenant_id, source_kind, source_ref),
        ).fetchone()
    if row is None:
        raise RuntimeError("ticket count query returned no row")
    return int(row[0])


def _ticket_custodian(tenant: TenantFixture, ticket_id: UUID) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT custodian_principal_id FROM tickets
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("ticket custody query returned no row")
    return cast(UUID, row[0])


def _migration_run(tenant: TenantFixture, label: str) -> UUID:
    run_id = uuid4()
    digest = bytes.fromhex("11" * 32)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO migration_import_runs (
                run_id, tenant_id, cutover_id, tenant_key, project_key,
                source_selection_digest, build_digest, client_digest, schema_digest,
                operation_registry_digest, reviewer_public_key_digest, created_by, created_at
            ) VALUES (
                %s, %s, %s, 'ctower', 'ctower',
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                run_id,
                tenant.tenant_id,
                uuid4(),
                digest,
                digest,
                digest,
                digest,
                digest,
                digest,
                tenant.operator_id,
                datetime.now(UTC),
            ),
        )
    del label
    return run_id


def _insert_import_binding(
    tenant: TenantFixture,
    ticket_id: UUID,
    run_id: UUID,
    source_id: str,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO ticket_project_bindings (
                ticket_id, tenant_id, project_key, run_id, source_namespace,
                immutable_source_id, bound_at, inbound_event_id
            ) VALUES (%s, %s, 'ctower', %s, 'mission-control:test', %s, %s, NULL)
            """,
            (ticket_id, tenant.tenant_id, run_id, source_id, datetime.now(UTC)),
        )


def _try_insert_binding(
    tenant: TenantFixture,
    ticket_id: UUID,
    run_id: UUID,
    source_id: str,
) -> str:
    try:
        _insert_import_binding(tenant, ticket_id, run_id, source_id)
    except psycopg.errors.UniqueViolation:
        return "conflict"
    return "bound"


def _binding_count(tenant: TenantFixture, ticket_id: UUID) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM ticket_project_bindings WHERE ticket_id = %s",
            (ticket_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("binding count query returned no row")
    return int(row[0])
