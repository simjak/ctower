"""Canonical Record command persistence for the Attention findings feed."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.attention import (
    AppendFinding,
    AttentionFindingReceipt,
    FindingDisposition,
    FindingDispositionReceipt,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.attention_events import (
    AttentionFindingAppendedPayload,
    AttentionFindingDispositionRecordedPayload,
)
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.transaction import RecordTransaction, authority_connection

__all__: tuple[str, ...] = ()


def append_finding(
    dsn: str, actor: Actor, command: AppendFinding
) -> AttentionFindingReceipt | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        request_digest = hashlib.sha256(_canonical_bytes(command.request_payload())).digest()
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _finding_receipt_from_payload(actor, command, existing)
        problem = _finding_refusal(connection, transaction, actor, command, request_digest, now)
        if problem is not None:
            return problem
        active = _active_kind_revision(connection, actor, command.kind_key)
        if active is None:
            raise RuntimeError("active attention-kind revision disappeared after refusal check")
        if not _ticket_exists(connection, actor, command.subject_ticket_id):
            problem = RecordProblem(
                code="tenant-scope-denied",
                detail="The finding subject ticket is unavailable in this tenant.",
                status=404,
                title="Finding subject unavailable",
                command_id=command.client_command_id,
            )
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                request_digest,
                problem,
                now=now,
            )
            return problem
        return _record_finding(connection, transaction, actor, command, active, request_digest, now)


def _finding_refusal(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: AppendFinding,
    request_digest: bytes,
    now: datetime,
) -> RecordProblem | None:
    if _active_kind_revision(connection, actor, command.kind_key) is not None:
        return None
    problem = RecordProblem(
        code="attention-kind-unrecognized",
        detail="This kind is absent from the active attention-kind catalog revision.",
        status=422,
        title="Attention kind unrecognized",
        command_id=command.client_command_id,
    )
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _active_kind_revision(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, kind_key: str
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT revision.attention_kind_catalog_revision_id, revision.catalog_key,
            revision.catalog_revision, revision.catalog_digest
        FROM company_bundle_active AS active
        JOIN company_bundle_members AS member
          ON member.bundle_revision_id = active.bundle_revision_id
         AND member.tenant_id = active.tenant_id
        JOIN attention_kind_catalog_revisions AS revision
          ON revision.attention_kind_catalog_revision_id = member.component_revision_id
         AND revision.tenant_id = member.tenant_id
        JOIN attention_kind_catalog_members AS kmember
          ON kmember.attention_kind_catalog_revision_id
           = revision.attention_kind_catalog_revision_id
         AND kmember.tenant_id = revision.tenant_id
         AND kmember.kind_key = %s
        WHERE active.tenant_id = %s
        """,
        (kind_key, actor.tenant_id),
    ).fetchone()


def _ticket_exists(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
        (actor.tenant_id, ticket_id),
    ).fetchone()
    return row is not None


def _record_finding(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: AppendFinding,
    active: dict[str, object],
    request_digest: bytes,
    now: datetime,
) -> AttentionFindingReceipt:
    finding_id = _uuid7(now)
    catalog_digest = f"sha256:{bytes(cast(bytes, active['catalog_digest'])).hex()}"
    receipt = AttentionFindingReceipt(
        actor.tenant_id, actor.principal_id, command, finding_id, now, (finding_id,)
    )
    payload = _finding_payload(command, finding_id, active, catalog_digest)
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=finding_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=finding_id,
        kind=EventKind.ATTENTION_FINDING_APPENDED,
        origin=EventOrigin.API,
        payload=payload,
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"attention-finding:{finding_id}",
        tenant_id=actor.tenant_id,
    )
    transaction.commit_control(
        event,
        outbox_id=_uuid7(now),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="attention.findings",
    )
    _insert_finding(connection, actor, command, active, finding_id, now)
    return receipt


def _finding_payload(
    command: AppendFinding,
    finding_id: UUID,
    active: dict[str, object],
    catalog_digest: str,
) -> AttentionFindingAppendedPayload:
    return AttentionFindingAppendedPayload(
        finding_id=finding_id,
        subject_ticket_id=command.subject_ticket_id,
        kind_key=command.kind_key,
        catalog_key=str(active["catalog_key"]),
        catalog_revision=int(cast(int, active["catalog_revision"])),
        catalog_digest=catalog_digest,
        reason_code=command.reason_code,
        effective_owner=command.effective_owner,
        recommendation=command.recommendation,
        alternatives=command.alternatives,
        consequence=command.consequence,
        deadline=command.deadline,
        dedupe_key=command.dedupe_key,
        source_facts=command.source_facts,
    )


