"""Transactional PostgreSQL Routine scan and fixed-operation job persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    RoutineOccurrenceRecordedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.runtime import (
    DreamDispatchEffect,
    FixedOperationJob,
    OccurrenceOutcome,
    OccurrencePlan,
    RoutineOccurrence,
    RoutineRevision,
    SchedulerScan,
    _gate_sql,
    _routine_rows,
)
from ctower_kernel.runtime._retirement_guard import lock_routine_tenant, routine_is_retired
from ctower_kernel.runtime._routine_ids import stable_uuid7 as _stable_uuid7
from ctower_kernel.runtime._routine_work_items_sql import (
    _append_expired_work_item_alarms,
    _append_work_item,
    _append_work_item_suppression,
    _open_work_item,
    _register_dream_spec,
    _register_routine_item_spec,
)
from ctower_kernel.runtime.items import (
    RoutineWorkItem,
    RoutineWorkItemAlarm,
    RoutineWorkItemSuppression,
)

__all__: tuple[str, ...] = ()
_MAX_DUE_PER_SCAN = 400
_CONTROL_WORKER_ID_DOMAIN = b"ctower.control-worker-principal/v1"
_CONTROL_WORKER_DISPLAY_NAME = "ctower:internal:control-worker:" + "-" * 90


def register(
    dsn: str,
    tenant_id: UUID,
    revision: RoutineRevision,
    *,
    first_fire_at: datetime | None,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        _control_worker_principal(connection, tenant_id, now)
        lock_routine_tenant(connection, tenant_id)
        if routine_is_retired(connection, tenant_id, revision.routine_ref):
            return
        initial_fire = first_fire_at or revision.next_fire_after(now)
        connection.execute(
            """
            INSERT INTO routine_revisions (
                revision_digest, routine_ref, schedule_kind, timezone, local_time,
                schedule_minutes, schedule_hours,
                dst_policy, concurrency, catch_up, catch_up_cap, timeout_seconds,
                handler_kind, component_digests, registered_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'wall_clock_once', %s, %s, %s, %s, %s, %s,
                transaction_timestamp())
            ON CONFLICT (revision_digest) DO NOTHING
            """,
            (
                _digest(revision.revision_digest),
                revision.routine_ref,
                revision.schedule_kind.value,
                revision.timezone,
                revision.local_time,
                list(revision.minute_marks) or None,
                list(revision.hour_marks) if revision.hour_marks is not None else None,
                revision.concurrency.value,
                revision.catch_up.value,
                revision.catch_up_cap,
                revision.timeout_seconds,
                revision.handler_kind,
                [_digest(item) for item in revision.component_digests],
            ),
        )
        _register_dream_spec(connection, revision)
        _register_routine_item_spec(connection, revision)
        _gate_sql.register_gate(connection, revision)
        stored = connection.execute(
            """
            SELECT revision.*, dream.scope_kind, dream.project_key, dream.skill_path,
                dream.primary_model_ref, dream.primary_reasoning_effort,
                dream.fallback_model_ref, dream.fallback_reasoning_effort,
                dream.minimum_model_tier, dream.excluded_model_families,
                item.item_key, item.knowledge_ref, item.document_id, item.owner_seat,
                item.escalation_seat,
                gate.gate_kind, gate.gate_source, gate.gate_threshold, gate.gate_project_key
            FROM routine_revisions AS revision
            LEFT JOIN routine_dream_dispatch_specs AS dream
              ON dream.revision_digest = revision.revision_digest
            LEFT JOIN routine_item_specs AS item
              ON item.revision_digest = revision.revision_digest
            LEFT JOIN routine_activity_gates AS gate
              ON gate.revision_digest = revision.revision_digest
            WHERE revision.revision_digest = %s
            """,
            (_digest(revision.revision_digest),),
        ).fetchone()
        if stored is None or _routine_rows.revision(cast(dict[str, object], stored)) != revision:
            raise ValueError("Routine revision digest conflicts with stored content")
        connection.execute(
            """
            DELETE FROM routine_triggers AS trigger
            USING routine_revisions AS registered
            WHERE trigger.tenant_id = %s
              AND trigger.revision_digest = registered.revision_digest
              AND registered.routine_ref = %s
              AND registered.revision_digest <> %s
            """,
            (tenant_id, revision.routine_ref, _digest(revision.revision_digest)),
        )
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
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        actor_principal_id = _control_worker_principal(connection, tenant_id, now)
        lock_routine_tenant(connection, tenant_id)
        rows = connection.execute(
            """
            SELECT trigger.next_fire_at, revision.*, dream.scope_kind, dream.project_key,
                dream.skill_path, dream.primary_model_ref, dream.primary_reasoning_effort,
                dream.fallback_model_ref, dream.fallback_reasoning_effort,
                dream.minimum_model_tier, dream.excluded_model_families,
                item.item_key, item.knowledge_ref, item.document_id, item.owner_seat,
                item.escalation_seat,
                gate.gate_kind, gate.gate_source, gate.gate_threshold, gate.gate_project_key
            FROM routine_triggers AS trigger
            JOIN routine_revisions AS revision
              ON revision.revision_digest = trigger.revision_digest
            LEFT JOIN routine_dream_dispatch_specs AS dream
              ON dream.revision_digest = revision.revision_digest
            LEFT JOIN routine_item_specs AS item
              ON item.revision_digest = revision.revision_digest
            LEFT JOIN routine_activity_gates AS gate
              ON gate.revision_digest = revision.revision_digest
            WHERE trigger.tenant_id = %s AND trigger.next_fire_at <= %s
            ORDER BY trigger.next_fire_at, revision.revision_digest
            FOR UPDATE OF trigger
            """,
            (tenant_id, now),
        ).fetchall()
        occurrences: list[RoutineOccurrence] = []
        jobs: list[FixedOperationJob] = []
        dream_dispatches: list[DreamDispatchEffect] = []
        work_items: list[RoutineWorkItem] = []
        suppressions: list[RoutineWorkItemSuppression] = []
        alarms: list[RoutineWorkItemAlarm] = []
        work_item_blockers: dict[str, UUID] = {}
        for row in rows:
            revision = _routine_rows.revision(row)
            plans, next_fire = _plans(connection, tenant_id, revision, row, now)
            plans = _gate_sql.apply_gate_decisions(connection, tenant_id, revision, plans, now)
            for planned in plans:
                _record_scan_plan(
                    connection,
                    tenant_id,
                    actor_principal_id,
                    revision,
                    planned,
                    now,
                    work_item_blockers,
                    occurrences,
                    jobs,
                    dream_dispatches,
                    work_items,
                    suppressions,
                )
            connection.execute(
                """
                UPDATE routine_triggers SET next_fire_at = %s, updated_at = %s
                WHERE tenant_id = %s AND revision_digest = %s
                """,
                (next_fire, now, tenant_id, _digest(revision.revision_digest)),
            )
        alarms.extend(
            _append_expired_work_item_alarms(connection, tenant_id, actor_principal_id, now)
        )
        watermark = _scheduler_watermark(connection, tenant_id, now)
    return SchedulerScan(
        tenant_id=tenant_id,
        scan_watermark=watermark,
        observed_at=now,
        occurrences=tuple(occurrences),
        jobs=tuple(jobs),
        dream_dispatches=tuple(dream_dispatches),
        work_items=tuple(work_items),
        work_item_suppressions=tuple(suppressions),
        work_item_alarms=tuple(alarms),
    )


def _record_scan_plan(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    revision: RoutineRevision,
    planned: OccurrencePlan,
    now: datetime,
    blockers: dict[str, UUID],
    occurrences: list[RoutineOccurrence],
    jobs: list[FixedOperationJob],
    dream_dispatches: list[DreamDispatchEffect],
    work_items: list[RoutineWorkItem],
    suppressions: list[RoutineWorkItemSuppression],
) -> None:
    plan = _apply_work_item_blocker(connection, tenant_id, revision, planned, blockers)
    occurrence, job, dream_dispatch, work_item, suppression = _persist_plan(
        connection,
        tenant_id,
        actor_principal_id,
        revision,
        plan,
        now,
    )
    if occurrence is not None:
        occurrences.append(occurrence)
    if job is not None:
        jobs.append(job)
    if dream_dispatch is not None:
        dream_dispatches.append(dream_dispatch)
    if work_item is not None:
        work_items.append(work_item)
        blockers[revision.routine_ref] = work_item.work_item_id
    if suppression is not None:
        suppressions.append(suppression)


def _apply_work_item_blocker(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    blockers: dict[str, UUID],
) -> OccurrencePlan:
    if revision.routine_item is None or plan.outcome is not OccurrenceOutcome.QUEUED:
        return plan
    if (
        revision.activity_gate is not None
        and revision.activity_gate.kind == "new_movement_since_watermark"
    ):
        return plan
    blocker = blockers.get(revision.routine_ref)
    if blocker is None:
        blocker = _open_work_item(connection, tenant_id, revision.routine_ref)
    if blocker is None:
        return plan
    blockers[revision.routine_ref] = blocker
    return replace(plan, outcome=OccurrenceOutcome.SKIPPED)


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
            SELECT count(*) AS value FROM operation_jobs AS job
            WHERE job.tenant_id = %s AND job.operation = %s AND job.state = 'pending'
              AND NOT EXISTS (
                  SELECT 1 FROM fixed_operation_results AS result
                  WHERE result.job_id = job.job_id
              )
            """,
            (tenant_id, revision.handler_kind),
        ).fetchone(),
    )
    pending_count = int(cast(int, pending["value"]))
    return revision.plan_due(tuple(due), pending_jobs=pending_count), candidate


