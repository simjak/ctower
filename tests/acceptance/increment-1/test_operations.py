"""PostgreSQL acceptance for deterministic CP3-B control-loop truth."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from support.acceptance import accept_command
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.attention import Attention, PoisonDisposition, PoisonDispositionAction
from ctower_kernel.attention.postgres import PostgresAttention
from ctower_kernel.projections import (
    BoardQuery,
    BoardView,
    HealthContributorKey,
    HealthStatus,
    ProjectionHealth,
    Projections,
)
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import (
    Actor,
    DurabilityHealth,
    DurabilityHealthStatus,
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
_EXPECTED_DUE_OCCURRENCES = 2
_EARLIER_SYDNEY_OFFSET_SECONDS = 39600
_HTTP_OK = 200
_HTTP_ACCEPTED = 202
_HTTP_CONFLICT = 409
_HTTP_NOT_FOUND = 404


def test_control_loop_migration_adds_separate_immutable_and_cursor_state(
    tenant: TenantFixture,
) -> None:
    expected = {
        "attention_findings",
        "health_watermarks",
        "operation_jobs",
        "outbox_consumer_cursors",
        "outbox_delivery_attempts",
        "outbox_poison",
        "outbox_poison_dispositions",
        "routine_occurrences",
        "routine_revisions",
        "routine_triggers",
        "scheduler_watermarks",
        "workflow_start_facts",
    }

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()

    assert expected <= {str(row[0]) for row in rows}


def test_duplicate_scans_converge_and_backup_has_only_one_pending_job(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = RoutineRevision(
        routine_ref="ctower.i1.daily-backup@1",
        revision_digest="sha256:" + "4" * 64,
        schedule_kind=ScheduleKind.DAILY,
        timezone="UTC",
        local_time=time(1),
        concurrency=ConcurrencyPolicy.SERIALIZE_ONE_PENDING,
        catch_up=CatchUpPolicy.ENQUEUE_MISSED_WITH_CAP,
        catch_up_cap=1,
        handler_kind="daily_backup",
        timeout_seconds=7200,
        component_digests=("sha256:" + "5" * 64,),
    )
    first_fire = datetime.now(UTC).replace(hour=1, minute=0, second=0, microsecond=0) - timedelta(
        days=2
    )

    runtime.register(tenant.tenant_id, revision, first_fire_at=first_fire)
    first = runtime.scan(tenant.tenant_id)
    duplicate = runtime.scan(tenant.tenant_id)

    assert len(first.occurrences) >= _EXPECTED_DUE_OCCURRENCES
    assert sum(item.job_id is not None for item in first.occurrences) == 1
    assert len(first.jobs) == 1
    assert duplicate.occurrences == ()
    assert duplicate.jobs == ()


def test_routine_due_transaction_has_canonical_lineage_and_acceptance_gated_job(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = RoutineRevision(
        routine_ref="ctower.test.lineage@1",
        revision_digest="sha256:" + "6" * 64,
        schedule_kind=ScheduleKind.DAILY,
        timezone="UTC",
        local_time=time(1),
        concurrency=ConcurrencyPolicy.SERIALIZE_ONE_PENDING,
        catch_up=CatchUpPolicy.ENQUEUE_MISSED_WITH_CAP,
        catch_up_cap=1,
        handler_kind="daily_backup",
        timeout_seconds=60,
        component_digests=("sha256:" + "7" * 64,),
    )
    first_fire = datetime.now(UTC).replace(hour=1, minute=0, second=0, microsecond=0) - timedelta(
        days=1
    )

    runtime.register(tenant.tenant_id, revision, first_fire_at=first_fire)
    scan = runtime.scan(tenant.tenant_id)

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        lineage = connection.execute(
            """
            SELECT occurrence.occurrence_id, occurrence.actor_principal_id,
                occurrence.client_command_id, event.event_id, result.status_code,
                outbox.outbox_id, job.job_id
            FROM routine_occurrences AS occurrence
            JOIN events AS event
              ON event.tenant_id = occurrence.tenant_id
             AND event.actor_principal_id = occurrence.actor_principal_id
             AND event.client_command_id = occurrence.client_command_id
             AND event.aggregate_id = occurrence.occurrence_id
             AND event.kind = 'routine.occurrence_recorded'
            JOIN command_results AS result
              ON result.tenant_id = occurrence.tenant_id
             AND result.principal_id = occurrence.actor_principal_id
             AND result.client_command_id = occurrence.client_command_id
            JOIN outbox ON outbox.tenant_id = occurrence.tenant_id
             AND outbox.event_id = event.event_id
             AND outbox.topic = 'runtime.occurrences'
            LEFT JOIN operation_jobs AS job
              ON job.tenant_id = occurrence.tenant_id
             AND job.occurrence_id = occurrence.occurrence_id
            WHERE occurrence.tenant_id = %s
              AND occurrence.revision_digest = %s
            ORDER BY occurrence.scheduled_for
            """,
            (tenant.tenant_id, bytes.fromhex("6" * 64)),
        ).fetchall()
        pending_dispatchable = connection.execute(
            "SELECT count(*) FROM dispatchable_operation_jobs WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()

    assert len(lineage) == len(scan.occurrences)
    assert all(row["event_id"] is not None and row["outbox_id"] is not None for row in lineage)
    queued = [row for row in lineage if row["job_id"] is not None]
    assert len(queued) == 1
    assert pending_dispatchable is not None and pending_dispatchable["count"] == 0

    accepted = queued[0]
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        cast(UUID, accepted["actor_principal_id"]),
        cast(UUID, accepted["client_command_id"]),
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        dispatchable = connection.execute(
            "SELECT job_id FROM dispatchable_operation_jobs WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchall()
    assert dispatchable == [(accepted["job_id"],)]


def test_routine_dst_gap_is_a_visible_skipped_canonical_occurrence(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = RoutineRevision(
        routine_ref="ctower.test.dst-gap@1",
        revision_digest="sha256:" + "8" * 64,
        schedule_kind=ScheduleKind.DAILY,
        timezone="America/New_York",
        local_time=time(2, 30),
        concurrency=ConcurrencyPolicy.COALESCE_IF_ACTIVE,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="synthetic_four_stage",
        timeout_seconds=60,
        component_digests=("sha256:" + "9" * 64,),
    )
    gap_decision = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)

    runtime.register(tenant.tenant_id, revision, first_fire_at=gap_decision)
    runtime.scan(tenant.tenant_id)
    repeated_revision = RoutineRevision(
        routine_ref="ctower.test.dst-repeat@1",
        revision_digest="sha256:" + "a" * 64,
        schedule_kind=ScheduleKind.DAILY,
        timezone="Australia/Sydney",
        local_time=time(2, 30),
        concurrency=ConcurrencyPolicy.COALESCE_IF_ACTIVE,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="synthetic_four_stage",
        timeout_seconds=60,
        component_digests=("sha256:" + "b" * 64,),
    )
    earlier_repeat = datetime(2026, 4, 4, 15, 30, tzinfo=UTC)
    runtime.register(tenant.tenant_id, repeated_revision, first_fire_at=earlier_repeat)
    runtime.scan(tenant.tenant_id)

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT occurrence.local_civil_time, occurrence.utc_offset_seconds,
                occurrence.offset_decision, occurrence.outcome, event.payload
            FROM routine_occurrences AS occurrence
            JOIN events AS event
              ON event.tenant_id = occurrence.tenant_id
             AND event.actor_principal_id = occurrence.actor_principal_id
             AND event.client_command_id = occurrence.client_command_id
            WHERE occurrence.tenant_id = %s
              AND occurrence.revision_digest = %s
              AND occurrence.local_civil_time = timestamp '2026-03-08 02:30:00'
            """,
            (tenant.tenant_id, bytes.fromhex("8" * 64)),
        ).fetchone()
        repeated = connection.execute(
            """
            SELECT scheduled_for, local_civil_time, utc_offset_seconds, offset_decision
            FROM routine_occurrences
            WHERE tenant_id = %s AND revision_digest = %s
              AND local_civil_time = timestamp '2026-04-05 02:30:00'
            """,
            (tenant.tenant_id, bytes.fromhex("a" * 64)),
        ).fetchone()

    assert row is not None
    assert row["utc_offset_seconds"] is None
    assert row["offset_decision"] == "nonexistent_local_time"
    assert row["outcome"] == "skipped"
    assert row["payload"]["local_civil_time"] == "2026-03-08T02:30:00"
    assert row["payload"]["utc_offset_seconds"] is None
    assert repeated is not None
    assert repeated["scheduled_for"] == earlier_repeat
    assert repeated["utc_offset_seconds"] == _EARLIER_SYDNEY_OFFSET_SECONDS
    assert repeated["offset_decision"] == "earlier_offset"