def _insert_finding(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: AppendFinding,
    active: dict[str, object],
    finding_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO attention_need_findings (
            finding_id, tenant_id, subject_ticket_id, attention_kind_catalog_revision_id,
            kind_key, reason_code, effective_owner, recommendation, alternatives,
            consequence, deadline, dedupe_key, source_facts, event_id, actor_principal_id,
            appended_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            finding_id,
            actor.tenant_id,
            command.subject_ticket_id,
            active["attention_kind_catalog_revision_id"],
            command.kind_key,
            command.reason_code,
            command.effective_owner,
            command.recommendation,
            list(command.alternatives),
            command.consequence,
            command.deadline,
            command.dedupe_key,
            list(command.source_facts),
            finding_id,
            actor.principal_id,
            now,
        ),
    )


def record_finding_disposition(
    dsn: str, actor: Actor, command: FindingDisposition
) -> FindingDispositionReceipt | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        request_digest = hashlib.sha256(_canonical_bytes(command.request_payload())).digest()
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _disposition_receipt_from_payload(actor, command, existing)
        problem = _disposition_refusal(connection, transaction, actor, command, request_digest, now)
        if problem is not None:
            return problem
        return _record_disposition(connection, transaction, actor, command, request_digest, now)


def _disposition_refusal(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: FindingDisposition,
    request_digest: bytes,
    now: datetime,
) -> RecordProblem | None:
    finding = connection.execute(
        "SELECT 1 FROM attention_need_findings WHERE tenant_id = %s AND finding_id = %s",
        (actor.tenant_id, command.finding_id),
    ).fetchone()
    problem: RecordProblem | None = None
    if finding is None:
        problem = RecordProblem(
            code="attention-finding-not-found",
            detail="The tenant-scoped finding does not exist.",
            status=404,
            title="Finding not found",
            command_id=command.client_command_id,
        )
    elif _already_disposed(connection, actor, command.finding_id):
        problem = RecordProblem(
            code="attention-finding-already-disposed",
            detail="This finding already carries a disposition.",
            status=409,
            title="Finding already disposed",
            command_id=command.client_command_id,
        )
    if problem is not None:
        transaction.refuse(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            problem,
            now=now,
        )
    return problem


def _already_disposed(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, finding_id: UUID
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM attention_need_dispositions WHERE tenant_id = %s AND finding_id = %s",
        (actor.tenant_id, finding_id),
    ).fetchone()
    return row is not None


def _record_disposition(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: FindingDisposition,
    request_digest: bytes,
    now: datetime,
) -> FindingDispositionReceipt:
    disposition_id = _uuid7(now)
    receipt = FindingDispositionReceipt(
        actor.tenant_id, actor.principal_id, command, now, (disposition_id,)
    )
    payload = AttentionFindingDispositionRecordedPayload(
        disposition_id=disposition_id,
        finding_id=command.finding_id,
        outcome=command.outcome.value,
        reason=command.reason,
    )
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=disposition_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=disposition_id,
        kind=EventKind.ATTENTION_FINDING_DISPOSITION_RECORDED,
        origin=EventOrigin.API,
        payload=payload,
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"attention-finding-disposition:{disposition_id}",
        tenant_id=actor.tenant_id,
    )
    transaction.commit_control(
        event,
        outbox_id=_uuid7(now),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="attention.finding_dispositions",
    )
    connection.execute(
        """
        INSERT INTO attention_need_dispositions (
            disposition_id, tenant_id, finding_id, outcome, reason, event_id,
            actor_principal_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            disposition_id,
            actor.tenant_id,
            command.finding_id,
            command.outcome.value,
            command.reason,
            disposition_id,
            actor.principal_id,
            now,
        ),
    )
    return receipt


def _finding_receipt_from_payload(
    actor: Actor, command: AppendFinding, payload: dict[str, object]
) -> AttentionFindingReceipt:
    event_ids = tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"]))
    return AttentionFindingReceipt(
        actor.tenant_id,
        actor.principal_id,
        command,
        UUID(str(payload["finding_id"])),
        datetime.fromisoformat(str(payload["recorded_at"])),
        event_ids,
    )


def _disposition_receipt_from_payload(
    actor: Actor, command: FindingDisposition, payload: dict[str, object]
) -> FindingDispositionReceipt:
    event_ids = tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"]))
    return FindingDispositionReceipt(
        actor.tenant_id,
        actor.principal_id,
        command,
        datetime.fromisoformat(str(payload["recorded_at"])),
        event_ids,
    )


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = cast(
        dict[str, object],
        connection.execute("SELECT transaction_timestamp() AS value").fetchone(),
    )
    return cast(datetime, row["value"])


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
