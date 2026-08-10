"""Isolated physical restore proof for first-class Request authority."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from support.acceptance import accept_pending_commands
from support.postgres import (
    PostgresServer,
    create_database,
    drop_database,
)
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestCapture,
    RequestCaptureResult,
    RequestChangeResult,
    RequestPriority,
    Requests,
)
from tools.process_execution import run

__all__: tuple[str, ...] = ()

_REQUEST_TABLES = (
    "request_number_allocators",
    "requests",
    "request_owner_facts",
    "request_priority_facts",
    "request_triage_facts",
    "request_ticket_relation_facts",
    "request_blocker_facts",
    "request_closure_evaluations",
    "request_attention_facts",
    "request_import_manifests",
)
_PROCESS_TIMEOUT_SECONDS = 30


def test_isolated_restore_preserves_complete_request_authority_and_high_water(
    tenant: TenantFixture,
    postgres_17: PostgresServer,
    tmp_path: Path,
) -> None:
    """OR-08: allocator, facts, aliases, events, ACKs, and outbox restore together."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    capture = RequestCapture(uuid4(), "ctower", "Restore this durable operator intent.")
    captured = authority.capture(
        actor, capture, telemetry=_telemetry(actor, capture.client_command_id)
    )
    assert isinstance(captured, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    replay = authority.capture(
        actor, capture, telemetry=_telemetry(actor, capture.client_command_id)
    )
    assert replay == captured
    priority = RequestPriority(uuid4(), captured.request_id, 1, "P1", "restore denominator")
    prioritized = authority.prioritize(
        actor,
        priority,
        telemetry=_telemetry(actor, priority.client_command_id),
    )
    assert isinstance(prioritized, RequestChangeResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    source_inventory = _inventory(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        command_ids=(capture.client_command_id, priority.client_command_id),
    )
    _assert_event_complete(tenant.database.admin_dsn, tenant.tenant_id)
    restored = create_database(postgres_17)
    dump = tmp_path / "request-authority.dump"
    try:
        _physical_restore(tenant.database.admin_dsn, restored.admin_dsn, dump)
        restored_inventory = _inventory(
            restored.admin_dsn,
            tenant.tenant_id,
            command_ids=(capture.client_command_id, priority.client_command_id),
        )
        _assert_event_complete(restored.admin_dsn, tenant.tenant_id)
        assert restored_inventory == source_inventory

        restored_authority = Requests(PostgresRequests(restored.runtime_dsn))
        next_command = RequestCapture(uuid4(), "ctower", "First request after restore.")
        next_result = restored_authority.capture(
            actor,
            next_command,
            telemetry=_telemetry(actor, next_command.client_command_id),
        )
        assert isinstance(next_result, RequestCaptureResult)
        assert next_result.request_number == captured.request_number + 1
    finally:
        drop_database(restored)

    print(
        "REAL_REQUEST_RESTORE"
        f" digest={_digest(source_inventory)}"
        f" requests={len(source_inventory['requests'])}"
        f" request_events={len(source_inventory['request_events'])}"
        f" next_number={captured.request_number + 1}"
    )


def _physical_restore(source_dsn: str, target_dsn: str, dump: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if pg_dump is None or pg_restore is None:
        raise RuntimeError("PostgreSQL client tools are required for restore acceptance")
    run(
        (pg_dump, "--format=custom", f"--file={dump}", source_dsn),
        check=True,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
        capture_output=True,
    )
    run(
        (pg_restore, "--no-owner", f"--dbname={target_dsn}", str(dump)),
        check=True,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
        capture_output=True,
    )


def _inventory(
    dsn: str,
    tenant_id: UUID,
    *,
    command_ids: tuple[UUID, ...],
) -> dict[str, list[object]]:
    inventory: dict[str, list[object]] = {}
    with psycopg.connect(dsn) as connection:
        for table in _REQUEST_TABLES:
            query = sql.SQL(
                "SELECT to_jsonb(row_value) FROM {} AS row_value "
                "WHERE tenant_id = %s ORDER BY to_jsonb(row_value)::text"
            ).format(sql.Identifier(table))
            inventory[table] = [row[0] for row in connection.execute(query, (tenant_id,))]
        inventory["request_events"] = _json_rows(
            connection,
            "SELECT to_jsonb(event_row) FROM events AS event_row "
            "WHERE tenant_id = %s AND kind = 'request.changed' "
            "ORDER BY stream_id, sequence",
            (tenant_id,),
        )
        inventory["request_event_links"] = _json_rows(
            connection,
            "SELECT to_jsonb(link_row) FROM event_links AS link_row "
            "WHERE tenant_id = %s AND subject_kind = 'request' "
            "ORDER BY event_id, subject_id",
            (tenant_id,),
        )
        inventory["request_outbox"] = _json_rows(
            connection,
            "SELECT to_jsonb(outbox_row) FROM outbox AS outbox_row "
            "WHERE tenant_id = %s AND event_id IN ("
            "SELECT event_id FROM events WHERE tenant_id = %s AND kind = 'request.changed'"
            ") ORDER BY event_id, topic",
            (tenant_id, tenant_id),
        )
        inventory["request_command_results"] = _json_rows(
            connection,
            "SELECT to_jsonb(result_row) FROM command_results AS result_row "
            "WHERE tenant_id = %s AND client_command_id = ANY(%s) "
            "ORDER BY client_command_id",
            (tenant_id, list(command_ids)),
        )
        inventory["request_inbound_events"] = _json_rows(
            connection,
            "SELECT to_jsonb(inbound_row) FROM inbound_events AS inbound_row "
            "WHERE tenant_id = %s AND initial_outcome = 'request_created' "
            "ORDER BY inbound_event_id",
            (tenant_id,),
        )
    return inventory


def _json_rows(
    connection: psycopg.Connection[tuple[object, ...]],
    statement: str,
    parameters: tuple[object, ...],
) -> list[object]:
    return [row[0] for row in connection.execute(statement, parameters)]


def _assert_event_complete(dsn: str, tenant_id: UUID) -> None:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            """
            SELECT request.request_id, request.version,
                   count(event.event_id), min(event.sequence), max(event.sequence),
                   bool_and((event.payload ->> 'version')::integer = event.sequence)
            FROM requests AS request
            JOIN events AS event
              ON event.tenant_id = request.tenant_id
             AND event.aggregate_id = request.request_id
             AND event.kind = 'request.changed'
            WHERE request.tenant_id = %s
            GROUP BY request.request_id, request.version
            ORDER BY request.request_id
            """,
            (tenant_id,),
        ).fetchall()
        allocator = connection.execute(
            "SELECT last_number FROM request_number_allocators WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        maximum = connection.execute(
            "SELECT max(request_number) FROM requests WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
    assert rows
    assert all(
        count == version and minimum == 1 and maximum_sequence == version
        for _, version, count, minimum, maximum_sequence, _payload_matches in rows
    )
    assert all(payload_matches for *_, payload_matches in rows)
    assert allocator is not None and maximum is not None
    assert allocator[0] == maximum[0]


def _digest(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )
