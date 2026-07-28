"""Durability authority SQL assertions, fault hooks, and HTTP requests."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.postgres import (
    DatabaseFixture,
    DurabilityPair,
    promote_durability_standby,
    start_durability_standby,
    stop_durability_primary,
)
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

__all__: tuple[str, ...] = ()

HTTP_CONFLICT = 409
SHA256_BYTES = 32


class AuthorityFixture(Protocol):
    @property
    def pair(self) -> DurabilityPair: ...

    @property
    def database(self) -> DatabaseFixture: ...

    @property
    def standby_dsn(self) -> str: ...

    @property
    def tenant(self) -> TenantFixture: ...


def assert_primary_evidence(authority: AuthorityFixture, accepted: tuple[UUID, UUID]) -> None:
    command_id, _ = accepted
    with psycopg.connect(authority.standby_dsn, row_factory=dict_row) as connection:
        receipt = connection.execute(
            """
            SELECT acknowledgement.acceptance_position, finalization.acceptance_position
                    AS finalized_position,
                acknowledgement.command_root, acknowledgement.request_sha256,
                acknowledgement.standby_application_name, acknowledgement.standby_identity,
                observation.standby_in_recovery
            FROM durability_acknowledgements AS acknowledgement
            JOIN durability_acceptance_finalizations AS finalization
              ON finalization.tenant_id = acknowledgement.tenant_id
             AND finalization.principal_id = acknowledgement.principal_id
             AND finalization.client_command_id = acknowledgement.client_command_id
             AND finalization.acceptance_position = acknowledgement.acceptance_position
            JOIN LATERAL (
                SELECT standby_in_recovery
                FROM durability_target_observations AS candidate
                WHERE candidate.tenant_id = acknowledgement.tenant_id
                  AND candidate.principal_id = acknowledgement.principal_id
                  AND candidate.client_command_id = acknowledgement.client_command_id
                  AND candidate.receipt_visible
                ORDER BY candidate.observed_at DESC LIMIT 1
            ) AS observation ON true
            WHERE acknowledgement.tenant_id = %s
              AND acknowledgement.client_command_id = %s
            """,
            (authority.tenant.tenant_id, command_id),
        ).fetchone()
        positions = connection.execute(
            """
            SELECT acceptance_position FROM durability_acceptance_finalizations
            ORDER BY acceptance_position
            """
        ).fetchall()
    assert receipt is not None
    position = int(cast(int, receipt["acceptance_position"]))
    assert position > 0
    assert receipt["finalized_position"] == position
    assert len(bytes(cast(bytes, receipt["command_root"]))) == SHA256_BYTES
    assert len(bytes(cast(bytes, receipt["request_sha256"]))) == SHA256_BYTES
    assert receipt["standby_application_name"] == "ctower_i1_ack"
    assert receipt["standby_identity"] == "ctower_i1_standby"
    assert receipt["standby_in_recovery"] is True
    ordered = [int(cast(int, row["acceptance_position"])) for row in positions]
    assert ordered == sorted(set(ordered))


def assert_primary_loss_boundary(
    authority: AuthorityFixture,
    accepted: tuple[UUID, UUID],
    local_commands: tuple[UUID, ...],
) -> None:
    accepted_command, accepted_ticket = accepted
    stop_durability_primary(authority.pair)
    start_durability_standby(authority.pair)
    promote_durability_standby(authority.pair)

    with psycopg.connect(authority.standby_dsn) as connection:
        accepted_row = connection.execute(
            """
            SELECT
                EXISTS (SELECT 1 FROM tickets WHERE ticket_id = %s),
                EXISTS (
                    SELECT 1 FROM durability_acknowledgements
                    WHERE tenant_id = %s AND client_command_id = %s
                ),
                EXISTS (
                    SELECT 1 FROM durability_acceptance_finalizations
                    WHERE tenant_id = %s AND client_command_id = %s
                )
            """,
            (
                accepted_ticket,
                authority.tenant.tenant_id,
                accepted_command,
                authority.tenant.tenant_id,
                accepted_command,
            ),
        ).fetchone()
        absent = connection.execute(
            """
            SELECT count(*) FROM command_results
            WHERE tenant_id = %s AND client_command_id = ANY(%s)
            """,
            (authority.tenant.tenant_id, list(local_commands)),
        ).fetchone()
    assert accepted_row == (True, True, True)
    assert absent == (0,)


def assert_replay_without_receipt(authority: AuthorityFixture, command_id: UUID) -> None:
    with psycopg.connect(authority.standby_dsn) as connection:
        facts = connection.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM command_results
                    WHERE tenant_id = %s AND client_command_id = %s
                ),
                EXISTS (
                    SELECT 1 FROM durability_acknowledgements
                    WHERE tenant_id = %s AND client_command_id = %s
                )
            """,
            (
                authority.tenant.tenant_id,
                command_id,
                authority.tenant.tenant_id,
                command_id,
            ),
        ).fetchone()
    assert facts == (True, False)


def assert_primary_only_result(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM command_results WHERE client_command_id = %s",
            (command_id,),
        ).fetchone()
    assert row == (1,)


