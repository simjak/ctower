"""Fixture history: live PROPERTIES reproduced, never live rows."""

from __future__ import annotations

import hashlib
import subprocess
import uuid
from datetime import UTC, datetime

import psycopg
from psycopg import sql

from tools.development_runtime._rehearsal_vocabulary import (
    FIXTURE_PROJECTS,
    FIXTURE_ROUTINE_EVENTS,
    FIXTURE_TICKETS,
    REPARSED_CONSTRAINT,
    REPARSED_TABLE,
    UpgradeRehearsalError,
)
from tools.development_runtime._rehearsal_cluster import Clone
from tools.development_runtime.host_commands import docker_path

__all__ = [
    "checkpoint_round_trip",
    "clone_counts",
    "clone_ledger",
    "inject_genuine_schema_drift",
    "seed_fixture_history",
]

# ---------------------------------------------------------------------------
# fixture history -- live PROPERTIES reproduced, never live rows
# ---------------------------------------------------------------------------


def seed_fixture_history(clone: Clone, live: LiveProperties) -> dict[str, int]:
    """Write the history a fresh database does not have: tickets, events, links, projections."""

    tickets = max(1, min(live.table_counts.get("tickets", FIXTURE_TICKETS), 200))
    routine = max(0, min(live.table_counts.get("events", 0) - tickets - 1, FIXTURE_ROUTINE_EVENTS))
    now = datetime.now(UTC)
    with psycopg.connect(clone.admin_dsn) as connection:
        tenant, operator, commander = _seed_principals(connection, now)
        position = _seed_tickets(connection, tenant, operator, commander, tickets, now)
        position = _seed_work_event(connection, tenant, operator, position, now)
        position, drifting = _seed_routine_events(connection, tenant, operator, routine, position, now)
        _seed_untracked_link(connection, tenant, drifting)
        _seed_projections(connection, tenant)
        connection.execute(
            "UPDATE record_position_ledger SET last_position = %s WHERE singleton", (position,)
        )
    return clone_counts(clone)


