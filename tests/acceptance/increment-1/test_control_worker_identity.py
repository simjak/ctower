"""Real-PostgreSQL matrix for the tenant-stable control-worker identity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.acceptance import accept_command
from support.postgres import DatabaseFixture
from support.tenant_fixture import TenantFixture, create_first_tenant, create_second_tenant

from ctower_api.control_worker import build_worker
from ctower_kernel.projections import BoardQuery, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    Routine,
    RoutineRevision,
    ScheduleKind,
)
from ctower_kernel.runtime.postgres import PostgresRuntime
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

__all__: tuple[str, ...] = ()
_ROOT = Path(__file__).parents[3]
_HUMAN_COLLISION = "ctower control worker"
_CONCURRENT_REGISTRATIONS = 8
_EXPECTED_TENANTS = 2
_MAX_HUMAN_DISPLAY_NAME_LENGTH = 120


@pytest.mark.parametrize("collision_kind", ["operator", "commander"])
def test_bootstrap_display_collision_completes_worker_and_accepted_outbox(
    database: DatabaseFixture,
    collision_kind: str,
) -> None:
    names = {
        "commander_name": (
            _HUMAN_COLLISION if collision_kind == "commander" else "Ctower Commander"
        ),
        "operator_name": (_HUMAN_COLLISION if collision_kind == "operator" else "First Operator"),
    }
    tenant = create_first_tenant(database, **names)
    ticket_id = _accepted_ticket(tenant, f"worker-collision-{collision_kind}")
    runtime = Routine(PostgresRuntime(database.runtime_dsn))
    projections = Projections(PostgresProjections(database.projection_dsn))

    build_worker(runtime, projections, pack_root=_ROOT / "packs").tick()

    actor = Actor(
        tenant.commander_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"ctower"}),
    )
    board = projections.board(actor, BoardQuery(project_key="ctower"))
    assert not isinstance(board, RecordProblem), board
    assert [card.ticket_id for card in board.cards] == [ticket_id]
    workers = _worker_rows(database.admin_dsn, tenant.tenant_id)
    assert len(workers) == 1
    _assert_credential_free(workers[0])
    with psycopg.connect(database.admin_dsn) as connection:
        collision = connection.execute(
            """
            SELECT principal_id FROM principals
            WHERE tenant_id = %s AND kind = %s AND display_name = %s
            """,
            (tenant.tenant_id, collision_kind, _HUMAN_COLLISION),
        ).fetchone()
    assert collision is not None and collision[0] != workers[0]["principal_id"]


def test_repeated_concurrent_registration_is_one_per_tenant_accepted_lineage(
    database: DatabaseFixture,
) -> None:
    first = create_first_tenant(database, commander_name=_HUMAN_COLLISION)
    second = create_second_tenant(database)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            "UPDATE principals SET display_name = %s WHERE principal_id = %s",
            (_HUMAN_COLLISION, second.operator_id),
        )
    runtime = Routine(PostgresRuntime(database.runtime_dsn))
    revision = _revision("shared-worker-identity", "c", "d")
    first_fire = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    _register_concurrently(runtime, first.tenant_id, revision, first_fire)
    _register_concurrently(runtime, second.tenant_id, revision, first_fire)
    runtime.register(first.tenant_id, revision, first_fire_at=first_fire)
    runtime.register(second.tenant_id, revision, first_fire_at=first_fire)
    first_scan = runtime.scan(first.tenant_id)
    second_scan = runtime.scan(second.tenant_id)

    assert len(first_scan.occurrences) == len(second_scan.occurrences) == 1
    assert runtime.scan(first.tenant_id).occurrences == ()
    assert runtime.scan(second.tenant_id).occurrences == ()
    workers = (
        _worker_rows(database.admin_dsn, first.tenant_id),
        _worker_rows(database.admin_dsn, second.tenant_id),
    )
    assert tuple(len(rows) for rows in workers) == (1, 1)
    assert workers[0][0]["principal_id"] != workers[1][0]["principal_id"]
    for rows in workers:
        _assert_credential_free(rows[0])

    pending = _pending_lineages(database.admin_dsn, revision)
    assert len(pending) == _EXPECTED_TENANTS
    for row in pending:
        accept_command(
            database.admin_dsn,
            cast(UUID, row["tenant_id"]),
            cast(UUID, row["actor_principal_id"]),
            cast(UUID, row["client_command_id"]),
        )
    accepted = _accepted_lineages(database.admin_dsn, revision)
    assert {row["tenant_id"] for row in accepted} == {first.tenant_id, second.tenant_id}
    assert all(row["trigger_count"] == 1 for row in accepted)
    assert all(row["canonical_count"] == 1 for row in accepted)


@pytest.mark.parametrize("invalid_state", ["wrong_kind", "disabled"])
def test_invalid_deterministic_identity_fails_closed_without_trigger(
    database: DatabaseFixture,
    invalid_state: str,
) -> None:
    tenant = create_first_tenant(database)
    runtime = Routine(PostgresRuntime(database.runtime_dsn))
    seed = _revision("identity-seed", "e", "f")
    rejected = _revision("identity-rejected", "1", "2")
    runtime.register(tenant.tenant_id, seed)
    worker = _worker_rows(database.admin_dsn, tenant.tenant_id)[0]
    worker_id = cast(UUID, worker["principal_id"])

    with psycopg.connect(database.admin_dsn) as connection:
        if invalid_state == "wrong_kind":
            connection.execute(
                """
                UPDATE principals SET kind = 'commander', display_name = %s
                WHERE principal_id = %s
                """,
                ("Wrong kind at deterministic machine identity", worker_id),
            )
        else:
            connection.execute(
                "UPDATE principals SET disabled = true WHERE principal_id = %s",
                (worker_id,),
            )

    with pytest.raises(RuntimeError, match="principal is unavailable"):
        runtime.register(tenant.tenant_id, rejected)
    with psycopg.connect(database.admin_dsn) as connection:
        trigger_count = connection.execute(
            """
            SELECT count(*) FROM routine_triggers
            WHERE tenant_id = %s AND revision_digest = %s
            """,
            (tenant.tenant_id, bytes.fromhex(rejected.revision_digest.removeprefix("sha256:"))),
        ).fetchone()
        identity = connection.execute(
            "SELECT principal_id, kind, disabled FROM principals WHERE principal_id = %s",
            (worker_id,),
        ).fetchone()
    assert trigger_count == (0,)
    assert identity is not None
    assert identity[0] == worker_id
    assert identity[1:] == (
        ("commander", False) if invalid_state == "wrong_kind" else ("control_worker", True)
    )


def _accepted_ticket(tenant: TenantFixture, source_ref: str) -> UUID:
    command_id = uuid4()
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        TicketCommand(
            client_command_id=command_id,
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            project_key="ctower",
            source=SourceReference("test", source_ref),
            title="Accepted outbox survives worker display collision",
        ),
        telemetry=_telemetry(tenant, command_id),
    )
    assert not isinstance(outcome, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        command_id,
    )
    return outcome.ticket.ticket_id


def _telemetry(tenant: TenantFixture, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(tenant.tenant_id),
        actor_id=str(tenant.commander_id),
        command_id=str(command_id),
    )


def _revision(name: str, digest: str, component: str) -> RoutineRevision:
    return RoutineRevision(
        routine_ref=f"ctower.test.{name}@1",
        revision_digest="sha256:" + digest * 64,
        schedule_kind=ScheduleKind.HOURLY,
        timezone="UTC",
        local_time=None,
        concurrency=ConcurrencyPolicy.SERIALIZE_ONE_PENDING,
        catch_up=CatchUpPolicy.ENQUEUE_MISSED_WITH_CAP,
        catch_up_cap=1,
        handler_kind="record_anchor",
        timeout_seconds=60,
        component_digests=("sha256:" + component * 64,),
    )


def _register_concurrently(
    runtime: Routine,
    tenant_id: UUID,
    revision: RoutineRevision,
    first_fire: datetime,
) -> None:
    def register_once(_index: int) -> None:
        runtime.register(tenant_id, revision, first_fire_at=first_fire)

    with ThreadPoolExecutor(max_workers=_CONCURRENT_REGISTRATIONS) as executor:
        tuple(executor.map(register_once, range(_CONCURRENT_REGISTRATIONS)))


def _worker_rows(dsn: str, tenant_id: UUID) -> list[dict[str, object]]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT principal.principal_id, principal.display_name, principal.disabled,
                principal.credential_ref, principal.vault_ref,
                count(credential.credential_id) FILTER (
                    WHERE credential.revoked_at IS NULL
                ) AS active_credentials
            FROM principals AS principal
            LEFT JOIN principal_credentials AS credential
              ON credential.principal_id = principal.principal_id
             AND credential.tenant_id = principal.tenant_id
            WHERE principal.tenant_id = %s AND principal.kind = 'control_worker'
            GROUP BY principal.principal_id
            ORDER BY principal.principal_id
            """,
            (tenant_id,),
        ).fetchall()
    return cast(list[dict[str, object]], rows)


