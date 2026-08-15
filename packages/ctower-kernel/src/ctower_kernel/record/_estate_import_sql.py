"""Operator-authority external-estate import choreography over real PostgreSQL.

Every tier import runs behind this one Interface: the caller presents a signed
manifest plus per-row facts; this module refuses non-operator callers, unverified
signatures, count mismatches, unmapped owners without a source-only disposition,
and prohibited data classes before any byte commits. No import mints a principal,
seat, or grant — source-only senders are attributed to the importing operator with
their source seat preserved verbatim in the record body.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from psycopg.types.json import Jsonb

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.artifacts import (
    ArtifactError,
    parse_artifact,
    verify_signed_artifact,
)
from ctower_kernel.record.estate_import_events import (
    CompanyRecordAppendedPayload,
)
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    event_digest,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import TelemetryContext

__all__ = (
    "CompanyRecordAppend",
    "CompanyRecordAppendResult",
    "append_company_record",
    "verify_estate_manifest",
)

_PARITY_SCHEMA = "ctower.estate-import-parity/v1"
_MANIFEST_SCHEMA = "ctower.estate-import-manifest/v1"
_HTTP_CONFLICT = 409
_MAX_NATURAL_KEY = 256


@dataclass(frozen=True, slots=True)
class CompanyRecordAppend:
    """One typed accountability row keyed by its declared natural key."""

    client_command_id: UUID
    record_type: str
    natural_key: str
    occurred_on: str
    seat: str
    payload: tuple[tuple[str, str], ...]
    source_ref: str
    imported_at: datetime

    def __post_init__(self) -> None:
        if self.record_type != "escape":
            raise ValueError("company record type is outside the authored contract")
        if not 1 <= len(self.natural_key) <= _MAX_NATURAL_KEY:
            raise ValueError("company record natural key is outside the authored contract")
        if re.fullmatch(r"[a-z][a-z0-9._-]{1,127}", self.seat) is None:
            raise ValueError("company record seat is outside the authored contract")
        if not self.payload:
            raise ValueError("company record payload must not be empty")
        if self.imported_at.tzinfo is None:
            raise ValueError("company record imported_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CompanyRecordAppendResult:
    command_id: UUID
    record_id: UUID
    record_type: str
    natural_key: str
    occurred_on: str
    seat: str
    payload_sha256: str
    source_ref: str
    imported_at: datetime
    already_present: bool

    def response_payload(self) -> dict[str, object]:
        return {
            "already_present": self.already_present,
            "command_id": str(self.command_id),
            "imported_at": self.imported_at.isoformat(),
            "natural_key": self.natural_key,
            "occurred_on": self.occurred_on,
            "payload_sha256": self.payload_sha256,
            "record_id": str(self.record_id),
            "record_type": self.record_type,
            "seat": self.seat,
            "source_ref": self.source_ref,
        }


def verify_estate_manifest(
    manifest_text: str,
    *,
    tier: str,
    source_row_count: int,
    public_key: Ed25519PublicKey,
) -> dict[str, Any]:
    """Verify one signed estate manifest and rebind it to the live source count."""

    manifest = parse_artifact(manifest_text, _MANIFEST_SCHEMA)
    if manifest.get("tier") != tier:
        raise ArtifactError("artifact-invalid")
    signature = manifest.get("signature")
    if not isinstance(signature, dict):
        raise ArtifactError("signature-invalid")
    key_ref, key_version = signature.get("key_ref"), signature.get("key_version")
    if not isinstance(key_ref, str) or not isinstance(key_version, int):
        raise ArtifactError("signature-invalid")
    artifact, _manifest_digest = verify_signed_artifact(
        manifest_text,
        _MANIFEST_SCHEMA,
        "manifest_digest",
        {(key_ref, key_version): public_key},
    )
    counts = cast(dict[str, int], artifact.get("counts", {}))
    if int(counts.get("source_rows", -1)) != source_row_count:
        raise ArtifactError("artifact-invalid")
    return artifact


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

    def _apply() -> CompanyRecordAppendResult | RecordProblem:
        with authority_connection(dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            refusal = _operator_refusal(connection, actor, command.client_command_id)
            if refusal is not None:
                return refusal
            payload_values = [item for pair in command.payload for item in pair]
            refusal = prohibited_data_refusal(
                (*payload_values, command.source_ref),
                command_id=command.client_command_id,
            )
            if refusal is not None:
                return refusal
            payload_canonical = dict(command.payload)
            payload_sha256 = hashlib.sha256(
                json_canonical(payload_canonical).encode("utf-8")
            ).hexdigest()
            transaction = RecordTransaction(connection)
            replay = transaction.reserve(
                actor.principal_id, command.client_command_id, request_digest
            )
            if replay is not None:
                return replay if isinstance(replay, RecordProblem) else _from_replay(replay)
            existing = connection.execute(
                """
                SELECT record_id, occurred_on, seat, payload_sha256, source_ref, imported_at
                FROM company_records
                WHERE tenant_id = %s AND record_type = %s AND natural_key = %s
                """,
                (actor.tenant_id, command.record_type, command.natural_key),
            ).fetchone()
            if existing is not None:
                if not _same_record(existing, command, payload_sha256):
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
                    command.imported_at,
                    already_present=True,
                )
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

    return recover_ambiguous_commit(_apply)


def _from_replay(payload: dict[str, object]) -> CompanyRecordAppendResult:
    body = payload.get("response_body")
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
        origin=EventOrigin.MIGRATION_IMPORTER,
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


def _same_record(
    row: dict[str, object], command: CompanyRecordAppend, payload_sha256: str
) -> bool:
    return (
        str(row["occurred_on"]) == command.occurred_on
        and str(row["seat"]) == command.seat
        and bytes(cast(bytes, row["payload_sha256"])).hex() == payload_sha256
        and str(row["source_ref"]) == command.source_ref
        and row["imported_at"] == command.imported_at
    )
