"""Shared persistence, digest, and parity support for estate imports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid5

import psycopg
import rfc8785

from ctower_api.estate_import_contracts import (
    _ESTATE_ROW_NAMESPACE,
    _MAX_BODY,
    _MAX_SOURCE_REF,
    _MAX_SOURCE_SEAT,
    _MAX_SUBJECT,
    _PARITY_SCHEMA,
    CompanyRecordAppend,
    EstateImportBatchResult,
    _EstateParitySigner,
    _import_timestamp,
    _InboxImportPlan,
    _required_text,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.estate_import_events import (
    CompanyRecordAppendedPayload,
    EstateImportChangedPayload,
)
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin, event_digest
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.inbox_events import InboxParticipant
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def _estate_replay(payload: dict[str, object]) -> EstateImportBatchResult:
    body = payload.get("response_body", payload)
    if not isinstance(body, Mapping):
        raise TypeError("committed estate-import result has no response body")
    event_ids = body.get("event_ids")
    parity = body.get("parity")
    if not isinstance(event_ids, list) or not isinstance(parity, Mapping):
        raise TypeError("committed estate-import result is incomplete")
    return EstateImportBatchResult(
        UUID(str(body["command_id"])),
        tuple(UUID(str(item)) for item in event_ids),
        str(body["tier"]),
        str(body["manifest_digest"]),
        int(cast(int, body["source_count"])),
        int(cast(int, body["imported_count"])),
        dict(parity),
        str(body.get("durability_state", "durability_pending")),
    )


def _estate_problem(
    command_id: UUID,
    code: str,
    detail: str,
    *,
    status: int = 422,
) -> RecordProblem:
    return RecordProblem(code, detail, status, "Estate import refused", command_id)


def _inbox_batch_header(
    artifact: Mapping[str, object],
    batch_index: int,
    row_count: int,
    command_id: UUID,
) -> Mapping[str, object] | RecordProblem:
    batches = artifact.get("batches")
    if not isinstance(batches, list) or batch_index < 0 or batch_index >= len(batches):
        return _estate_problem(
            command_id,
            "estate-import-batch-invalid",
            "Batch is absent from the manifest.",
        )
    batch = batches[batch_index]
    if not isinstance(batch, Mapping) or batch.get("batch_index") != batch_index:
        return _estate_problem(
            command_id,
            "estate-import-batch-invalid",
            "Manifest batches are not contiguous.",
        )
    declared_count = batch.get("source_count")
    if not isinstance(declared_count, int) or declared_count != row_count:
        return _estate_problem(
            command_id,
            "estate-import-count-mismatch",
            "Batch row count differs from the signed manifest.",
        )
    return batch


def _validate_generic_batch_digest(
    header: Mapping[str, object],
    tier: str,
    rows: Sequence[Mapping[str, object]],
    command_id: UUID,
) -> RecordProblem | None:
    expected = header.get("batch_digest")
    projected = [_generic_manifest_projection(tier, row) for row in rows]
    if expected != _digest_json(projected):
        return _estate_problem(
            command_id,
            "estate-import-batch-digest-mismatch",
            "Batch rows do not match the signed batch digest.",
        )
    return None


def _generic_manifest_projection(tier: str, row: Mapping[str, object]) -> dict[str, object]:
    source_ref = _required_text(row, "source_ref")
    content_sha256 = _required_text(row, "content_sha256")
    source_seat = row.get("source_seat", row.get("seat", "unknown-owner"))
    projection: dict[str, object] = {
        "_disposition": row.get("_disposition", "source_only"),
        "content_sha256": content_sha256,
        "source_ref": source_ref,
        "source_seat": source_seat,
    }
    if tier == "company_records":
        projection["natural_key"] = _required_text(row, "natural_key")
        projection["target_seat_key"] = row.get("target_seat_key")
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("estate company-record payload is invalid")
        projection["payload"] = dict(payload)
    return projection


def _validate_inbox_row(row: Mapping[str, object], command_id: UUID) -> RecordProblem | None:
    try:
        message_id = UUID(_required_text(row, "message_id"))
        source_ref = _required_text(row, "source_ref")
        source_sender = _required_text(row, "source_sender")
        source_recipient = _required_text(row, "source_recipient")
        sent_at = _import_timestamp(row["sent_at"])
        subject = _required_text(row, "subject", allow_empty=True)
        body = _required_text(row, "body")
        read_state = _required_text(row, "read_state")
        content_sha256 = _required_text(row, "content_sha256")
    except (KeyError, TypeError, ValueError) as error:
        return _estate_problem(command_id, "estate-import-row-invalid", str(error))
    del message_id, sent_at
    if (
        len(source_ref) > _MAX_SOURCE_REF
        or len(source_sender) > _MAX_SOURCE_SEAT
        or len(source_recipient) > _MAX_SOURCE_SEAT
    ):
        return _estate_problem(
            command_id,
            "estate-import-row-invalid",
            "Inbox source identity exceeds its contract bounds.",
        )
    if len(subject) > _MAX_SUBJECT or len(body) > _MAX_BODY:
        return _estate_problem(
            command_id,
            "estate-import-row-invalid",
            "Inbox content exceeds its contract bounds.",
        )
    if read_state not in {"delivered", "read"}:
        return _estate_problem(
            command_id,
            "estate-import-row-invalid",
            "Inbox read state is outside the contract.",
        )
    expected_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps({"subject": subject, "body": body}, sort_keys=True).encode("utf-8")
        ).hexdigest()
    )
    if content_sha256 != expected_digest:
        return _estate_problem(
            command_id,
            "estate-import-content-mismatch",
            "Inbox content digest does not match the source fields.",
        )
    return prohibited_data_refusal(
        (source_ref, source_sender, source_recipient, subject, body),
        command_id=command_id,
    )


def _seat_for_source(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, source_seat: str
) -> InboxParticipant | None:
    rows = connection.execute(
        """
        SELECT principal_id, seat_key FROM project_seats
        WHERE tenant_id = %s AND seat_key = %s ORDER BY principal_id
        """,
        (tenant_id, source_seat),
    ).fetchall()
    if len(rows) != 1:
        return None
    row = rows[0]
    return InboxParticipant(cast(UUID, row["principal_id"]), str(row["seat_key"]))


def _manifest_projection(plan: _InboxImportPlan) -> dict[str, object]:
    return {
        "_disposition": "source_only" if plan.source_only else "mapped",
        "content_sha256": _required_text(plan.row, "content_sha256"),
        "source_ref": _required_text(plan.row, "source_ref"),
        "source_seat": plan.source_sender,
        "target_seat_key": plan.sender.seat_key if plan.sender is not None else None,
    }


def _digest_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(cast(Any, value))).hexdigest()


def _digest_request(
    operation: str, batch_index: int, rows: Sequence[Mapping[str, object]]
) -> bytes:
    return hashlib.sha256(
        rfc8785.dumps(cast(Any, {"batch_index": batch_index, "operation": operation, "rows": rows}))
    ).digest()


def _persist_source_only_message(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    plan: _InboxImportPlan,
    command_id: UUID,
    now: datetime,
) -> RecordProblem | None:
    row = plan.row
    source_ref = _required_text(row, "source_ref")
    message_id = UUID(_required_text(row, "message_id"))
    sent_at = _import_timestamp(row["sent_at"])
    subject = _required_text(row, "subject", allow_empty=True)
    body = _required_text(row, "body")
    read_state = _required_text(row, "read_state")
    content_digest = _required_text(row, "content_sha256")
    existing = connection.execute(
        """
        SELECT message_id, source_sender, source_recipient, sent_at, subject, body,
               read_state, content_sha256
        FROM estate_import_source_only_messages
        WHERE tenant_id = %s AND source_ref = %s
        """,
        (actor.tenant_id, source_ref),
    ).fetchone()
    if existing is not None:
        same = (
            existing["message_id"] == message_id
            and str(existing["source_sender"]) == plan.source_sender
            and str(existing["source_recipient"]) == plan.source_recipient
            and existing["sent_at"] == sent_at
            and str(existing["subject"]) == subject
            and str(existing["body"]) == body
            and str(existing["read_state"]) == read_state
            and bytes(cast(bytes, existing["content_sha256"])).hex()
            == content_digest.removeprefix("sha256:")
        )
        if same:
            return None
        return _estate_problem(
            command_id,
            "estate-import-source-conflict",
            "Source reference already names different immutable inbox content.",
            status=409,
        )
    row_command_id = uuid5(_ESTATE_ROW_NAMESPACE, f"{actor.tenant_id}:source-only:{source_ref}")
    connection.execute(
        """
        INSERT INTO estate_import_source_only_messages (
            message_id, tenant_id, source_ref, source_sender, source_recipient,
            sent_at, subject, body, read_state, content_sha256, source_only_disposition,
            imported_by, imported_at, command_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'source_only', %s, %s, %s)
        """,
        (
            message_id,
            actor.tenant_id,
            source_ref,
            plan.source_sender,
            plan.source_recipient,
            sent_at,
            subject,
            body,
            read_state,
            bytes.fromhex(content_digest.removeprefix("sha256:")),
            actor.principal_id,
            now,
            row_command_id,
        ),
    )
    return None


def _inbox_parity(
    *,
    tier: str,
    manifest_digest: str,
    batch_index: int,
    plans: Sequence[_InboxImportPlan],
    signer: _EstateParitySigner,
) -> dict[str, object]:
    owner_counts: dict[str, int] = {}
    for plan in plans:
        if plan.source_only:
            owner_counts[plan.source_sender] = owner_counts.get(plan.source_sender, 0) + 1
    report: dict[str, object] = {
        "schema": _PARITY_SCHEMA,
        "tier": tier,
        "manifest_digest": manifest_digest,
        "source_count": len(plans),
        "imported_count": len(plans),
        "batches": [
            {
                "batch_index": batch_index,
                "batch_digest": _digest_json([_manifest_projection(plan) for plan in plans]),
                "source_count": len(plans),
                "imported_count": len(plans),
            }
        ],
        "sampled_content_hashes": [
            {
                "source_ref": _required_text(plan.row, "source_ref"),
                "content_sha256": _required_text(plan.row, "content_sha256"),
            }
            for plan in plans[:3]
        ],
        "source_only_owners": [
            {
                "source_seat": source_seat,
                "row_count": count,
                "source_only_disposition": "source_only",
            }
            for source_seat, count in sorted(owner_counts.items())
        ],
        "emitted_before_closure": True,
    }
    return signer.seal(report, "parity_digest")


def _generic_parity(
    *,
    tier: str,
    manifest_digest: str,
    batch_index: int,
    rows: Sequence[Mapping[str, object]],
    imported_count: int,
    signer: _EstateParitySigner,
) -> dict[str, object]:
    owner_counts: dict[str, int] = {}
    for row in rows:
        owner = str(row.get("source_seat", row.get("seat", "unknown-owner")))
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
    report: dict[str, object] = {
        "schema": _PARITY_SCHEMA,
        "tier": tier,
        "manifest_digest": manifest_digest,
        "source_count": len(rows),
        "imported_count": imported_count,
        "batches": [
            {
                "batch_index": batch_index,
                "batch_digest": _digest_json(
                    [_generic_manifest_projection(tier, row) for row in rows]
                ),
                "source_count": len(rows),
                "imported_count": imported_count,
            }
        ],
        "sampled_content_hashes": [
            {
                "source_ref": _required_text(row, "source_ref"),
                "content_sha256": _required_text(row, "content_sha256"),
            }
            for row in rows[:3]
        ],
        "source_only_owners": [
            {
                "source_seat": source_seat,
                "row_count": count,
                "source_only_disposition": "source_only",
            }
            for source_seat, count in sorted(owner_counts.items())
        ],
        "emitted_before_closure": True,
    }
    return signer.seal(report, "parity_digest")


def _estate_batch_event(
    actor: Actor,
    command_id: UUID,
    *,
    tier: str,
    manifest_digest: str,
    batch_index: int,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    aggregate_id = uuid5(
        _ESTATE_ROW_NAMESPACE,
        f"{actor.tenant_id}:estate-batch:{manifest_digest}:{batch_index}",
    )
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=aggregate_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=telemetry.correlation_uuid(command_id),
        event_id=uuid7(now),
        kind=EventKind.ESTATE_IMPORT_CHANGED,
        origin=EventOrigin.ESTATE_IMPORT,
        payload=EstateImportChangedPayload(
            tier,
            manifest_digest,
            "batch_applied",
            f"estate-import:{tier}:{batch_index}",
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"estate-import:{aggregate_id}",
        tenant_id=actor.tenant_id,
    )


def _operator_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
) -> RecordProblem | None:
    row = connection.execute(
        """
        SELECT kind FROM principals WHERE tenant_id = %s AND principal_id = %s
        """,
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    if row is None or str(row["kind"]) != PrincipalKind.OPERATOR.value:
        return RecordProblem(
            "estate-import-operator-required",
            "Estate imports require operator authority.",
            403,
            "Operator authority required",
            command_id,
        )
    return None


def _company_event(
    actor: Actor,
    command: CompanyRecordAppend,
    record_id: UUID,
    payload_sha256: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventEnvelope, bytes]:
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=record_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=uuid7(now),
        kind=EventKind.COMPANY_RECORD_APPENDED,
        origin=EventOrigin.ESTATE_IMPORT,
        payload=CompanyRecordAppendedPayload(
            record_id,
            command.record_type,
            command.natural_key,
            command.occurred_on,
            command.seat,
            f"sha256:{payload_sha256}",
            command.source_ref,
            command.imported_at,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"company-record:{record_id}",
        tenant_id=actor.tenant_id,
    )
    return event, event_digest(event)


def json_canonical(value: dict[str, str]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _same_record(row: dict[str, object], command: CompanyRecordAppend, payload_sha256: str) -> bool:
    return (
        str(row["occurred_on"]) == command.occurred_on
        and str(row["seat"]) == command.seat
        and bytes(cast(bytes, row["payload_sha256"])).hex() == payload_sha256
        and str(row["source_ref"]) == command.source_ref
    )