def test_board_fold_excludes_pending_commands_and_rebuilds_accepted_facts_only(
    tenant: TenantFixture,
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=_command_id(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            project_key="ctower",
            source=SourceReference("test", "test:accepted-board"),
            title="Accepted Board fact",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))

    pending = projections.catch_up(tenant.tenant_id)
    pending_board = _board(projections, tenant)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )
    accepted = projections.catch_up(tenant.tenant_id)
    projections.rebuild(tenant.tenant_id)
    accepted_board = _board(projections, tenant)
    rebuilt_board = _board(projections, tenant)

    assert pending_board.cards == ()
    assert pending.source_watermark == 0
    assert accepted.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in accepted_board.cards] == [outcome.ticket.ticket_id]
    assert rebuilt_board.response_payload() == accepted_board.response_payload()


def test_poison_stops_partition_deduplicates_attention_and_retry_recovers(
    tenant: TenantFixture,
) -> None:
    ticket_id, outbox_id, original = _prepare_poisoned_ticket(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    poisoned = projections.catch_up(tenant.tenant_id)
    repeated = projections.catch_up(tenant.tenant_id)
    assert poisoned.health is ProjectionHealth.STATE_UNKNOWN
    assert repeated.projection_watermark == 0
    assert _poison_counts(tenant) == (1, 1, 1)

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE outbox SET payload = %s WHERE outbox_id = %s", (Jsonb(original), outbox_id)
        )
    command_id = uuid4()
    disposition, replay, changed, missing = _post_disposition_matrix(
        tenant, projections, outbox_id, command_id
    )
    assert disposition.status_code == _HTTP_ACCEPTED
    assert replay.status_code == _HTTP_ACCEPTED
    assert replay.json() == disposition.json()
    assert changed.status_code == _HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    assert missing.status_code == _HTTP_NOT_FOUND
    assert missing.json()["code"] == "poison-not-found"
    _assert_canonical_disposition(tenant, command_id)
    pending = projections.catch_up(tenant.tenant_id)
    assert pending.health is ProjectionHealth.STATE_UNKNOWN
    assert pending.projection_watermark == 0

    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        command_id,
    )
    recovered = projections.catch_up(tenant.tenant_id)

    assert recovered.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in _board(projections, tenant).cards] == [ticket_id]


