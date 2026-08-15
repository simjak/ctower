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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

import psycopg
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from psycopg.types.json import Jsonb

from ctower_kernel.inbox.models import (
    InboxAcknowledgeCommand,
    InboxAcknowledgementState,
    InboxSendCommand,
)
from ctower_kernel.inbox.postgres import PostgresInbox
from ctower_kernel.knowledge._sql import register_document
from ctower_kernel.knowledge.models import KnowledgeAddCommand
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.artifacts import (
    ArtifactError,
    parse_artifact,
    verify_signed_artifact,
)
from ctower_kernel.record.estate_import_events import (
    CompanyRecordAppendedPayload,
    EstateImportChangedPayload,
)
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    event_digest,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.inbox_events import InboxParticipant
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._ruling_sql import append_ruling
from ctower_kernel.work._ruling_types import RulingAppend

__all__ = (
    "CompanyRecordAppend",
    "CompanyRecordAppendResult",
    "EstateImportBatchResult",
    "PostgresEstateImports",
    "append_company_record",
    "verify_estate_manifest",
)

_PARITY_SCHEMA = "ctower.estate-import-parity/v1"
_MANIFEST_SCHEMA = "ctower.estate-import-manifest/v1"
_HTTP_CONFLICT = 409
_MAX_NATURAL_KEY = 256
_MAX_SOURCE_REF = 512
_MAX_SOURCE_SEAT = 128
_MAX_SUBJECT = 1024
_MAX_BODY = 65536
_ESTATE_ROW_NAMESPACE = UUID("0eeb5f0d-8b5a-5c5b-b2f0-3ea8be7b7e22")
_ESTATE_READ_NAMESPACE = UUID("d3cb3c2e-44c5-5fb9-8f98-9fbfca91e570")


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


def _inbox_send_command(
    actor: Actor,
    row: Mapping[str, object],
    *,
    sender: InboxParticipant,
    recipient: InboxParticipant,
) -> InboxSendCommand:
    """Translate one verified estate row into a deterministic inbox command."""
    source_ref = _required_text(row, "source_ref")
    message_id = UUID(_required_text(row, "message_id"))
    sent_at = _import_timestamp(row["sent_at"])
    subject = _required_text(row, "subject", allow_empty=True)
    body = _required_text(row, "body")
    text = f"{subject}\n\n{body}" if subject else body
    return InboxSendCommand(
        uuid5(_ESTATE_ROW_NAMESPACE, f"{actor.tenant_id}:inbox-send:{source_ref}"),
        recipient.seat_key,
        text,
        message_id=message_id,
        sent_at=sent_at,
        source_ref=source_ref,
        source_sender=_required_text(row, "source_sender"),
        source_recipient=_required_text(row, "source_recipient"),
        sender_principal_id=sender.principal_id,
        sender_seat=sender.seat_key,
        origin=EventOrigin.MIGRATION_IMPORTER,
    )


def _inbox_acknowledge_command(
    command: InboxSendCommand,
    state: InboxAcknowledgementState = InboxAcknowledgementState.READ,
) -> InboxAcknowledgeCommand:
    """Carry source-recorded time and migration origin into delivery facts."""
    if command.message_id is None or command.sent_at is None:
        raise ValueError("estate inbox acknowledgement requires message identity and timestamp")
    return InboxAcknowledgeCommand(
        uuid5(_ESTATE_READ_NAMESPACE, f"inbox-read:{command.client_command_id}"),
        command.message_id,
        state,
        recorded_at=command.sent_at,
        origin=EventOrigin.MIGRATION_IMPORTER,
    )


