"""Private secret exclusion and redacted diagnostic helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ctowerctl.spool._recovery import CorruptRecord, RecoveredRecord, Session

__all__ = [
    "JsonObject",
    "SecretMaterialError",
    "ServerRefusal",
    "SpoolDoctorReport",
    "SpoolEntry",
    "SpoolState",
    "SpoolStatus",
    "canonical_json",
    "corrupt_entry",
    "digest_json",
    "discarded_entry",
    "doctor_failure",
    "entry_order",
    "reason_digest",
    "reject_secret_material",
    "spool_entry",
    "spool_status",
    "torn_entry",
    "unknown_status",
]

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

_FORBIDDEN_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "bearer",
        "bootstrap_capability",
        "bootstrap_token",
        "cookie",
        "credential",
        "credential_value",
        "password",
        "private_key",
        "refresh_token",
        "resolved_secret",
        "secret_value",
        "session_token",
        "token",
    }
)
_FIELD_NORMALIZER = re.compile(r"[^a-z0-9]+")
_MAX_REFUSAL_TITLE = 200
_MAX_REFUSAL_DETAIL = 1000


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SpoolState(StrEnum):
    """Durable command states visible to callers."""

    PENDING = "pending"
    ACCEPTED_ARCHIVE = "accepted_archive"
    QUARANTINE = "quarantine"


class ServerRefusal(_BoundaryModel):
    """The refusal the server named for one rejected command."""

    status: Annotated[int, Field(ge=400, le=599)]
    problem_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    title: Annotated[str, Field(min_length=1, max_length=_MAX_REFUSAL_TITLE)]
    detail: Annotated[str, Field(min_length=1, max_length=_MAX_REFUSAL_DETAIL)]


class SpoolEntry(_BoundaryModel):
    """Redacted command inventory row."""

    sequence: int | None
    command_id: UUID | None
    operation_id: str | None
    state: SpoolState
    enqueued_at: datetime | None
    expires_at: datetime | None
    bytes: Annotated[int, Field(ge=0)]
    reason_code: str | None = None
    artifact_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    server_refusal: ServerRefusal | None = None


class SpoolStatus(_BoundaryModel):
    """Low-cardinality redacted health and capacity summary."""

    origin_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    health: Literal["healthy", "degraded", "state_unknown"]
    pending_count: int | None
    accepted_count: int | None
    quarantine_count: int | None
    pending_bytes: int | None
    quarantine_bytes: int | None
    oldest_pending_seconds: float | None
    last_accepted_sequence: int | None
    keyring_available: bool
    chain_status: Literal["healthy", "degraded", "state_unknown"]
    reason_codes: tuple[str, ...] = ()


class SpoolDoctorReport(_BoundaryModel):
    """Non-mutating verification report."""

    healthy: bool
    state: Literal["healthy", "degraded", "state_unknown", "uninitialized"]
    checks: tuple[str, ...]
    findings: tuple[str, ...]


class SecretMaterialError(ValueError):
    """Raised when a spool payload attempts to persist authority material."""


def canonical_json(value: JsonObject) -> bytes:
    """Return deterministic strict JSON bytes."""

    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("payload must contain only finite JSON values") from error
    return encoded.encode("utf-8")


def digest_json(value: JsonObject) -> str:
    """Digest JSON without exposing its content."""

    return hashlib.sha256(canonical_json(value)).hexdigest()


def reject_secret_material(value: JsonValue) -> None:
    """Reject fields that could carry reusable authority or resolved secrets."""

    _inspect(value, ())


def reason_digest(reason: str) -> str:
    """Return a stable non-content diagnostic for an operator reason."""

    return hashlib.sha256(reason.encode("utf-8")).hexdigest()


def spool_status(session: Session, origin_digest: str) -> SpoolStatus:
    """Build a redacted status from a verified session."""

    entries = (
        *(spool_entry(item, session) for item in session.commands()),
        *(corrupt_entry(item) for item in session.corrupt_records),
    )
    pending = tuple(item for item in entries if item.state is SpoolState.PENDING)
    accepted = tuple(item for item in entries if item.state is SpoolState.ACCEPTED_ARCHIVE)
    quarantined = tuple(item for item in entries if item.state is SpoolState.QUARANTINE)
    reasons = tuple(sorted({item.reason_code for item in quarantined if item.reason_code}))
    if session.torn_evidence:
        reasons = tuple(sorted({*reasons, "torn_write"}))
    health: Literal["healthy", "degraded"] = (
        "degraded" if quarantined or session.torn_evidence else "healthy"
    )
    return SpoolStatus(
        origin_digest=origin_digest,
        health=health,
        pending_count=len(pending),
        accepted_count=len(accepted),
        quarantine_count=len(quarantined) + session.torn_evidence,
        pending_bytes=sum(item.bytes for item in pending),
        quarantine_bytes=sum(item.bytes for item in quarantined),
        oldest_pending_seconds=_oldest_age(pending),
        last_accepted_sequence=max(
            (item.sequence for item in accepted if item.sequence is not None),
            default=None,
        ),
        keyring_available=True,
        chain_status="degraded" if session.corrupt_records else "healthy",
        reason_codes=reasons,
    )


def spool_entry(record: RecoveredRecord, session: Session) -> SpoolEntry:
    """Expose identity/state while keeping content encrypted and private."""

    payload = record.opened.payload
    state = {
        "pending": SpoolState.PENDING,
        "accepted": SpoolState.ACCEPTED_ARCHIVE,
        "quarantine": SpoolState.QUARANTINE,
    }[record.stored.directory]
    reason_code, server_refusal = _quarantine_outcome(session, record)
    return SpoolEntry(
        sequence=record.stored.sequence,
        command_id=UUID(_string_field(payload, "command_id")),
        operation_id=_string_field(payload, "operation_id"),
        state=state,
        enqueued_at=_parse_utc(_string_field(payload, "enqueued_at")),
        expires_at=_parse_utc(_string_field(payload, "expires_at")),
        bytes=record.stored.size,
        reason_code=reason_code,
        server_refusal=server_refusal,
    )


def corrupt_entry(record: CorruptRecord) -> SpoolEntry:
    """Expose bounded exact ciphertext evidence without trusting plaintext."""

    return SpoolEntry(
        sequence=record.stored.sequence,
        command_id=None,
        operation_id=None,
        state=SpoolState.QUARANTINE,
        enqueued_at=None,
        expires_at=None,
        bytes=record.stored.size,
        reason_code="corrupt_record",
        artifact_digest=record.artifact_digest,
    )


def unknown_status(
    origin_digest: str,
    reason_code: str,
    *,
    keyring_available: bool,
) -> SpoolStatus:
    """Return no guessed counts when encrypted state cannot be verified."""

    return SpoolStatus(
        origin_digest=origin_digest,
        health="state_unknown",
        pending_count=None,
        accepted_count=None,
        quarantine_count=None,
        pending_bytes=None,
        quarantine_bytes=None,
        oldest_pending_seconds=None,
        last_accepted_sequence=None,
        keyring_available=keyring_available,
        chain_status="state_unknown",
        reason_codes=(reason_code,),
    )


def doctor_failure(
    state: Literal["degraded", "state_unknown"],
    finding: str,
) -> SpoolDoctorReport:
    """Return one stable non-content doctor finding."""

    return SpoolDoctorReport(
        healthy=False,
        state=state,
        checks=(),
        findings=(finding,),
    )


def torn_entry(count: int) -> SpoolEntry:
    """Represent uncommitted encrypted temp evidence without exposing bytes."""

    return SpoolEntry(
        sequence=None,
        command_id=None,
        operation_id=None,
        state=SpoolState.QUARANTINE,
        enqueued_at=None,
        expires_at=None,
        bytes=count,
        reason_code="torn_write",
    )


def discarded_entry(sequence: int) -> SpoolEntry:
    """Represent the just-completed explicit discard result."""

    return SpoolEntry(
        sequence=sequence,
        command_id=None,
        operation_id=None,
        state=SpoolState.QUARANTINE,
        enqueued_at=None,
        expires_at=None,
        bytes=0,
        reason_code="discarded",
    )


def entry_order(entry: SpoolEntry) -> tuple[int, str]:
    """Stable ordering for bounded diagnostic output."""

    return (entry.sequence or 0, entry.reason_code or "")


def _inspect(value: JsonValue, path: tuple[str, ...]) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _FIELD_NORMALIZER.sub("_", raw_key.casefold()).strip("_")
            if key in _FORBIDDEN_FIELDS:
                raise SecretMaterialError("spool payload contains forbidden authority material")
            _inspect(child, (*path, key))
        return
    if isinstance(value, Sequence) and not isinstance(value, str):
        for child in value:
            _inspect(child, path)


def _quarantine_outcome(
    session: Session,
    command: RecoveredRecord,
) -> tuple[str | None, ServerRefusal | None]:
    outcomes: list[tuple[str, ServerRefusal | None]] = []
    for record in session.records:
        if record.opened.header.record_type != "quarantine_receipt":
            continue
        payload = record.opened.payload
        if payload.get("command_sequence") == command.stored.sequence:
            outcomes.append(
                (_string_field(payload, "reason_code"), _server_refusal(payload.get("refusal")))
            )
    return outcomes[-1] if outcomes else (None, None)


def _server_refusal(value: JsonValue) -> ServerRefusal | None:
    return ServerRefusal.model_validate(value) if isinstance(value, Mapping) else None


def _oldest_age(entries: tuple[SpoolEntry, ...]) -> float | None:
    timestamps = tuple(item.enqueued_at for item in entries if item.enqueued_at is not None)
    if not timestamps:
        return None
    return max(0.0, (datetime.now(UTC) - min(timestamps)).total_seconds())


def _string_field(payload: JsonObject, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise TypeError("verified spool identity field is not a string")
    return value


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("verified spool timestamp is not canonical UTC")
    return datetime.fromisoformat(value).astimezone(UTC)
