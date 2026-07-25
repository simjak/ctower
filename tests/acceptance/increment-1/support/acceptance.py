"""Exact local acceptance fixture for tests that do not need a live standby pair."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.postgres import PostgresRecord

__all__ = ["accept_command", "accept_pending_commands"]


def accept_pending_commands(dsn: str, tenant_id: UUID) -> tuple[int, ...]:
    """Accept fixture commands in committed event order, once each."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT result.principal_id, result.client_command_id,
                min(event.record_position) AS first_position
            FROM command_results AS result
            JOIN events AS event
              ON event.tenant_id = result.tenant_id
             AND event.actor_principal_id = result.principal_id
             AND event.client_command_id = result.client_command_id
            JOIN outbox ON outbox.event_id = event.event_id
            LEFT JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = result.tenant_id
             AND confirmation.principal_id = result.principal_id
             AND confirmation.client_command_id = result.client_command_id
            WHERE result.tenant_id = %s AND confirmation.client_command_id IS NULL
            GROUP BY result.principal_id, result.client_command_id
            ORDER BY min(event.record_position), result.client_command_id
            """,
            (tenant_id,),
        ).fetchall()
    return tuple(
        accept_command(
            dsn,
            tenant_id,
            cast(UUID, row["principal_id"]),
            cast(UUID, row["client_command_id"]),
        )
        for row in rows
    )


def accept_command(dsn: str, tenant_id: UUID, principal_id: UUID, command_id: UUID) -> int:
    """Insert one complete receipt chain through administrator-only fixture authority."""

    now = datetime.now(UTC)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        command = connection.execute(
            """
            SELECT request_sha256 FROM command_results
            WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
            """,
            (tenant_id, principal_id, command_id),
        ).fetchone()
        if command is None:
            raise AssertionError("cannot accept a missing command")
        root = PostgresRecord(dsn).command_root(tenant_id, principal_id, command_id)
        assert not isinstance(root, RecordProblem), "cannot snapshot an unavailable command"
        receipt = connection.execute(
            """
            INSERT INTO durability_acknowledgements (
                tenant_id, principal_id, client_command_id, request_sha256, command_root,
                policy_ref, standby_application_name, standby_identity,
                standby_system_identifier, standby_timeline_id, standby_replay_lsn,
                acknowledged_at
            ) VALUES (%s, %s, %s, %s, %s, 'ctower.test-acceptance@1',
                'ctower_i1_ack', 'ctower-test-standby', 1, 1, '0/1', %s)
            RETURNING acceptance_position
            """,
            (
                tenant_id,
                principal_id,
                command_id,
                command["request_sha256"],
                root,
                now,
            ),
        ).fetchone()
        position = int(cast(int, cast(dict[str, object], receipt)["acceptance_position"]))
        common = (
            tenant_id,
            principal_id,
            command_id,
            command["request_sha256"],
            root,
            position,
            "ctower.test-acceptance@1",
            "ctower_i1_ack",
            "ctower-test-standby",
            1,
            1,
            "0/1",
            now,
        )
        connection.execute(
            """
            INSERT INTO durability_acceptance_finalizations (
                tenant_id, principal_id, client_command_id, request_sha256, command_root,
                acceptance_position, policy_ref, standby_application_name, standby_identity,
                standby_system_identifier, standby_timeline_id, standby_replay_lsn, finalized_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            common,
        )
        connection.execute(
            """
            INSERT INTO durability_acceptance_confirmations (
                tenant_id, principal_id, client_command_id, request_sha256, command_root,
                acceptance_position, policy_ref, standby_application_name, standby_identity,
                standby_system_identifier, standby_timeline_id, standby_replay_lsn, confirmed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            common,
        )
    return position