def _ruling_import_command(
    actor: Actor,
    row: Mapping[str, object],
    *,
    project_key: str | None = None,
) -> RulingAppend:
    """Translate one verified estate row into a historical Ruling command."""
    source_ref = _required_text(row, "source_ref")
    verbatim = _required_text(row, "verbatim")
    recorded_at = _import_timestamp(row["recorded_at"])
    content_sha256 = _required_text(row, "content_sha256")
    _require_content_digest(verbatim, content_sha256)
    ruling_id_value = row.get("ruling_id")
    ruling_id = (
        UUID(str(ruling_id_value))
        if ruling_id_value is not None
        else uuid5(_ESTATE_ROW_NAMESPACE, f"ruling:{source_ref}")
    )
    return RulingAppend(
        uuid5(_ESTATE_ROW_NAMESPACE, f"{actor.tenant_id}:ruling:{source_ref}"),
        verbatim,
        source_ref=source_ref,
        recorded_at=recorded_at,
        project_key=project_key,
        ruling_id=ruling_id,
        origin=EventOrigin.MIGRATION_IMPORTER,
    )


def _knowledge_import_command(
    actor: Actor,
    row: Mapping[str, object],
) -> KnowledgeAddCommand:
    """Translate one verified estate row into a historical Knowledge command."""
    document_id = UUID(_required_text(row, "document_id"))
    source_ref = _required_text(row, "source_ref")
    title = _required_text(row, "title")
    body = _required_text(row, "body")
    recorded_at = _import_timestamp(row["recorded_at"])
    content_sha256 = _required_text(row, "content_sha256")
    _require_content_digest(body, content_sha256)
    scope = row.get("scope", "org")
    project_key = row.get("project_key")
    if not isinstance(scope, str) or not isinstance(project_key, (str, type(None))):
        raise TypeError("estate knowledge scope is invalid")
    return KnowledgeAddCommand(
        uuid5(_ESTATE_ROW_NAMESPACE, f"{actor.tenant_id}:knowledge:{source_ref}"),
        scope,
        body=body,
        project_key=project_key,
        source_ref=source_ref,
        title=title,
        recorded_at=recorded_at,
        document_id=document_id,
        origin=EventOrigin.MIGRATION_IMPORTER,
    )


def _company_import_command(
    actor: Actor,
    row: Mapping[str, object],
) -> CompanyRecordAppend:
    """Translate one verified estate row into a company-record command."""
    record_type = _required_text(row, "record_type")
    natural_key = _required_text(row, "natural_key")
    occurred_on = _required_text(row, "occurred_on")
    seat = _required_text(row, "seat")
    source_ref = _required_text(row, "source_ref")
    imported_at = _import_timestamp(row["imported_at"])
    payload = row.get("payload")
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("estate company-record payload is invalid")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        raise ValueError("estate company-record payload values must be strings")
    typed_payload = tuple(sorted((str(key), str(value)) for key, value in payload.items()))
    return CompanyRecordAppend(
        uuid5(_ESTATE_ROW_NAMESPACE, f"{actor.tenant_id}:company:{source_ref}"),
        record_type,
        natural_key,
        occurred_on,
        seat,
        typed_payload,
        source_ref,
        imported_at,
    )


def _require_content_digest(content: str, digest: str) -> None:
    expected = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    if digest != expected:
        raise ValueError("estate import content digest does not match the source fields")


def _required_text(row: Mapping[str, object], key: str, *, allow_empty: bool = False) -> str:
    value = row.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"estate inbox row field {key!r} is invalid")
    return value


def _import_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("estate inbox timestamp is invalid")
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError("estate inbox timestamp must be timezone-aware")
    return timestamp.astimezone(UTC)


