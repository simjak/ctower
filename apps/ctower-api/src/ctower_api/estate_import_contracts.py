"""Typed estate-import contracts and validation primitives."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ctower_kernel.inbox import InboxAcknowledgeCommand, InboxAcknowledgementState, InboxSendCommand
from ctower_kernel.knowledge import KnowledgeAddCommand
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.artifacts import ArtifactError, parse_artifact, verify_signed_artifact
from ctower_kernel.record.events import EventOrigin
from ctower_kernel.record.inbox_events import InboxParticipant
from ctower_kernel.work.rulings import RulingAppend

__all__ = (
    "CompanyRecordAppend",
    "CompanyRecordAppendResult",
    "EstateImportBatchResult",
    "_EstateImportPlan",
    "_EstateParitySigner",
    "verify_estate_manifest",
)

_PARITY_SCHEMA = "ctower.estate-import-parity/v1"
_MANIFEST_SCHEMA = "ctower.estate-import-manifest/v1"
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
        origin=EventOrigin.ESTATE_IMPORT,
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
        origin=EventOrigin.ESTATE_IMPORT,
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
        origin=EventOrigin.ESTATE_IMPORT,
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
        origin=EventOrigin.ESTATE_IMPORT,
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
    prohibited: RecordProblem | None = None


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
