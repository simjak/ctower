"""PostgreSQL persistence for record-backed Routine work-item facts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
)
from ctower_kernel.record.routine_work_item_events import (
    RoutineWorkItemAppendedPayload,
    RoutineWorkItemSuppressedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.runtime._routine_ids import stable_uuid7 as _stable_uuid7
from ctower_kernel.runtime.interface import OccurrenceOutcome, OccurrencePlan, RoutineRevision
from ctower_kernel.runtime.items import (
    RoutineGateEvidence,
    RoutineWorkItem,
    RoutineWorkItemSuppression,
)

__all__: tuple[str, ...] = ()


def _open_work_item(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, routine_ref: str
) -> UUID | None:
    row = connection.execute(
        """
        SELECT work_item_id FROM inbox_work_items
        WHERE tenant_id = %s AND routine_ref = %s AND status = 'open'
        ORDER BY scheduled_for, work_item_id
        LIMIT 1
        """,
        (tenant_id, routine_ref),
    ).fetchone()
    return cast(UUID, row["work_item_id"]) if row is not None else None


def _append_work_item(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> RoutineWorkItem | None:
    spec = revision.routine_item
    if spec is None or plan.outcome is not OccurrenceOutcome.QUEUED:
        return None
    work_item_id = _work_item_id(tenant_id, revision.revision_digest, plan.scheduled_for)
    gate_evidence = _gate_evidence(connection, tenant_id, revision, plan.scheduled_for)
    window_ends_at = plan.scheduled_for + timedelta(seconds=revision.timeout_seconds)
    item = RoutineWorkItem(
        work_item_id=work_item_id,
        tenant_id=tenant_id,
        routine_ref=revision.routine_ref,
        revision_digest=revision.revision_digest,
        scheduled_for=plan.scheduled_for,
        window_ends_at=window_ends_at,
        owner_seat=spec.owner_seat,
        escalation_seat=spec.escalation_seat,
        knowledge_ref=spec.knowledge_ref,
        document_id=spec.document_id,
        gate_evidence=gate_evidence,
        created_at=now,
    )
    command_id, event_id, outbox_id = _work_item_ids(plan.scheduled_for, tenant_id, work_item_id)
    request_payload = item.response_payload()
    request_digest = hashlib.sha256(_canonical_bytes(request_payload)).digest()
    transaction = RecordTransaction(connection)
    if transaction.reserve(actor_principal_id, command_id, request_digest) is not None:
        return None
    event = _work_item_event(
        tenant_id, actor_principal_id, item, command_id, event_id, request_digest, now
    )
    _commit_work_item_fact(
        transaction, event, outbox_id, request_payload, now, "runtime.routine-work-items"
    )
    _insert_work_item(connection, item, event_id, now)
    return item


def _work_item_id(tenant_id: UUID, revision_digest: str, scheduled_for: datetime) -> UUID:
    return _stable_uuid7(
        scheduled_for,
        b"routine-work-item",
        tenant_id.bytes,
        _digest(revision_digest),
        scheduled_for.isoformat().encode("ascii"),
    )


def _work_item_ids(
    scheduled_for: datetime, tenant_id: UUID, work_item_id: UUID
) -> tuple[UUID, UUID, UUID]:
    return (
        _stable_uuid7(
            scheduled_for,
            b"routine-work-item-command",
            tenant_id.bytes,
            work_item_id.bytes,
        ),
        _stable_uuid7(
            scheduled_for,
            b"routine-work-item-event",
            tenant_id.bytes,
            work_item_id.bytes,
        ),
        _stable_uuid7(
            scheduled_for,
            b"routine-work-item-outbox",
            tenant_id.bytes,
            work_item_id.bytes,
        ),
    )


def _work_item_event(
    tenant_id: UUID,
    actor_principal_id: UUID,
    item: RoutineWorkItem,
    command_id: UUID,
    event_id: UUID,
    request_digest: bytes,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor_principal_id,
        aggregate_id=item.work_item_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_WORK_ITEM_APPENDED,
        origin=EventOrigin.CONTROL_WORKER,
        payload=RoutineWorkItemAppendedPayload(
            work_item_id=item.work_item_id,
            routine_ref=item.routine_ref,
            revision_digest=item.revision_digest,
            scheduled_for=item.scheduled_for,
            window_ends_at=item.window_ends_at,
            owner_seat=item.owner_seat,
            escalation_seat=item.escalation_seat,
            knowledge_ref=item.knowledge_ref,
            document_id=item.document_id,
            gate_evidence=item.gate_evidence.response_payload(),
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"routine-work-item:{item.work_item_id}",
        tenant_id=tenant_id,
    )


def _commit_work_item_fact(
    transaction: RecordTransaction,
    event: EventEnvelope,
    outbox_id: UUID,
    response_body: dict[str, object],
    now: datetime,
    topic: str,
) -> None:
    transaction.commit_control(
        event,
        outbox_id=outbox_id,
        response_body=response_body,
        status_code=202,
        now=now,
        topic=topic,
    )


def _insert_work_item(
    connection: psycopg.Connection[dict[str, object]],
    item: RoutineWorkItem,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO inbox_work_items (
            work_item_id, tenant_id, routine_ref, revision_digest, scheduled_for,
            window_ends_at, owner_seat, escalation_seat, knowledge_ref, document_id,
            gate_evidence,
            created_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            item.work_item_id,
            item.tenant_id,
            item.routine_ref,
            _digest(item.revision_digest),
            item.scheduled_for,
            item.window_ends_at,
            item.owner_seat,
            item.escalation_seat,
            item.knowledge_ref,
            item.document_id,
            Jsonb(item.gate_evidence.response_payload()),
            now,
            event_id,
        ),
    )


def _append_work_item_suppression(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> RoutineWorkItemSuppression | None:
    if revision.routine_item is None or plan.outcome is not OccurrenceOutcome.SKIPPED:
        return None
    blocker = _open_work_item(connection, tenant_id, revision.routine_ref)
    if blocker is None:
        return None
    suppression_id, command_id, event_id, outbox_id = _suppression_ids(
        tenant_id, revision.revision_digest, plan.scheduled_for
    )
    suppression = RoutineWorkItemSuppression(
        suppression_id=suppression_id,
        routine_ref=revision.routine_ref,
        scheduled_for=plan.scheduled_for,
        blocking_item_id=blocker,
        recorded_at=now,
    )
    request_payload = suppression.response_payload()
    request_digest = hashlib.sha256(_canonical_bytes(request_payload)).digest()
    transaction = RecordTransaction(connection)
    if transaction.reserve(actor_principal_id, command_id, request_digest) is not None:
        return None
    event = _suppression_event(
        tenant_id,
        actor_principal_id,
        suppression,
        command_id,
        event_id,
        request_digest,
        now,
    )
    _commit_work_item_fact(
        transaction,
        event,
        outbox_id,
        request_payload,
        now,
        "runtime.routine-work-item-suppressions",
    )
    _insert_suppression(connection, suppression, tenant_id, event_id)
    return suppression


def _suppression_ids(
    tenant_id: UUID, revision_digest: str, scheduled_for: datetime
) -> tuple[UUID, UUID, UUID, UUID]:
    suppression_id = _stable_uuid7(
        scheduled_for,
        b"routine-work-item-suppression",
        tenant_id.bytes,
        _digest(revision_digest),
        scheduled_for.isoformat().encode("ascii"),
    )
    return (
        suppression_id,
        _stable_uuid7(
            scheduled_for,
            b"routine-work-item-suppression-command",
            tenant_id.bytes,
            suppression_id.bytes,
        ),
        _stable_uuid7(
            scheduled_for,
            b"routine-work-item-suppression-event",
            tenant_id.bytes,
            suppression_id.bytes,
        ),
        _stable_uuid7(
            scheduled_for,
            b"routine-work-item-suppression-outbox",
            tenant_id.bytes,
            suppression_id.bytes,
        ),
    )


def _suppression_event(
    tenant_id: UUID,
    actor_principal_id: UUID,
    suppression: RoutineWorkItemSuppression,
    command_id: UUID,
    event_id: UUID,
    request_digest: bytes,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor_principal_id,
        aggregate_id=suppression.suppression_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_WORK_ITEM_SUPPRESSED,
        origin=EventOrigin.CONTROL_WORKER,
        payload=RoutineWorkItemSuppressedPayload(
            suppression_id=suppression.suppression_id,
            routine_ref=suppression.routine_ref,
            scheduled_for=suppression.scheduled_for,
            blocking_item_id=suppression.blocking_item_id,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"routine-work-item:{suppression.suppression_id}",
        tenant_id=tenant_id,
    )


def _insert_suppression(
    connection: psycopg.Connection[dict[str, object]],
    suppression: RoutineWorkItemSuppression,
    tenant_id: UUID,
    event_id: UUID,
) -> None:
    connection.execute(
        """
        INSERT INTO routine_work_item_suppressions (
            suppression_id, tenant_id, routine_ref, scheduled_for,
            blocking_item_id, recorded_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            suppression.suppression_id,
            tenant_id,
            suppression.routine_ref,
            suppression.scheduled_for,
            suppression.blocking_item_id,
            suppression.recorded_at,
            event_id,
        ),
    )


