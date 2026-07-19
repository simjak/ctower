"""Public custody transfer, isolation, concurrency, and restart acceptance."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_api.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_CREATED = 201
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
VERSION_AFTER_FIRST_TRANSFER = 2


def test_atomic_reassign_exact_replay_and_stale_from(tenant: TenantFixture) -> None:
    ticket = _create_ticket(tenant)
    ticket_id = UUID(str(ticket["ticket_id"]))
    first_command = uuid4()
    with _client(tenant) as client:
        first = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=first_command,
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Operator suspension",
        )
        replay = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=first_command,
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Operator suspension",
        )
        stale = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=2,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Stale declared custodian",
        )
    _assert_transfer_outcomes(first, replay, stale)


def _assert_transfer_outcomes(
    first: Response,
    replay: Response,
    stale: Response,
) -> None:
    assert first.status_code == HTTP_OK
    assert first.content == replay.content
    assert first.json()["durability_state"] == "durability_pending"
    assert first.json()["ticket"]["version"] == VERSION_AFTER_FIRST_TRANSFER
    assert stale.status_code == HTTP_CONFLICT
    assert stale.json()["code"] == "version-conflict"
    assert stale.json()["current_version"] == VERSION_AFTER_FIRST_TRANSFER


def test_operator_custody_can_transfer_to_commander_after_restart(tenant: TenantFixture) -> None:
    ticket_id = UUID(str(_create_ticket(tenant, custodian_id=tenant.operator_id)["ticket_id"]))
    with _client(tenant) as client:
        transferred = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.operator_id,
            to_id=tenant.commander_id,
            reason="Commander accountability restored",
        )
    with _client(tenant) as restarted:
        shown = _show(restarted, tenant.operator_credential, ticket_id)
        timeline = _timeline(restarted, tenant.operator_credential, ticket_id)

    assert transferred.status_code == HTTP_OK
    assert shown.json() == transferred.json()["ticket"]
    assert shown.json()["custodian_id"] == str(tenant.commander_id)
    assert [event["sequence"] for event in timeline.json()["events"]] == [1, 2]
    assert timeline.json()["events"][1]["payload"] == {
        "from_custodian_id": str(tenant.operator_id),
        "reason": "Commander accountability restored",
        "to_custodian_id": str(tenant.commander_id),
    }


def test_protected_authority_and_eligible_same_tenant_targets(tenant: TenantFixture) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))
    with _client(tenant) as client:
        unprotected = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Unprotected attempt",
            protected=False,
        )
        commander = _transfer(
            client,
            tenant.commander_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=tenant.operator_id,
            reason="Commander cannot execute protected transfer",
        )
        ineligible = _transfer(
            client,
            tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=uuid4(),
            reason="Unknown target",
        )
        shown = _show(client, tenant.operator_credential, ticket_id)
        timeline = _timeline(client, tenant.operator_credential, ticket_id)

    assert unprotected.status_code == HTTP_FORBIDDEN
    assert commander.status_code == HTTP_FORBIDDEN
    assert ineligible.status_code == HTTP_NOT_FOUND
    assert shown.json()["custodian_id"] == str(tenant.commander_id)
    assert shown.json()["version"] == 1
    assert len(timeline.json()["events"]) == 1


def test_real_second_tenant_is_denied_without_existence_reveal(
    tenant: TenantFixture, second_tenant: TenantFixture
) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))
    missing_id = uuid4()
    with _client(second_tenant) as client:
        real_show = _show(client, second_tenant.operator_credential, ticket_id)
        missing_show = _show(client, second_tenant.operator_credential, missing_id)
        real_timeline = _timeline(client, second_tenant.operator_credential, ticket_id)
        foreign_target = _transfer(
            client,
            second_tenant.operator_credential,
            ticket_id=ticket_id,
            command_id=uuid4(),
            expected_version=1,
            from_id=tenant.commander_id,
            to_id=second_tenant.commander_id,
            reason="Cross-tenant transfer refused",
        )

    assert real_show.status_code == missing_show.status_code == HTTP_NOT_FOUND
    assert real_show.content == missing_show.content
    assert real_timeline.status_code == HTTP_NOT_FOUND
    assert real_timeline.json()["code"] == "tenant-scope-denied"
    assert foreign_target.status_code == HTTP_NOT_FOUND
    assert foreign_target.json()["code"] == "tenant-scope-denied"


def test_concurrent_transfers_append_one_ordered_event(tenant: TenantFixture) -> None:
    ticket_id = UUID(str(_create_ticket(tenant)["ticket_id"]))

    def attempt() -> Response:
        with _client(tenant) as client:
            return _transfer(
                client,
                tenant.operator_credential,
                ticket_id=ticket_id,
                command_id=uuid4(),
                expected_version=1,
                from_id=tenant.commander_id,
                to_id=tenant.operator_id,
                reason="Concurrent protected transfer",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = tuple(executor.map(lambda _: attempt(), range(2)))

    assert sorted(response.status_code for response in responses) == [HTTP_OK, HTTP_CONFLICT]
    conflict = next(response for response in responses if response.status_code == HTTP_CONFLICT)
    assert conflict.json()["current_version"] == VERSION_AFTER_FIRST_TRANSFER
    with _client(tenant) as client:
        shown = _show(client, tenant.operator_credential, ticket_id)
        timeline = _timeline(client, tenant.operator_credential, ticket_id)
    assert shown.json()["version"] == VERSION_AFTER_FIRST_TRANSFER
    assert shown.json()["custodian_id"] == str(tenant.operator_id)
    events = timeline.json()["events"]
    assert [event["sequence"] for event in events] == [1, 2]
    assert len({event["event_id"] for event in events}) == VERSION_AFTER_FIRST_TRANSFER


def test_service_role_cannot_update_or_delete_immutable_record_rows(
    tenant: TenantFixture,
) -> None:
    statements = (
        "UPDATE events SET payload = payload WHERE false",
        "DELETE FROM events WHERE false",
        "UPDATE command_results SET response_body = response_body WHERE false",
        "DELETE FROM command_results WHERE false",
        "UPDATE outbox SET payload = payload WHERE false",
        "DELETE FROM outbox WHERE false",
    )

    for statement in statements:
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            psycopg.connect(tenant.database.dsn) as connection,
        ):
            connection.execute("SET ROLE ctower_svc")
            connection.execute(statement)


def _client(tenant: TenantFixture) -> TestClient:
    return TestClient(create_app(PostgresRecord(tenant.database.dsn)), client=("127.0.0.1", 51000))


def _create_ticket(tenant: TenantFixture, *, custodian_id: UUID | None = None) -> dict[str, object]:
    with _client(tenant) as client:
        response = client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(custodian_id or tenant.commander_id),
                "priority": "P1",
                "source": {"kind": "mission-control", "ref": "mission-control:custody"},
                "title": "Custody acceptance ticket",
            },
            headers={
                **_auth(tenant.operator_credential),
                "Idempotency-Key": str(uuid4()),
            },
        )
    assert response.status_code == HTTP_CREATED
    return cast(dict[str, object], response.json()["ticket"])


def _transfer(
    client: TestClient,
    credential: str,
    *,
    ticket_id: UUID,
    command_id: UUID,
    expected_version: int,
    from_id: UUID,
    to_id: UUID,
    reason: str,
    protected: bool = True,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/custody",
            json={
                "expected_version": expected_version,
                "from_custodian_id": str(from_id),
                "protected_transfer": protected,
                "reason": reason,
                "to_custodian_id": str(to_id),
            },
            headers={**_auth(credential), "Idempotency-Key": str(command_id)},
        ),
    )


def _show(client: TestClient, credential: str, ticket_id: UUID) -> Response:
    return cast(
        Response,
        client.get(f"/v1/tickets/{ticket_id}", headers=_auth(credential)),
    )


def _timeline(client: TestClient, credential: str, ticket_id: UUID) -> Response:
    return cast(
        Response,
        client.get(f"/v1/tickets/{ticket_id}/timeline", headers=_auth(credential)),
    )


def _auth(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}
