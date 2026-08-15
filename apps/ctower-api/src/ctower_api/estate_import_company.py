"""Company-record persistence for estate imports."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ctower_api.estate_import_contracts import CompanyRecordAppend, CompanyRecordAppendResult
from ctower_api.estate_import_support import (
    _company_event,
    _operator_refusal,
    _same_record,
    json_canonical,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import TelemetryContext

__all__ = ("append_company_record",)


def append_company_record(
    dsn: str,
    actor: Actor,
    command: CompanyRecordAppend,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CompanyRecordAppendResult | RecordProblem:
    """Append one company record idempotently by (record_type, natural_key)."""
    return recover_ambiguous_commit(
        lambda: _append_company_record(
            dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
    )


def _append_company_record(
    dsn: str,
    actor: Actor,
    command: CompanyRecordAppend,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CompanyRecordAppendResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        refusal = _company_refusal(connection, actor, command)
        if refusal is not None:
            return refusal
        payload_canonical = dict(command.payload)
        payload_sha256 = hashlib.sha256(
            json_canonical(payload_canonical).encode("utf-8")
        ).hexdigest()
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _from_replay(replay)
        existing = _existing_company_record(connection, actor, command)
        if existing is not None:
            return _existing_company_result(existing, command, payload_sha256)
        return _insert_company_record(
            connection,
            transaction,
            actor,
            command,
            payload_canonical,
            payload_sha256,
            request_digest,
            now,
            telemetry,
        )


def _company_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyRecordAppend,
) -> RecordProblem | None:
    refusal = _operator_refusal(connection, actor, command.client_command_id)
    if refusal is not None:
        return refusal
    payload_values = [item for pair in command.payload for item in pair]
    return prohibited_data_refusal(
        (*payload_values, command.source_ref),
        command_id=command.client_command_id,
    )


def _existing_company_record(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyRecordAppend,
) -> Mapping[str, object] | None:
    return connection.execute(
        """
        SELECT record_id, occurred_on, seat, payload_sha256, source_ref, imported_at
        FROM company_records
        WHERE tenant_id = %s AND record_type = %s AND natural_key = %s
        """,
        (actor.tenant_id, command.record_type, command.natural_key),
    ).fetchone()


def _existing_company_result(
    existing: Mapping[str, object],
    command: CompanyRecordAppend,
    payload_sha256: str,
) -> CompanyRecordAppendResult | RecordProblem:
    if not _same_record(dict(existing), command, payload_sha256):
        return RecordProblem(
            "company-record-conflict",
            "Natural key already names an immutable different company record.",
            409,
            "Company record conflict",
            command.client_command_id,
        )
    return CompanyRecordAppendResult(
        command.client_command_id,
        cast(UUID, existing["record_id"]),
        command.record_type,
        command.natural_key,
        command.occurred_on,
        command.seat,
        f"sha256:{payload_sha256}",
        command.source_ref,
        cast(datetime, existing["imported_at"]),
        already_present=True,
    )


def _insert_company_record(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: CompanyRecordAppend,
    payload_canonical: dict[str, str],
    payload_sha256: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CompanyRecordAppendResult:
    record_id = uuid7(now)
    event, _digest = _company_event(
        actor, command, record_id, payload_sha256, request_digest, now, telemetry
    )
    result = CompanyRecordAppendResult(
        command.client_command_id,
        record_id,
        command.record_type,
        command.natural_key,
        command.occurred_on,
        command.seat,
        f"sha256:{payload_sha256}",
        command.source_ref,
        command.imported_at,
        already_present=False,
    )
    transaction.commit_batch(
        (EventCommit(event, uuid7(now)),),
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=(("company_record", record_id),),
    )
    connection.execute(
        """
        INSERT INTO company_records (
            record_id, tenant_id, record_type, natural_key, occurred_on,
            seat, payload, payload_sha256, source_ref, imported_by,
            imported_at, command_id, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record_id,
            actor.tenant_id,
            command.record_type,
            command.natural_key,
            command.occurred_on,
            command.seat,
            Jsonb(payload_canonical),
            bytes.fromhex(payload_sha256),
            command.source_ref,
            actor.principal_id,
            command.imported_at,
            command.client_command_id,
            event.event_id,
        ),
    )
    return result


def _from_replay(payload: dict[str, object]) -> CompanyRecordAppendResult:
    body = payload.get("response_body", payload)
    if not isinstance(body, dict):
        raise TypeError("committed company-record result has no response body")
    return CompanyRecordAppendResult(
        UUID(str(body["command_id"])),
        UUID(str(body["record_id"])),
        str(body["record_type"]),
        str(body["natural_key"]),
        str(body["occurred_on"]),
        str(body["seat"]),
        str(body["payload_sha256"]),
        str(body["source_ref"]),
        datetime.fromisoformat(str(body["imported_at"])),
        already_present=True,
    )