def test_board_get_is_a_nonmutating_stored_projection_read(tenant: TenantFixture) -> None:
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    app = create_app(PostgresRecord(tenant.database.runtime_dsn), projections=projections)
    before = _projection_mutation_counts(tenant)
    command_id = uuid4()

    with TestClient(app) as client:
        response = client.get(
            "/v1/board",
            params={"project_key": "ctower"},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(command_id),
            },
        )
    after = _projection_mutation_counts(tenant)

    assert response.status_code == _HTTP_OK
    assert response.json()["health"] == "STATE_UNKNOWN"
    assert after == before


def test_accepted_tombstone_survives_projection_generation_rebuild(
    tenant: TenantFixture,
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            project_key="ctower",
            source=SourceReference("test", "test:tombstone-rebuild"),
            title="Tombstone rebuild",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )
    outbox_id, _ = _corrupt_outbox_schema(tenant, outcome.command_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    poisoned = projections.catch_up(tenant.tenant_id)
    assert poisoned.projection_watermark == 0

    command_id = uuid4()
    receipt = Attention(PostgresAttention(tenant.database.runtime_dsn)).disposition(
        actor,
        PoisonDisposition(
            client_command_id=command_id,
            consumer_key="board_projection",
            topic="record.events",
            outbox_id=outbox_id,
            action=PoisonDispositionAction.TOMBSTONE,
            reason="Policy-authorized invalid historical payload tombstone",
        ),
    )
    assert not isinstance(receipt, RecordProblem)
    pending = projections.catch_up(tenant.tenant_id)
    assert pending.projection_watermark == 0
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        command_id,
    )

    projections.catch_up(tenant.tenant_id)
    disposed_board = _board(projections, tenant)
    rebuilt = projections.rebuild(tenant.tenant_id)
    rebuilt_board = _board(projections, tenant)

    assert disposed_board.response_payload() == rebuilt_board.response_payload()
    assert rebuilt.health is ProjectionHealth.STATE_UNKNOWN
    assert rebuilt.projection_watermark == rebuilt.source_watermark == 1
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        attempts = connection.execute(
            """
            SELECT generation, attempt_number, outcome
            FROM outbox_delivery_attempts
            WHERE tenant_id = %s AND outbox_id = %s
            ORDER BY generation, attempt_number
            """,
            (tenant.tenant_id, outbox_id),
        ).fetchall()
    assert [(row["generation"], row["outcome"]) for row in attempts] == [
        (1, "poisoned"),
        (1, "tombstoned"),
        (2, "tombstoned"),
    ]