class _EstateParitySigner(Protocol):
    def seal(self, artifact: Mapping[str, object], digest_field: str) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class EstateImportBatchResult:
    """One durable response for a bounded estate batch."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    tier: str
    manifest_digest: str
    source_count: int
    imported_count: int
    parity: Mapping[str, object]
    durability_state: str = "durability_pending"

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": self.durability_state,
            "event_ids": [str(event_id) for event_id in self.event_ids],
            "tier": self.tier,
            "manifest_digest": self.manifest_digest,
            "source_count": self.source_count,
            "imported_count": self.imported_count,
            "parity": dict(self.parity),
        }


@dataclass(frozen=True, slots=True)
class _InboxImportPlan:
    row: Mapping[str, object]
    source_sender: str
    source_recipient: str
    sender: InboxParticipant | None
    recipient: InboxParticipant | None
    command: InboxSendCommand | None
    source_only: bool


@dataclass(frozen=True, slots=True)
class _RulingImportPlan:
    row: Mapping[str, object]
    command: RulingAppend
    source_only: bool = True


@dataclass(frozen=True, slots=True)
class _KnowledgeImportPlan:
    row: Mapping[str, object]
    command: KnowledgeAddCommand
    source_only: bool = True


@dataclass(frozen=True, slots=True)
class _CompanyImportPlan:
    row: Mapping[str, object]
    command: CompanyRecordAppend
    source_only: bool = True


type _EstateImportPlan = (
    _InboxImportPlan | _RulingImportPlan | _KnowledgeImportPlan | _CompanyImportPlan
)


class PostgresEstateImports:
    """Operator-only PostgreSQL adapter for all estate-import tiers."""

    def __init__(
        self,
        dsn: str,
        trusted_keys: Mapping[tuple[str, int], Ed25519PublicKey],
        *,
        parity_signer: _EstateParitySigner | None,
        inbox: PostgresInbox | None = None,
    ) -> None:
        self._dsn = dsn
        self._trusted_keys = trusted_keys
        self._parity_signer = parity_signer
        self._inbox = inbox or PostgresInbox(dsn)

    def import_batch(
        self,
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: self._apply_batch(
                actor,
                tier=tier,
                batch_index=batch_index,
                command_id=command_id,
                manifest=manifest,
                rows=rows,
                now=now,
                telemetry=telemetry,
            )
        )

    def _apply_batch(
        self,
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | RecordProblem:
        with authority_connection(self._dsn) as connection:
            connection.execute("SET ROLE ctower_svc")
            refusal = _operator_refusal(connection, actor, command_id)
            if refusal is not None:
                return refusal
            prepared = self._prepare_import(
                connection,
                actor,
                tier=tier,
                batch_index=batch_index,
                command_id=command_id,
                manifest=manifest,
                rows=rows,
            )
            if isinstance(prepared, RecordProblem):
                return prepared
            manifest_digest, plans = prepared
            return self._commit_inbox_batch(
                connection,
                actor,
                tier=tier,
                batch_index=batch_index,
                command_id=command_id,
                manifest_digest=manifest_digest,
                rows=rows,
                plans=plans,
                now=now,
                telemetry=telemetry,
            )

    def _prepare_import(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
    ) -> tuple[str, tuple[_EstateImportPlan, ...]] | RecordProblem:
        try:
            artifact, manifest_digest = self._verified_manifest(manifest, tier)
            prepared: tuple[_EstateImportPlan, ...] | RecordProblem
            if tier == "inbox_history":
                prepared = self._prepare_inbox_batch(
                    connection, actor, artifact, batch_index, rows, command_id
                )
            elif tier == "agreed_decisions":
                prepared = self._prepare_ruling_batch(
                    actor, artifact, batch_index, rows, command_id
                )
            elif tier == "knowledge_documents":
                prepared = self._prepare_knowledge_batch(
                    artifact, batch_index, rows, command_id, actor
                )
            elif tier == "company_records":
                prepared = self._prepare_company_batch(
                    artifact, batch_index, rows, command_id, actor
                )
            else:
                prepared = _estate_problem(
                    command_id,
                    "estate-import-invalid",
                    "Estate import tier is outside the contract.",
                )
        except (ArtifactError, KeyError, TypeError, ValueError) as error:
            return _estate_problem(command_id, "estate-import-invalid", str(error))
        if isinstance(prepared, RecordProblem):
            return prepared
        return manifest_digest, prepared

    def _prepare_ruling_batch(
        self,
        actor: Actor,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
    ) -> tuple[_RulingImportPlan, ...] | RecordProblem:
        header = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        if isinstance(header, RecordProblem):
            return header
        plans: list[_RulingImportPlan] = []
        seen: set[str] = set()
        project_key = artifact.get("project_key")
        project_key = project_key if isinstance(project_key, str) else None
        for row in rows:
            try:
                source_ref = _required_text(row, "source_ref")
                command = _ruling_import_command(actor, row, project_key=project_key)
            except (KeyError, TypeError, ValueError) as error:
                return _estate_problem(command_id, "estate-import-row-invalid", str(error))
            refusal = prohibited_data_refusal((command.verbatim, source_ref), command_id=command_id)
            if refusal is not None:
                return refusal
            if source_ref in seen:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            seen.add(source_ref)
            plans.append(_RulingImportPlan(row, command))
        problem = _validate_generic_batch_digest(header, "agreed_decisions", rows, command_id)
        if problem is not None:
            return problem
        return tuple(plans)

    def _prepare_knowledge_batch(
        self,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
        actor: Actor,
    ) -> tuple[_KnowledgeImportPlan, ...] | RecordProblem:
        header = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        if isinstance(header, RecordProblem):
            return header
        plans: list[_KnowledgeImportPlan] = []
        seen: set[str] = set()
        for row in rows:
            try:
                source_ref = _required_text(row, "source_ref")
                command = _knowledge_import_command(actor, row)
            except (KeyError, TypeError, ValueError) as error:
                return _estate_problem(command_id, "estate-import-row-invalid", str(error))
            refusal = prohibited_data_refusal(
                (command.title, command.body, source_ref), command_id=command_id
            )
            if refusal is not None:
                return refusal
            if source_ref in seen:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            seen.add(source_ref)
            plans.append(_KnowledgeImportPlan(row, command))
        problem = _validate_generic_batch_digest(header, "knowledge_documents", rows, command_id)
        if problem is not None:
            return problem
        return tuple(plans)

    def _prepare_company_batch(
        self,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
        actor: Actor,
    ) -> tuple[_CompanyImportPlan, ...] | RecordProblem:
        header = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        if isinstance(header, RecordProblem):
            return header
        plans: list[_CompanyImportPlan] = []
        seen: set[str] = set()
        for row in rows:
            try:
                source_ref = _required_text(row, "source_ref")
                command = _company_import_command(actor, row)
            except (KeyError, TypeError, ValueError) as error:
                return _estate_problem(command_id, "estate-import-row-invalid", str(error))
            if source_ref in seen:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            seen.add(source_ref)
            plans.append(_CompanyImportPlan(row, command))
        problem = _validate_generic_batch_digest(header, "company_records", rows, command_id)
        if problem is not None:
            return problem
        return tuple(plans)

    def _commit_inbox_batch(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest_digest: str,
        rows: Sequence[Mapping[str, object]],
        plans: Sequence[_EstateImportPlan],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | RecordProblem:
        request_digest = _digest_request(manifest_digest, batch_index, rows)
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _estate_replay(replay)
        if self._parity_signer is None:
            problem = _estate_problem(
                command_id,
                "estate-import-parity-signer-unavailable",
                "Estate import parity requires an approved signing key.",
                status=503,
            )
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command_id,
                request_digest,
                problem,
                now=now,
            )
            return problem
        imported = self._apply_inbox_plans(
            actor,
            plans,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
            connection=connection,
        )
        if isinstance(imported, RecordProblem):
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command_id,
                request_digest,
                imported,
                now=now,
            )
            return imported
        parity = (
            _inbox_parity(
                tier=tier,
                manifest_digest=manifest_digest,
                batch_index=batch_index,
                plans=cast(Sequence[_InboxImportPlan], plans),
                signer=self._parity_signer,
            )
            if tier == "inbox_history"
            else _generic_parity(
                tier=tier,
                manifest_digest=manifest_digest,
                batch_index=batch_index,
                rows=rows,
                imported_count=imported,
                signer=self._parity_signer,
            )
        )
        event = _estate_batch_event(
            actor,
            command_id,
            tier=tier,
            manifest_digest=manifest_digest,
            batch_index=batch_index,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        result = EstateImportBatchResult(
            command_id,
            (event.event_id,),
            tier,
            manifest_digest,
            len(plans),
            imported,
            parity,
        )
        transaction.commit_batch(
            (EventCommit(event, uuid7(now)),),
            response_body=result.response_payload(),
            status_code=201,
            telemetry=telemetry,
            now=now,
        )
        return result

    def _verified_manifest(
        self, manifest: Mapping[str, object], tier: str
    ) -> tuple[dict[str, Any], str]:
        signature = manifest.get("signature")
        if not isinstance(signature, Mapping):
            raise ArtifactError("signature-invalid")
        key_ref, key_version = signature.get("key_ref"), signature.get("key_version")
        if not isinstance(key_ref, str) or not isinstance(key_version, int):
            raise ArtifactError("signature-invalid")
        public_key = self._trusted_keys.get((key_ref, key_version))
        if public_key is None:
            raise ArtifactError("review-key-untrusted")
        text = rfc8785.dumps(cast(Any, manifest)).decode("utf-8")
        counts = manifest.get("counts")
        if not isinstance(counts, Mapping):
            raise ArtifactError("artifact-invalid")
        source_count = counts.get("source_rows")
        if not isinstance(source_count, int):
            raise ArtifactError("artifact-invalid")
        artifact = verify_estate_manifest(
            text,
            tier=tier,
            source_row_count=source_count,
            public_key=public_key,
        )
        digest = artifact.get("manifest_digest")
        if not isinstance(digest, str):
            raise ArtifactError("artifact-invalid")
        return artifact, digest

    def _prepare_inbox_batch(
        self,
        connection: psycopg.Connection[dict[str, object]],
        actor: Actor,
        artifact: Mapping[str, object],
        batch_index: int,
        rows: Sequence[Mapping[str, object]],
        command_id: UUID,
    ) -> tuple[_InboxImportPlan, ...] | RecordProblem:
        batch = _inbox_batch_header(artifact, batch_index, len(rows), command_id)
        if isinstance(batch, RecordProblem):
            return batch
        plans: list[_InboxImportPlan] = []
        source_refs: set[str] = set()
        for row in rows:
            problem = _validate_inbox_row(row, command_id)
            if problem is not None:
                return problem
            source_ref = _required_text(row, "source_ref")
            if source_ref in source_refs:
                return _estate_problem(
                    command_id,
                    "estate-import-duplicate-source",
                    "A batch contains a duplicate source reference.",
                )
            source_refs.add(source_ref)
            source_sender = _required_text(row, "source_sender")
            source_recipient = _required_text(row, "source_recipient")
            sender = _seat_for_source(connection, actor.tenant_id, source_sender)
            recipient = _seat_for_source(connection, actor.tenant_id, source_recipient)
            source_only = (
                sender is None or recipient is None or sender.principal_id == recipient.principal_id
            )
            if source_only:
                command = None
            else:
                if sender is None or recipient is None:
                    raise RuntimeError("mapped inbox plan lost a participant")
                command = _inbox_send_command(actor, row, sender=sender, recipient=recipient)
            plans.append(
                _InboxImportPlan(
                    row=row,
                    source_sender=source_sender,
                    source_recipient=source_recipient,
                    sender=sender,
                    recipient=recipient,
                    command=command,
                    source_only=source_only,
                )
            )
        expected_digest = batch.get("batch_digest")
        projected_rows = [_manifest_projection(plan) for plan in plans]
        if expected_digest != _digest_json(projected_rows):
            return _estate_problem(
                command_id,
                "estate-import-batch-digest-mismatch",
                "Batch rows do not match the signed batch digest.",
            )
        return tuple(plans)

    def _apply_inbox_plans(
        self,
        actor: Actor,
        plans: Sequence[_EstateImportPlan],
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
        connection: psycopg.Connection[dict[str, object]],
    ) -> int | RecordProblem:
        for plan in plans:
            problem = self._apply_plan(
                actor,
                plan,
                command_id=command_id,
                now=now,
                telemetry=telemetry,
                connection=connection,
            )
            if problem is not None:
                return problem
        return len(plans)

    def _apply_plan(
        self,
        actor: Actor,
        plan: _EstateImportPlan,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
        connection: psycopg.Connection[dict[str, object]],
    ) -> RecordProblem | None:
        if isinstance(plan, _InboxImportPlan):
            return self._apply_inbox_plan(
                actor,
                plan,
                command_id=command_id,
                now=now,
                telemetry=telemetry,
                connection=connection,
            )
        if isinstance(plan, _RulingImportPlan):
            ruling_result = append_ruling(
                self._dsn,
                actor,
                plan.command,
                request_digest=_digest_request("ruling-import", 0, [plan.row]),
                now=now,
                telemetry=telemetry,
            )
            return ruling_result if isinstance(ruling_result, RecordProblem) else None
        if isinstance(plan, _KnowledgeImportPlan):
            knowledge_result = register_document(
                self._dsn,
                actor,
                plan.command,
                request_digest=_digest_request("knowledge-import", 0, [plan.row]),
                now=now,
                telemetry=telemetry,
                source=None,
            )
            return knowledge_result if isinstance(knowledge_result, RecordProblem) else None
        company_result = append_company_record(
            self._dsn,
            actor,
            plan.command,
            request_digest=_digest_request("company-record-import", 0, [plan.row]),
            now=now,
            telemetry=telemetry,
        )
        return company_result if isinstance(company_result, RecordProblem) else None

    def _apply_inbox_plan(
        self,
        actor: Actor,
        plan: _InboxImportPlan,
        *,
        command_id: UUID,
        now: datetime,
        telemetry: TelemetryContext,
        connection: psycopg.Connection[dict[str, object]],
    ) -> RecordProblem | None:
        if plan.source_only:
            return _persist_source_only_message(connection, actor, plan, command_id, now)
        if plan.command is None:
            raise RuntimeError("mapped inbox plan has no send command")
        send = self._inbox.send(
            actor,
            plan.command,
            request_digest=_digest_request("inbox-send", 0, [plan.row]),
            now=now,
            telemetry=telemetry,
        )
        if isinstance(send, RecordProblem):
            return send
        state = InboxAcknowledgementState(
            "read" if plan.row["read_state"] == "read" else "delivered"
        )
        acknowledge = self._inbox.acknowledge(
            actor,
            _inbox_acknowledge_command(plan.command, state),
            request_digest=_digest_request("inbox-acknowledge", 0, [plan.row]),
            now=now,
            telemetry=telemetry,
        )
        return acknowledge if isinstance(acknowledge, RecordProblem) else None


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
                    cast(datetime, existing["imported_at"]),
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


def _estate_replay(payload: dict[str, object]) -> EstateImportBatchResult:
    body = payload.get("response_body")
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
        origin=EventOrigin.MIGRATION_IMPORTER,
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
        stream_id=f"estate-import:{manifest_digest}:{batch_index}",
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


def _same_record(row: dict[str, object], command: CompanyRecordAppend, payload_sha256: str) -> bool:
    return (
        str(row["occurred_on"]) == command.occurred_on
        and str(row["seat"]) == command.seat
        and bytes(cast(bytes, row["payload_sha256"])).hex() == payload_sha256
        and str(row["source_ref"]) == command.source_ref
    )