def assert_one_result_and_ack(authority: AuthorityFixture, command_id: UUID) -> None:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM command_results WHERE client_command_id = %s),
                (SELECT count(*) FROM durability_acknowledgements WHERE client_command_id = %s),
                (SELECT count(*) FROM durability_acceptance_finalizations
                 WHERE client_command_id = %s)
            """,
            (command_id, command_id, command_id),
        ).fetchone()
    assert row == (1, 1, 1)


def assert_ack_without_finalization(authority: AuthorityFixture, command_id: UUID) -> None:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM durability_acknowledgements
                    WHERE tenant_id = %s AND client_command_id = %s
                ),
                EXISTS (
                    SELECT 1 FROM durability_acceptance_finalizations
                    WHERE tenant_id = %s AND client_command_id = %s
                )
            """,
            (
                authority.tenant.tenant_id,
                command_id,
                authority.tenant.tenant_id,
                command_id,
            ),
        ).fetchone()
    assert row == (True, False)


def assert_exact_refusal(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT status_code, response_body, event_ids
            FROM command_results WHERE client_command_id = %s
            """,
            (command_id,),
        ).fetchone()
    assert row is not None
    assert row["status_code"] == HTTP_CONFLICT
    assert cast(dict[str, object], row["response_body"])["code"] == "durability_pending"
    assert row["event_ids"] == []


def assert_no_relation(
    authority: AuthorityFixture, source_ticket_id: UUID, target_ticket_id: UUID
) -> None:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM ticket_relations
            WHERE tenant_id = %s AND source_ticket_id = %s AND target_ticket_id = %s
            """,
            (authority.tenant.tenant_id, source_ticket_id, target_ticket_id),
        ).fetchone()
    assert row == (0,)


def assert_secret_free_telemetry(captures: list[dict[str, object]], tenant: TenantFixture) -> None:
    encoded = json.dumps(captures, separators=(",", ":"), sort_keys=True)
    assert tenant.operator_credential not in encoded
    assert tenant.commander_credential not in encoded
    assert "postgresql://" not in encoded
    assert {str(item["reason"]) for item in captures} <= {
        "authorized",
        "committed",
        "durability_pending",
        "idempotency-conflict",
    }


def semantic_without_durability(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: semantic_without_durability(item)
            for key, item in value.items()
            if key != "durability_state"
        }
    if isinstance(value, list):
        return [semantic_without_durability(item) for item in value]
    return value


def set_target(authority: AuthorityFixture, identity: str) -> None:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE durability_policy_state
            SET standby_identity = %s, configured_at = clock_timestamp()
            WHERE singleton
            """,
            (identity,),
        )


def set_mode(authority: AuthorityFixture, mode: str) -> None:
    policy_ref = "ctower.pending-only@1" if mode == "pending_only" else "ctower.cutover-rpo0@1"
    with psycopg.connect(authority.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE durability_policy_state
            SET policy_ref = %s, mode = %s, configured_at = clock_timestamp()
            WHERE singleton
            """,
            (policy_ref, mode),
        )


def acceptance_position(authority: AuthorityFixture, command_id: UUID) -> int:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT acceptance_position FROM durability_acceptance_finalizations
            WHERE tenant_id = %s AND client_command_id = %s
            """,
            (authority.tenant.tenant_id, command_id),
        ).fetchone()
    if row is None:
        raise AssertionError("accepted command has no finalized acceptance position")
    return int(cast(int, row[0]))


def install_ack_delay(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION test_delay_durability_ack() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_sleep(3);
                RETURN NEW;
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER test_delay_durability_ack
            BEFORE INSERT ON durability_acknowledgements
            FOR EACH ROW EXECUTE FUNCTION test_delay_durability_ack()
            """
        )


def remove_ack_delay(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "DROP TRIGGER IF EXISTS test_delay_durability_ack ON durability_acknowledgements"
        )
        connection.execute("DROP FUNCTION IF EXISTS test_delay_durability_ack()")


def install_finalization_refusal(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION test_refuse_durability_finalization() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'test finalization refusal';
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER test_refuse_durability_finalization
            BEFORE INSERT ON durability_acceptance_finalizations
            FOR EACH ROW EXECUTE FUNCTION test_refuse_durability_finalization()
            """
        )


def remove_finalization_refusal(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            DROP TRIGGER IF EXISTS test_refuse_durability_finalization
            ON durability_acceptance_finalizations
            """
        )
        connection.execute("DROP FUNCTION IF EXISTS test_refuse_durability_finalization()")


def database_now(dsn: str) -> datetime:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None:
        raise RuntimeError("database clock was unavailable")
    return cast(datetime, row[0])


def create_ticket(
    client: TestClient,
    tenant: TenantFixture,
    command_id: UUID,
    *,
    title: str,
    credential: str | None = None,
    source_ref: str | None = None,
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P1",
                "source": {
                    "kind": "test",
                    "ref": source_ref or f"test:durability:{command_id}",
                },
                "title": title,
            },
            headers={
                **telemetry_headers(command_id),
                "Authorization": f"Bearer {credential or tenant.operator_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )


def change_priority(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/priority",
            json={
                "expected_version": 1,
                "priority": "P2",
                "reason": "Dependent mutation must wait for acknowledged subject state",
            },
            headers={
                **telemetry_headers(command_id, ticket_id=ticket_id),
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )


def add_relation(
    client: TestClient,
    tenant: TenantFixture,
    source_ticket_id: UUID,
    target_ticket_id: UUID,
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{source_ticket_id}/relations",
            json={
                "expected_version": 1,
                "reason": "Both relation endpoints must be acknowledged",
                "relation_kind": "depends_on",
                "target_ticket_id": str(target_ticket_id),
            },
            headers={
                **telemetry_headers(command_id, ticket_id=source_ticket_id),
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )
