"""PostgreSQL acceptance for deterministic CP3-B control-loop truth."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from support.acceptance import accept_command
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.attention import Attention, PoisonDisposition, PoisonDispositionAction
from ctower_kernel.attention.postgres import PostgresAttention
from ctower_kernel.projections import (
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
_HTTP_OK = 200
_HTTP_ACCEPTED = 202


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
            source=SourceReference("test", "test:accepted-board"),
            title="Accepted Board fact",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))

    pending = projections.catch_up(tenant.tenant_id)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )
    accepted = projections.catch_up(tenant.tenant_id)
    rebuilt = projections.rebuild(tenant.tenant_id)

    assert pending.cards == ()
    assert pending.source_watermark == 0
    assert accepted.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in accepted.cards] == [outcome.ticket.ticket_id]
    assert rebuilt.response_payload() == accepted.response_payload()


def test_poison_stops_partition_deduplicates_attention_and_retry_recovers(
    tenant: TenantFixture,
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
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
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))

    poisoned = projections.catch_up(tenant.tenant_id)
    repeated = projections.catch_up(tenant.tenant_id)
    counts = _poison_counts(tenant)

    assert poisoned.health is ProjectionHealth.STATE_UNKNOWN
    assert repeated.projection_watermark == 0
    assert counts == (1, 1, 1)

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE outbox SET payload = %s WHERE outbox_id = %s", (Jsonb(original), outbox_id)
        )
    command_id = uuid4()
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=projections,
        attention=Attention(PostgresAttention(tenant.database.runtime_dsn)),
    )
    with TestClient(app) as client:
        disposition = client.post(
            f"/v1/outbox/{outbox_id}/dispositions",
            json={
                "consumer_key": "board_projection",
                "topic": "record.events",
                "action": "retry",
                "reason": "Authored payload restored from immutable event",
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        )
    assert disposition.status_code == _HTTP_ACCEPTED
    recovered = projections.catch_up(tenant.tenant_id)

    assert recovered.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in recovered.cards] == [outcome.ticket.ticket_id]


def test_board_get_is_a_nonmutating_stored_projection_read(tenant: TenantFixture) -> None:
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    app = create_app(PostgresRecord(tenant.database.runtime_dsn), projections=projections)
    before = _projection_mutation_counts(tenant)
    command_id = uuid4()

    with TestClient(app) as client:
        response = client.get(
            "/v1/board",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(command_id),
            },
        )
    after = _projection_mutation_counts(tenant)

    assert response.status_code == _HTTP_OK
    assert response.json()["health"] == "STATE_UNKNOWN"
    assert after == before


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
    terminal = projections.catch_up(tenant.tenant_id)

    assert first.cards == second.cards == terminal.cards == ()
    assert first.projection_watermark == second.projection_watermark == 0
    assert _poison_counts(tenant) == (3, 1, 1)

    _remove_projection_failure(tenant)
    Attention(PostgresAttention(tenant.database.runtime_dsn)).disposition(
        actor,
        PoisonDisposition(
            client_command_id=uuid4(),
            consumer_key="board_projection",
            topic="record.events",
            outbox_id=outbox_id,
            action=PoisonDispositionAction.RETRY,
            reason="Projection constraint repaired",
        ),
    )
    recovered = projections.catch_up(tenant.tenant_id)

    assert recovered.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in recovered.cards] == [outcome.ticket.ticket_id]


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