def test_fold_crash_replays_and_terminal_retry_requires_recovery(
    tenant: TenantFixture,
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            project_key="ctower",
            source=SourceReference("test", "test:fold-crash"),
            title="Fold crash replay",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )
    outbox_id = _outbox_id(tenant, outcome.command_id)
    _install_projection_failure(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))

    first = projections.catch_up(tenant.tenant_id)
    second = projections.catch_up(tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    failed_board = _board(projections, tenant)

    assert failed_board.cards == ()
    assert first.projection_watermark == second.projection_watermark == 0
    assert _poison_counts(tenant) == (3, 1, 1)

    _remove_projection_failure(tenant)
    recovery_command_id = uuid4()
    recovery = Attention(PostgresAttention(tenant.database.runtime_dsn)).disposition(
        actor,
        PoisonDisposition(
            client_command_id=recovery_command_id,
            consumer_key="board_projection",
            topic="record.events",
            outbox_id=outbox_id,
            action=PoisonDispositionAction.RETRY,
            reason="Projection constraint repaired",
        ),
    )
    assert not isinstance(recovery, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        recovery_command_id,
    )
    recovered = projections.catch_up(tenant.tenant_id)

    assert recovered.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in _board(projections, tenant).cards] == [
        outcome.ticket.ticket_id
    ]


def test_health_keeps_future_contributors_explicitly_unknown(tenant: TenantFixture) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    now = datetime.now(UTC)
    snapshot = Projections(PostgresProjections(tenant.database.projection_dsn)).health(
        actor,
        DurabilityHealth(
            DurabilityHealthStatus.HEALTHY,
            "ctower.test-acceptance@1",
            "ctower-test-standby",
            1,
            now,
            "current",
        ),
        now=now,
    )
    contributors = {
        item.key: item
        for dimension in (snapshot.availability, snapshot.completeness, snapshot.integrity)
        for item in dimension.contributors
    }

    assert set(contributors) == set(HealthContributorKey)
    for key in (
        HealthContributorKey.BACKUP,
        HealthContributorKey.ANCHOR,
        HealthContributorKey.OBJECT,
        HealthContributorKey.SYNTHETIC,
    ):
        assert contributors[key].status is HealthStatus.STATE_UNKNOWN
        assert contributors[key].watermark is None
        assert contributors[key].reason == "not-applicable-in-cp3-b"
    assert snapshot.status is HealthStatus.STATE_UNKNOWN

    command_id = uuid4()
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
    )
    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(command_id),
            },
        )
    assert response.status_code == _HTTP_OK
    assert response.json()["schema_id"] == "ctower.health/v1"


def _board(projections: Projections, tenant: TenantFixture) -> BoardView:
    result = projections.board(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        BoardQuery(project_key="ctower"),
    )
    assert not isinstance(result, RecordProblem), result
    return result


def _prepare_poisoned_ticket(tenant: TenantFixture) -> tuple[UUID, UUID, dict[str, object]]:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
            project_key="ctower",
            source=SourceReference("test", "test:poison-recovery"),
            title="Poison recovery",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )
    outbox_id, original = _corrupt_outbox_schema(tenant, outcome.command_id)
    return outcome.ticket.ticket_id, outbox_id, original