def _assert_credential_free(worker: dict[str, object]) -> None:
    assert worker["disabled"] is False
    assert worker["credential_ref"] is None
    assert worker["vault_ref"] is None
    assert worker["active_credentials"] == 0
    assert len(str(worker["display_name"])) > _MAX_HUMAN_DISPLAY_NAME_LENGTH


def _pending_lineages(dsn: str, revision: RoutineRevision) -> list[dict[str, object]]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT tenant_id, actor_principal_id, client_command_id
            FROM routine_occurrences
            WHERE revision_digest = %s
            ORDER BY tenant_id
            """,
            (bytes.fromhex(revision.revision_digest.removeprefix("sha256:")),),
        ).fetchall()
    return cast(list[dict[str, object]], rows)


def _accepted_lineages(dsn: str, revision: RoutineRevision) -> list[dict[str, object]]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT occurrence.tenant_id,
                count(*) AS canonical_count,
                (
                    SELECT count(*) FROM routine_triggers AS trigger
                    WHERE trigger.tenant_id = occurrence.tenant_id
                      AND trigger.revision_digest = occurrence.revision_digest
                ) AS trigger_count
            FROM routine_occurrences AS occurrence
            JOIN events AS event
              ON event.tenant_id = occurrence.tenant_id
             AND event.actor_principal_id = occurrence.actor_principal_id
             AND event.client_command_id = occurrence.client_command_id
             AND event.aggregate_id = occurrence.occurrence_id
            JOIN command_results AS result
              ON result.tenant_id = occurrence.tenant_id
             AND result.principal_id = occurrence.actor_principal_id
             AND result.client_command_id = occurrence.client_command_id
            JOIN outbox
              ON outbox.tenant_id = event.tenant_id AND outbox.event_id = event.event_id
            JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = occurrence.tenant_id
             AND confirmation.principal_id = occurrence.actor_principal_id
             AND confirmation.client_command_id = occurrence.client_command_id
            WHERE occurrence.revision_digest = %s
            GROUP BY occurrence.tenant_id, occurrence.revision_digest
            ORDER BY occurrence.tenant_id
            """,
            (bytes.fromhex(revision.revision_digest.removeprefix("sha256:")),),
        ).fetchall()
    return cast(list[dict[str, object]], rows)