def _seed_principals(
    connection: psycopg.Connection[tuple[object, ...]], now: datetime
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant, operator, commander = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    connection.execute(
        "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
        (tenant, "ctower", "Ctower Rehearsal", now),
    )
    connection.cursor().executemany(
        """
        INSERT INTO principals (principal_id, tenant_id, kind, display_name, disabled, created_at)
        VALUES (%s, %s, %s, %s, false, %s)
        """,
        (
            (operator, tenant, "operator", "Rehearsal Operator", now),
            (commander, tenant, "commander", "Rehearsal Commander", now),
        ),
    )
    return tenant, operator, commander


def _seed_tickets(
    connection: psycopg.Connection[tuple[object, ...]],
    tenant: uuid.UUID,
    operator: uuid.UUID,
    commander: uuid.UUID,
    count: int,
    now: datetime,
) -> int:
    """One created ticket per row, with the event, link, command result and outbox row it carries."""

    for index in range(1, count + 1):
        project = FIXTURE_PROJECTS[index % len(FIXTURE_PROJECTS)]
        ticket = uuid.uuid4()
        priority = "P1" if index % 2 else "P2"
        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, tenant_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, durability_state, created_by, created_at,
                project_key
            ) VALUES (%s, %s, %s, 'mission-control-request', %s, %s, %s, 1,
                      'durability_pending', %s, %s, %s)
            """,
            (
                ticket,
                tenant,
                f"{project} rehearsal ticket {index}",
                f"{project}-R{index}",
                priority,
                commander,
                operator,
                now,
                project,
            ),
        )
        event = _append_event(
            connection,
            tenant=tenant,
            actor=operator,
            kind="ticket.created",
            stream=f"ticket:{ticket}",
            aggregate=ticket,
            position=index,
            origin="api",
            now=now,
        )
        _link_event(connection, event, tenant, "ticket", ticket)
    return count


def _seed_work_event(
    connection: psycopg.Connection[tuple[object, ...]],
    tenant: uuid.UUID,
    operator: uuid.UUID,
    position: int,
    now: datetime,
) -> int:
    work = uuid.uuid4()
    position += 1
    event = _append_event(
        connection,
        tenant=tenant,
        actor=operator,
        kind="work.changed",
        stream=f"work:{work}",
        aggregate=work,
        position=position,
        origin="control_worker",
        now=now,
    )
    _link_event(connection, event, tenant, "work", work)
    return position


def _seed_routine_events(
    connection: psycopg.Connection[tuple[object, ...]],
    tenant: uuid.UUID,
    operator: uuid.UUID,
    count: int,
    position: int,
    now: datetime,
) -> tuple[int, uuid.UUID | None]:
    """Unlinked control-worker history, the bulk of what a used box accumulates."""

    routine = uuid.uuid4()
    last: uuid.UUID | None = None
    for sequence in range(1, count + 1):
        position += 1
        last = _append_event(
            connection,
            tenant=tenant,
            actor=operator,
            kind="routine.occurrence_recorded",
            stream=f"routine:{routine}",
            aggregate=routine,
            position=position,
            origin="control_worker",
            now=now,
            sequence=sequence,
        )
    return position, last


def _seed_untracked_link(
    connection: psycopg.Connection[tuple[object, ...]],
    tenant: uuid.UUID,
    event: uuid.UUID | None,
) -> None:
    """The link a used database holds that the pre-ledger mirror query cannot derive.

    The live box carries exactly one such link. It is not corruption: append_event links whatever
    subject its caller names, including kinds the mirror in `event-link-backfill` never
    enumerated. Reproducing it is what makes the clone's precondition vector equal the live one.
    """

    if event is None:
        return
    connection.execute(
        """
        INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
        SELECT %s, %s, 'ticket', ticket_id FROM tickets WHERE tenant_id = %s
        ORDER BY ticket_id LIMIT 1
        """,
        (event, tenant, tenant),
    )


def _append_event(
    connection: psycopg.Connection[tuple[object, ...]],
    *,
    tenant: uuid.UUID,
    actor: uuid.UUID,
    kind: str,
    stream: str,
    aggregate: uuid.UUID,
    position: int,
    origin: str,
    now: datetime,
    sequence: int = 1,
) -> uuid.UUID:
    """One event plus the command result and outbox row the real writer commits with it."""

    event, command = uuid.uuid4(), uuid.uuid4()
    request = hashlib.sha256(f"{kind}:{position}".encode()).digest()
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id, causation_id,
            origin, server_time, payload, prev_hash, event_hash, record_position
        ) VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, NULL, %s, %s, '{}'::jsonb, %s, %s, %s)
        """,
        (
            event,
            tenant,
            stream,
            aggregate,
            sequence,
            kind,
            actor,
            command,
            request,
            uuid.uuid4(),
            origin,
            now,
            bytes(32),
            hashlib.sha256(str(event).encode()).digest(),
            position,
        ),
    )
    connection.execute(
        """
        INSERT INTO command_results (
            tenant_id, principal_id, client_command_id, request_sha256, status_code,
            response_body, event_ids, created_at
        ) VALUES (%s, %s, %s, %s, 201, '{}'::jsonb, %s, %s)
        """,
        (tenant, actor, command, request, [event], now),
    )
    connection.execute(
        """
        INSERT INTO outbox (outbox_id, tenant_id, event_id, topic, payload, telemetry, created_at)
        VALUES (%s, %s, %s, %s, '{}'::jsonb,
                '{"schema": "ctower.telemetry-context/v1"}'::jsonb, %s)
        """,
        (uuid.uuid4(), tenant, event, "record.events", now),
    )
    return event


def _link_event(
    connection: psycopg.Connection[tuple[object, ...]],
    event: uuid.UUID,
    tenant: uuid.UUID,
    kind: str,
    subject: uuid.UUID,
) -> None:
    connection.execute(
        "INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)"
        " VALUES (%s,%s,%s,%s)",
        (event, tenant, kind, subject),
    )


