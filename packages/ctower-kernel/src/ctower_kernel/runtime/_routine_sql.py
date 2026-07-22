"""Transactional PostgreSQL Routine scan and fixed-operation job persistence."""

from __future__ import annotations

import secrets
from datetime import datetime, time
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    FixedOperationJob,
    OccurrenceOutcome,
    OccurrencePlan,
    RoutineOccurrence,
    RoutineRevision,
    ScheduleKind,
    SchedulerScan,
)

__all__: tuple[str, ...] = ()
_MAX_DUE_PER_SCAN = 400


def register(
    dsn: str,
    tenant_id: UUID,
    revision: RoutineRevision,
    *,
    first_fire_at: datetime | None,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        initial_fire = first_fire_at or revision.next_fire_after(_database_now(connection))
        connection.execute(
            """
            INSERT INTO routine_revisions (
                revision_digest, routine_ref, schedule_kind, timezone, local_time,
                dst_policy, concurrency, catch_up, catch_up_cap, timeout_seconds,
                handler_kind, component_digests, registered_at
            ) VALUES (%s, %s, %s, %s, %s, 'wall_clock_once', %s, %s, %s, %s, %s, %s,
                transaction_timestamp())
            ON CONFLICT (revision_digest) DO NOTHING
            """,
            (
                _digest(revision.revision_digest),
                revision.routine_ref,
                revision.schedule_kind.value,
                revision.timezone,
                revision.local_time,
                revision.concurrency.value,
                revision.catch_up.value,
                revision.catch_up_cap,
                revision.timeout_seconds,
                revision.handler_kind,
                [_digest(item) for item in revision.component_digests],
            ),
        )
        stored = connection.execute(
            "SELECT * FROM routine_revisions WHERE revision_digest = %s",
            (_digest(revision.revision_digest),),
        ).fetchone()
        if stored is None or _revision(stored) != revision:
            raise ValueError("Routine revision digest conflicts with stored content")
        connection.execute(
            """
            INSERT INTO routine_triggers (
                tenant_id, revision_digest, next_fire_at, updated_at
            ) VALUES (%s, %s, %s, transaction_timestamp())
            ON CONFLICT (tenant_id, revision_digest) DO NOTHING
            """,
            (tenant_id, _digest(revision.revision_digest), initial_fire),
        )


def tenant_ids(dsn: str) -> tuple[UUID, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute("SELECT tenant_id FROM tenants ORDER BY tenant_id").fetchall()
    return tuple(cast(UUID, row["tenant_id"]) for row in rows)


def scan(dsn: str, tenant_id: UUID) -> SchedulerScan:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        rows = connection.execute(
            """
            SELECT trigger.next_fire_at, revision.*
            FROM routine_triggers AS trigger
            JOIN routine_revisions AS revision
              ON revision.revision_digest = trigger.revision_digest
            WHERE trigger.tenant_id = %s AND trigger.next_fire_at <= %s
            ORDER BY trigger.next_fire_at, revision.revision_digest
            FOR UPDATE OF trigger
            """,
            (tenant_id, now),
        ).fetchall()
        occurrences: list[RoutineOccurrence] = []
        jobs: list[FixedOperationJob] = []
        for row in rows:
            revision = _revision(row)
            plans, next_fire = _plans(connection, tenant_id, revision, row, now)
            for plan in plans:
                occurrence, job = _persist_plan(connection, tenant_id, revision, plan, now)
                if occurrence is not None:
                    occurrences.append(occurrence)
                if job is not None:
                    jobs.append(job)
            connection.execute(
                """
                UPDATE routine_triggers SET next_fire_at = %s, updated_at = %s
                WHERE tenant_id = %s AND revision_digest = %s
                """,
                (next_fire, now, tenant_id, _digest(revision.revision_digest)),
            )
        watermark = _scheduler_watermark(connection, tenant_id, now)
    return SchedulerScan(tenant_id, watermark, now, tuple(occurrences), tuple(jobs))


def _plans(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision: RoutineRevision,
    row: dict[str, object],
    now: datetime,
) -> tuple[tuple[OccurrencePlan, ...], datetime]:
    due: list[datetime] = []
    candidate = cast(datetime, row["next_fire_at"])
    while candidate <= now:
        due.append(candidate)
        if len(due) > _MAX_DUE_PER_SCAN:
            raise RuntimeError("Routine due prefix exceeds the bounded scan limit")
        candidate = revision.next_fire_after(candidate)
    pending = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT count(*) AS value FROM operation_jobs
            WHERE tenant_id = %s AND operation = %s AND state = 'pending'
            """,
            (tenant_id, revision.handler_kind),
        ).fetchone(),
    )
    pending_count = int(cast(int, pending["value"]))
    return revision.plan_due(tuple(due), pending_jobs=pending_count), candidate


def _persist_plan(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> tuple[RoutineOccurrence | None, FixedOperationJob | None]:
    occurrence_id = _uuid7(now)
    inserted = connection.execute(
        """
        INSERT INTO routine_occurrences (
            occurrence_id, tenant_id, revision_digest, scheduled_for,
            local_civil_time, timezone, utc_offset_seconds, outcome, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, revision_digest, scheduled_for) DO NOTHING
        RETURNING occurrence_id
        """,
        (
            occurrence_id,
            tenant_id,
            _digest(revision.revision_digest),
            plan.scheduled_for,
            plan.local_civil_time,
            revision.timezone,
            plan.utc_offset_seconds,
            plan.outcome.value,
            now,
        ),
    ).fetchone()
    if inserted is None:
        return None, None
    job = None
    if plan.outcome is OccurrenceOutcome.QUEUED:
        job = _insert_job(connection, tenant_id, occurrence_id, revision, now)
    occurrence = RoutineOccurrence(
        occurrence_id,
        tenant_id,
        revision.routine_ref,
        revision.revision_digest,
        plan.scheduled_for,
        plan.local_civil_time,
        revision.timezone,
        plan.utc_offset_seconds,
        plan.outcome,
        job.job_id if job else None,
    )
    return occurrence, job


def _insert_job(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    occurrence_id: UUID,
    revision: RoutineRevision,
    now: datetime,
) -> FixedOperationJob:
    job_id = _uuid7(now)
    connection.execute(
        """
        INSERT INTO operation_jobs (
            job_id, tenant_id, occurrence_id, operation, state,
            timeout_seconds, component_digests, created_at
        ) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)
        """,
        (
            job_id,
            tenant_id,
            occurrence_id,
            revision.handler_kind,
            revision.timeout_seconds,
            [_digest(item) for item in revision.component_digests],
            now,
        ),
    )
    return FixedOperationJob(
        job_id,
        tenant_id,
        occurrence_id,
        revision.handler_kind,
        revision.timeout_seconds,
        revision.component_digests,
        now,
    )


def _scheduler_watermark(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, now: datetime
) -> int:
    row = cast(
        dict[str, object],
        connection.execute(
            """
            INSERT INTO scheduler_watermarks (
                tenant_id, scan_watermark, status, reason, observed_at
            ) VALUES (%s, 1, 'HEALTHY', 'scan-complete', %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                scan_watermark = scheduler_watermarks.scan_watermark + 1,
                status = 'HEALTHY', reason = 'scan-complete', observed_at = EXCLUDED.observed_at
            RETURNING scan_watermark
            """,
            (tenant_id, now),
        ).fetchone(),
    )
    watermark = int(cast(int, row["scan_watermark"]))
    connection.execute(
        """
        INSERT INTO health_watermarks (
            tenant_id, contributor, status, watermark, threshold_seconds,
            observed_at, owner, reason
        ) VALUES (%s, 'scheduler', 'HEALTHY', %s, 60, %s, 'runtime', 'scan-complete')
        ON CONFLICT (tenant_id, contributor) DO UPDATE SET
            status = EXCLUDED.status, watermark = EXCLUDED.watermark,
            threshold_seconds = EXCLUDED.threshold_seconds,
            observed_at = EXCLUDED.observed_at, owner = EXCLUDED.owner,
            reason = EXCLUDED.reason
        """,
        (tenant_id, watermark, now),
    )
    return watermark


def _revision(row: dict[str, object]) -> RoutineRevision:
    local_time = row["local_time"]
    if local_time is not None and not isinstance(local_time, time):
        raise TypeError("stored Routine local time is invalid")
    return RoutineRevision(
        routine_ref=str(row["routine_ref"]),
        revision_digest="sha256:" + bytes(cast(bytes, row["revision_digest"])).hex(),
        schedule_kind=ScheduleKind(str(row["schedule_kind"])),
        timezone=str(row["timezone"]),
        local_time=local_time,
        concurrency=ConcurrencyPolicy(str(row["concurrency"])),
        catch_up=CatchUpPolicy(str(row["catch_up"])),
        catch_up_cap=int(cast(int, row["catch_up_cap"])),
        handler_kind=str(row["handler_kind"]),
        timeout_seconds=int(cast(int, row["timeout_seconds"])),
        component_digests=tuple(
            "sha256:" + bytes(cast(bytes, item)).hex()
            for item in cast(list[object], row["component_digests"])
        ),
    )


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = cast(
        dict[str, object],
        connection.execute("SELECT transaction_timestamp() AS value").fetchone(),
    )
    return cast(datetime, row["value"])


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