def _persist_plan(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> tuple[
    RoutineOccurrence | None,
    FixedOperationJob | None,
    DreamDispatchEffect | None,
    RoutineWorkItem | None,
    RoutineWorkItemSuppression | None,
]:
    occurrence_id, command_id, event_id, outbox_id, job_id = _occurrence_ids(
        tenant_id, revision, plan
    )
    request_payload = _occurrence_payload(tenant_id, occurrence_id, revision, plan, job_id)
    request_digest = hashlib.sha256(_canonical_bytes(request_payload)).digest()
    transaction = RecordTransaction(connection)
    existing = transaction.reserve(actor_principal_id, command_id, request_digest)
    if existing is not None:
        return None, None, None, None, None
    event = _occurrence_event(
        tenant_id,
        actor_principal_id,
        occurrence_id,
        command_id,
        event_id,
        revision,
        plan,
        job_id,
        request_digest,
        now,
    )
    _commit_occurrence(transaction, event, outbox_id, request_payload, job_id, now)
    _insert_occurrence(
        connection, tenant_id, actor_principal_id, occurrence_id, command_id, revision, plan, now
    )
    job = None
    if job_id is not None:
        job = _insert_job(connection, tenant_id, occurrence_id, job_id, revision, now)
    dream_dispatch = _insert_dream_dispatch(
        connection, tenant_id, occurrence_id, revision, plan, now
    )
    work_item = _append_work_item(connection, tenant_id, actor_principal_id, revision, plan, now)
    suppression = _append_work_item_suppression(
        connection, tenant_id, actor_principal_id, revision, plan, now
    )
    occurrence = _routine_occurrence(tenant_id, occurrence_id, revision, plan, job_id)
    return occurrence, job, dream_dispatch, work_item, suppression


def _insert_dream_dispatch(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    occurrence_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> DreamDispatchEffect | None:
    spec = revision.dream_dispatch
    if spec is None or plan.outcome is not OccurrenceOutcome.QUEUED:
        return None
    effect_id = _stable_uuid7(
        plan.scheduled_for,
        b"dream-dispatch",
        tenant_id.bytes,
        _digest(revision.revision_digest),
        plan.scheduled_for.isoformat().encode("ascii"),
    )
    connection.execute(
        """
        INSERT INTO runtime_dream_dispatch_effects (
            effect_id, occurrence_id, tenant_id, revision_digest, routine_ref,
            scheduled_for, scope_kind, project_key, skill_path,
            primary_model_ref, primary_reasoning_effort,
            fallback_model_ref, fallback_reasoning_effort,
            minimum_model_tier, excluded_model_families, emitted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            effect_id,
            occurrence_id,
            tenant_id,
            _digest(revision.revision_digest),
            revision.routine_ref,
            plan.scheduled_for,
            spec.scope_kind,
            spec.project_key,
            spec.skill_path,
            spec.primary_model_ref,
            spec.primary_reasoning_effort,
            spec.fallback_model_ref,
            spec.fallback_reasoning_effort,
            spec.minimum_model_tier,
            list(spec.excluded_model_families),
            now,
        ),
    )
    return DreamDispatchEffect(
        effect_id,
        occurrence_id,
        tenant_id,
        revision.routine_ref,
        revision.revision_digest,
        plan.scheduled_for,
        spec,
        now,
    )


def _occurrence_ids(
    tenant_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
) -> tuple[UUID, UUID, UUID, UUID, UUID | None]:
    identity = (
        tenant_id.bytes,
        _digest(revision.revision_digest),
        plan.scheduled_for.isoformat().encode("ascii"),
    )
    job_id = (
        _stable_uuid7(plan.scheduled_for, b"job", *identity)
        if plan.outcome is OccurrenceOutcome.QUEUED and revision.handler_kind != "routine_item"
        else None
    )
    return (
        _stable_uuid7(plan.scheduled_for, b"occurrence", *identity),
        _stable_uuid7(plan.scheduled_for, b"command", *identity),
        _stable_uuid7(plan.scheduled_for, b"event", *identity),
        _stable_uuid7(plan.scheduled_for, b"outbox", *identity),
        job_id,
    )


def _occurrence_event(
    tenant_id: UUID,
    actor_principal_id: UUID,
    occurrence_id: UUID,
    command_id: UUID,
    event_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    job_id: UUID | None,
    request_digest: bytes,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor_principal_id,
        aggregate_id=occurrence_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_OCCURRENCE_RECORDED,
        origin=EventOrigin.CONTROL_WORKER,
        payload=RoutineOccurrenceRecordedPayload(
            occurrence_id=occurrence_id,
            routine_ref=revision.routine_ref,
            revision_digest=revision.revision_digest,
            scheduled_for=plan.scheduled_for,
            local_civil_time=plan.local_civil_time,
            timezone=revision.timezone,
            utc_offset_seconds=plan.utc_offset_seconds,
            offset_decision=plan.offset_decision.value,
            outcome=plan.outcome.value,
            job_id=job_id,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"routine-occurrence:{occurrence_id}",
        tenant_id=tenant_id,
    )


def _commit_occurrence(
    transaction: RecordTransaction,
    event: EventEnvelope,
    outbox_id: UUID,
    request_payload: dict[str, object],
    job_id: UUID | None,
    now: datetime,
) -> None:
    transaction.commit_control(
        event,
        outbox_id=outbox_id,
        response_body={
            "command_id": str(event.client_command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(event.event_id)],
            "occurrence": request_payload,
        },
        status_code=202,
        now=now,
        topic="runtime.occurrences",
        job_id=job_id,
    )


def _insert_occurrence(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    occurrence_id: UUID,
    command_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO routine_occurrences (
            occurrence_id, tenant_id, actor_principal_id, client_command_id,
            revision_digest, scheduled_for, local_civil_time, timezone,
            utc_offset_seconds, offset_decision, outcome, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            occurrence_id,
            tenant_id,
            actor_principal_id,
            command_id,
            _digest(revision.revision_digest),
            plan.scheduled_for,
            plan.local_civil_time,
            revision.timezone,
            plan.utc_offset_seconds,
            plan.offset_decision.value,
            plan.outcome.value,
            now,
        ),
    )


def _routine_occurrence(
    tenant_id: UUID,
    occurrence_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    job_id: UUID | None,
) -> RoutineOccurrence:
    return RoutineOccurrence(
        occurrence_id=occurrence_id,
        tenant_id=tenant_id,
        routine_ref=revision.routine_ref,
        revision_digest=revision.revision_digest,
        scheduled_for=plan.scheduled_for,
        local_civil_time=plan.local_civil_time,
        timezone=revision.timezone,
        utc_offset_seconds=plan.utc_offset_seconds,
        offset_decision=plan.offset_decision,
        outcome=plan.outcome,
        job_id=job_id,
    )


def _insert_job(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    occurrence_id: UUID,
    job_id: UUID,
    revision: RoutineRevision,
    now: datetime,
) -> FixedOperationJob:
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


def _occurrence_payload(
    tenant_id: UUID,
    occurrence_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    job_id: UUID | None,
) -> dict[str, object]:
    return {
        "job_id": str(job_id) if job_id is not None else None,
        "local_civil_time": plan.local_civil_time,
        "occurrence_id": str(occurrence_id),
        "offset_decision": plan.offset_decision.value,
        "outcome": plan.outcome.value,
        "revision_digest": revision.revision_digest,
        "routine_ref": revision.routine_ref,
        "scheduled_for": plan.scheduled_for.isoformat(),
        "schema_id": "ctower.routine-occurrence/v1",
        "tenant_id": str(tenant_id),
        "timezone": revision.timezone,
        "utc_offset_seconds": plan.utc_offset_seconds,
    }


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _control_worker_principal(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    now: datetime,
) -> UUID:
    principal_id = _control_worker_principal_id(tenant_id)
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled,
            credential_ref, vault_ref, created_at
        ) VALUES (%s, %s, 'control_worker', %s, false, NULL, NULL, %s)
        ON CONFLICT DO NOTHING
        """,
        (principal_id, tenant_id, _CONTROL_WORKER_DISPLAY_NAME, now),
    )
    row = connection.execute(
        """
        SELECT principal_id, tenant_id, kind, display_name, disabled,
            credential_ref, vault_ref,
            NOT EXISTS (
                SELECT 1 FROM principal_credentials AS credential
                WHERE credential.principal_id = principal.principal_id
                  AND credential.tenant_id = principal.tenant_id
                  AND credential.revoked_at IS NULL
            ) AS credential_free
        FROM principals AS principal
        WHERE principal_id = %s
        """,
        (principal_id,),
    ).fetchone()
    expected = (
        principal_id,
        tenant_id,
        "control_worker",
        _CONTROL_WORKER_DISPLAY_NAME,
        False,
        None,
        None,
        True,
    )
    fields = (
        "principal_id",
        "tenant_id",
        "kind",
        "display_name",
        "disabled",
        "credential_ref",
        "vault_ref",
        "credential_free",
    )
    if row is None or tuple(row[field] for field in fields) != expected:
        raise RuntimeError("Routine control-worker principal is unavailable")
    return principal_id


def _control_worker_principal_id(tenant_id: UUID) -> UUID:
    digest = bytearray(
        hashlib.sha256(_CONTROL_WORKER_ID_DOMAIN + b"\x00" + tenant_id.bytes).digest()[:16]
    )
    digest[6] = (digest[6] & 0x0F) | 0x80
    digest[8] = (digest[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(digest))


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


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = cast(
        dict[str, object],
        connection.execute("SELECT transaction_timestamp() AS value").fetchone(),
    )
    return cast(datetime, row["value"])


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))