def _gate_evidence(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision: RoutineRevision,
    scheduled_for: datetime,
) -> RoutineGateEvidence:
    row = connection.execute(
        """
        SELECT gate_kind, result, watermark_kind, watermark_position,
            observed_count, detail
        FROM routine_gate_evaluations
        WHERE tenant_id = %s AND revision_digest = %s AND scheduled_for = %s
        """,
        (tenant_id, _digest(revision.revision_digest), scheduled_for),
    ).fetchone()
    if row is None:
        return RoutineGateEvidence("always", "none", None, 0, "ungated routine")
    return RoutineGateEvidence(
        kind=str(row["gate_kind"]),
        watermark_kind=str(row["watermark_kind"]),
        watermark_position=cast(datetime | None, row["watermark_position"]),
        observed_count=max(0, int(cast(int, row["observed_count"]))),
        detail=str(row["detail"]),
    )


def _register_dream_spec(
    connection: psycopg.Connection[dict[str, object]], revision: RoutineRevision
) -> None:
    spec = revision.dream_dispatch
    if spec is None:
        return
    connection.execute(
        """
        INSERT INTO routine_dream_dispatch_specs (
            revision_digest, scope_kind, project_key, skill_path,
            primary_model_ref, primary_reasoning_effort,
            fallback_model_ref, fallback_reasoning_effort,
            minimum_model_tier, excluded_model_families
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (revision_digest) DO NOTHING
        """,
        (
            _digest(revision.revision_digest),
            spec.scope_kind,
            spec.project_key,
            spec.skill_path,
            spec.primary_model_ref,
            spec.primary_reasoning_effort,
            spec.fallback_model_ref,
            spec.fallback_reasoning_effort,
            spec.minimum_model_tier,
            list(spec.excluded_model_families),
        ),
    )


def _register_routine_item_spec(
    connection: psycopg.Connection[dict[str, object]], revision: RoutineRevision
) -> None:
    spec = revision.routine_item
    if spec is None:
        return
    connection.execute(
        """
        INSERT INTO routine_item_specs (
            revision_digest, item_key, knowledge_ref, document_id, owner_seat, escalation_seat
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (revision_digest) DO NOTHING
        """,
        (
            _digest(revision.revision_digest),
            spec.item_key,
            spec.knowledge_ref,
            spec.document_id,
            spec.owner_seat,
            spec.escalation_seat,
        ),
    )


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: str) -> bytes:
    if not value.startswith("sha256:"):
        raise ValueError("digest must be sha256-prefixed")
    return bytes.fromhex(value.removeprefix("sha256:"))