def _seed_projections(
    connection: psycopg.Connection[tuple[object, ...]], tenant: uuid.UUID
) -> None:
    """Seed the read-side exactly as the authored backfills derive it, so no mirror check drifts."""

    connection.execute(
        """
        INSERT INTO board_projection_rows (
            tenant_id, ticket_id, title, lane, underlying_lane, priority, custodian_id,
            delivery_facts, ticket_version, source_position, source_kind, source_ref,
            project_key
        )
        SELECT ticket.tenant_id, ticket.ticket_id, ticket.title, 'backlog', 'backlog',
               ticket.priority, ticket.custodian_principal_id, '[]'::jsonb, ticket.version,
               COALESCE(event.record_position, 0), ticket.source_kind, ticket.source_ref,
               ticket.project_key
        FROM tickets AS ticket
        LEFT JOIN events AS event ON event.aggregate_id = ticket.ticket_id
                                 AND event.kind = 'ticket.created'
        WHERE ticket.tenant_id = %s
        """,
        (tenant,),
    )
    connection.execute(
        """
        INSERT INTO lifecycle_episodes (ticket_id, tenant_id, episode_number, state, opened_at)
        SELECT ticket_id, tenant_id, 1, 'open', created_at FROM tickets WHERE tenant_id = %s
        """,
        (tenant,),
    )
    connection.execute(
        """
        INSERT INTO priority_facts (
            ticket_id, tenant_id, fact_sequence, priority, changed_by, reason,
            client_command_id, recorded_at
        )
        SELECT ticket.ticket_id, ticket.tenant_id, 1, ticket.priority, ticket.created_by,
               'rehearsal fixture history', event.client_command_id, ticket.created_at
        FROM tickets AS ticket
        JOIN events AS event ON event.aggregate_id = ticket.ticket_id
                            AND event.kind = 'ticket.created'
        WHERE ticket.tenant_id = %s
        """,
        (tenant,),
    )
    connection.execute(
        """
        INSERT INTO durability_subject_heads (
            tenant_id, subject_kind, subject_id, principal_id, client_command_id, updated_at
        )
        SELECT DISTINCT ON (link.tenant_id, link.subject_kind, link.subject_id)
               link.tenant_id, link.subject_kind, link.subject_id, event.actor_principal_id,
               event.client_command_id, event.server_time
        FROM event_links AS link
        JOIN events AS event ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
        JOIN command_results AS result
          ON result.tenant_id = event.tenant_id
         AND result.principal_id = event.actor_principal_id
         AND result.client_command_id = event.client_command_id
        WHERE link.tenant_id = %s
        ORDER BY link.tenant_id, link.subject_kind, link.subject_id,
                 event.record_position DESC, event.event_id DESC
        """,
        (tenant,),
    )


def clone_counts(clone: Clone) -> dict[str, int]:
    with psycopg.connect(clone.admin_dsn) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()
        ]
        return {
            table: int(
                connection.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(
                        sql.Identifier(table)
                    )
                ).fetchone()[0]
            )
            for table in tables
        }


def clone_ledger(clone: Clone) -> tuple[int, str | None]:
    with psycopg.connect(clone.admin_dsn) as connection:
        row = connection.execute(
            "SELECT count(*), max(migration_id) FROM ctower_schema_migrations"
        ).fetchone()
    if row is None:
        raise UpgradeRehearsalError("the clone carries no migration ledger")
    return int(row[0]), None if row[1] is None else str(row[1])


def _clone_ledger_attestation(clone: Clone) -> str:
    with psycopg.connect(clone.admin_dsn) as connection:
        row = connection.execute(
            "SELECT result_schema_sha256 FROM ctower_schema_migrations "
            "ORDER BY migration_id DESC LIMIT 1"
        ).fetchone()
    return str(row[0]) if row and row[0] else ""  # type: ignore[unreachable]


def checkpoint_round_trip(clone: Clone) -> None:
    """Replay what the live box underwent: `checkpoint` captures a pg_dump, `restore` replays it.

    Proven mechanism, not a guess: this round trip on a clean base clone reproduces the live
    fingerprint byte for byte, because pg_dump re-deparses one CHECK constraint into a form the
    original migration never wrote.
    """

    docker = docker_path()
    dumped = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            docker, "exec", "--user", "postgres", clone.container, "pg_dump", "--create",
            "--clean", "--if-exists", "--quote-all-identifiers", "--dbname", DATABASE_NAME,
        ],
        check=True,
        capture_output=True,
    ).stdout
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            docker, "exec", "--interactive", "--user", "postgres", clone.container, "psql",
            "--no-psqlrc", "--quiet", "--set", "ON_ERROR_STOP=1", "--username", "postgres",
            "--dbname", "postgres",
        ],
        input=dumped,
        check=True,
        capture_output=True,
    )


def inject_genuine_schema_drift(clone: Clone) -> None:
    """Mutate the schema record set, not only PostgreSQL's deparse text."""

    with psycopg.connect(clone.admin_dsn) as connection:
        exists = connection.execute(
            """
            SELECT 1
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS class ON class.oid = constraint_row.conrelid
            WHERE class.relname = %s AND constraint_row.conname = %s
            """,
            (REPARSED_TABLE, REPARSED_CONSTRAINT),
        ).fetchone()
        if exists is None:
            raise UpgradeRehearsalError(
                f"cannot inject genuine drift: {REPARSED_TABLE}.{REPARSED_CONSTRAINT} is absent"
            )
        connection.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.Identifier(REPARSED_TABLE),
                sql.Identifier(REPARSED_CONSTRAINT),
            )
        )