def _post_disposition_matrix(
    tenant: TenantFixture,
    projections: Projections,
    outbox_id: UUID,
    command_id: UUID,
) -> tuple[Response, Response, Response, Response]:
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=projections,
        attention=Attention(PostgresAttention(tenant.database.runtime_dsn)),
    )
    body = {
        "consumer_key": "board_projection",
        "topic": "record.events",
        "action": "retry",
        "reason": "Authored payload restored from immutable event",
    }
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    missing_id = uuid4()
    missing_headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(missing_id),
        **telemetry_headers(missing_id),
    }
    with TestClient(app) as client:
        disposition = client.post(
            f"/v1/outbox/{outbox_id}/dispositions", json=body, headers=headers
        )
        replay = client.post(f"/v1/outbox/{outbox_id}/dispositions", json=body, headers=headers)
        changed = client.post(
            f"/v1/outbox/{outbox_id}/dispositions",
            json={**body, "reason": "A different command body"},
            headers=headers,
        )
        missing = client.post(
            f"/v1/outbox/{uuid4()}/dispositions", json=body, headers=missing_headers
        )
    return disposition, replay, changed, missing


def _assert_canonical_disposition(tenant: TenantFixture, command_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        canonical = connection.execute(
            """
            SELECT count(*) FROM outbox_poison_dispositions AS disposition
            JOIN command_results AS result
              ON result.tenant_id = disposition.tenant_id
             AND result.principal_id = disposition.actor_principal_id
             AND result.client_command_id = disposition.client_command_id
            JOIN events AS event
              ON event.event_id = disposition.event_id
             AND event.tenant_id = disposition.tenant_id
             AND event.kind = 'attention.poison_disposition_recorded'
            JOIN outbox ON outbox.event_id = event.event_id
             AND outbox.tenant_id = event.tenant_id
             AND outbox.topic = 'attention.dispositions'
            WHERE disposition.tenant_id = %s
              AND disposition.actor_principal_id = %s
              AND disposition.client_command_id = %s
            """,
            (tenant.tenant_id, tenant.commander_id, command_id),
        ).fetchone()
    assert canonical == (1,)


def _corrupt_outbox_schema(
    tenant: TenantFixture, command_id: UUID
) -> tuple[UUID, dict[str, object]]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT outbox.outbox_id, outbox.payload FROM outbox
            JOIN events ON events.event_id = outbox.event_id
            WHERE events.tenant_id = %s AND events.client_command_id = %s
            """,
            (tenant.tenant_id, command_id),
        ).fetchone()
        assert row is not None
        original = dict(cast(dict[str, object], row["payload"]))
        poisoned = {**original, "schema_version": 99}
        connection.execute(
            "UPDATE outbox SET payload = %s WHERE outbox_id = %s",
            (Jsonb(poisoned), row["outbox_id"]),
        )
    return cast(UUID, row["outbox_id"]), original


def _outbox_id(tenant: TenantFixture, command_id: UUID) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT outbox.outbox_id FROM outbox JOIN events ON events.event_id = outbox.event_id
            WHERE events.tenant_id = %s AND events.client_command_id = %s
            """,
            (tenant.tenant_id, command_id),
        ).fetchone()
    assert row is not None
    return cast(UUID, row[0])


def _install_projection_failure(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION ctower_test_reject_board_fold() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test fold failure'; END $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER ctower_test_reject_board_fold
            BEFORE INSERT ON board_projection_rows
            FOR EACH ROW EXECUTE FUNCTION ctower_test_reject_board_fold()
            """
        )


def _remove_projection_failure(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute("DROP TRIGGER ctower_test_reject_board_fold ON board_projection_rows")
        connection.execute("DROP FUNCTION ctower_test_reject_board_fold()")


def _poison_counts(tenant: TenantFixture) -> tuple[int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        values = connection.execute(
            """
            SELECT (SELECT count(*) FROM outbox_delivery_attempts),
                (SELECT count(*) FROM outbox_poison),
                (SELECT count(*) FROM attention_findings)
            """
        ).fetchone()
    assert values is not None
    return (int(values[0]), int(values[1]), int(values[2]))


def _projection_mutation_counts(tenant: TenantFixture) -> tuple[int, int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        values = connection.execute(
            """
            SELECT (SELECT count(*) FROM board_projection_rows),
                (SELECT count(*) FROM projection_cursors),
                (SELECT count(*) FROM outbox_consumer_cursors),
                (SELECT count(*) FROM outbox_delivery_attempts)
            """
        ).fetchone()
    assert values is not None
    return (int(values[0]), int(values[1]), int(values[2]), int(values[3]))


def _command_id() -> UUID:
    return uuid4()


def _telemetry() -> TelemetryContext:
    command_id = str(_command_id())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )
