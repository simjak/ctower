"""Typed Record authority for canonical event envelopes and hashes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

__all__ = [
    "BootstrapCreatedPayload",
    "CustodyTransferredPayload",
    "EventEnvelope",
    "EventKind",
    "EventOrigin",
    "ProofChangedPayload",
    "TicketCreatedPayload",
    "TicketEventPayload",
    "WorkflowChangedPayload",
    "canonical_event_bytes",
    "event_digest",
    "ticket_payload_from_mapping",
]


class EventKind(StrEnum):
    BOOTSTRAP_CREATED = "bootstrap.first_tenant_created"
    TICKET_CREATED = "ticket.created"
    CUSTODY_TRANSFERRED = "ticket.custody_transferred"
    PROOF_CHANGED = "proof.changed"
    WORKFLOW_CHANGED = "workflow.changed"


class EventOrigin(StrEnum):
    API = "api"
    BOOTSTRAP = "bootstrap"


_DIGEST_BYTES = 32
_DIGEST_TEXT = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_VERSIONED_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class BootstrapCreatedPayload:
    commander_id: UUID
    commander_vault_ref: str
    operator_credential_ref: str
    operator_id: UUID
    operator_vault_ref: str
    tenant_id: UUID
    tenant_slug: str

    def __post_init__(self) -> None:
        _require_uuid_fields(
            self,
            ("commander_id", "operator_id", "tenant_id"),
        )
        _bounded("commander_vault_ref", self.commander_vault_ref, minimum=1)
        _bounded("operator_credential_ref", self.operator_credential_ref, minimum=1)
        _bounded("operator_vault_ref", self.operator_vault_ref, minimum=1)
        _bounded("tenant_slug", self.tenant_slug, minimum=2, maximum=63)

    def to_mapping(self) -> dict[str, object]:
        return {
            "commander_id": str(self.commander_id),
            "commander_vault_ref": self.commander_vault_ref,
            "operator_credential_ref": self.operator_credential_ref,
            "operator_id": str(self.operator_id),
            "operator_vault_ref": self.operator_vault_ref,
            "tenant_id": str(self.tenant_id),
            "tenant_slug": self.tenant_slug,
        }


@dataclass(frozen=True, slots=True)
class TicketCreatedPayload:
    custodian_id: UUID
    priority: str
    source_kind: str
    source_ref: str
    title: str

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("custodian_id",))
        if self.priority not in {"P0", "P1", "P2"}:
            raise ValueError("priority is outside the authored event contract")
        _bounded("source_kind", self.source_kind, minimum=1, maximum=64)
        _bounded("source_ref", self.source_ref, minimum=1, maximum=256)
        _bounded("title", self.title, minimum=1, maximum=200)

    def to_mapping(self) -> dict[str, object]:
        return {
            "custodian_id": str(self.custodian_id),
            "priority": self.priority,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class CustodyTransferredPayload:
    from_custodian_id: UUID
    reason: str
    to_custodian_id: UUID

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("from_custodian_id", "to_custodian_id"))
        _bounded("reason", self.reason, minimum=1, maximum=500)

    def to_mapping(self) -> dict[str, object]:
        return {
            "from_custodian_id": str(self.from_custodian_id),
            "reason": self.reason,
            "to_custodian_id": str(self.to_custodian_id),
        }


@dataclass(frozen=True, slots=True)
class ProofChangedPayload:
    operation: str
    ticket_id: UUID
    proof_version: int
    candidate_digest: str
    invalidated_evidence_ids: tuple[UUID, ...]
    invalidated_verdict_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("ticket_id",))
        _require_uuid_tuple("invalidated_evidence_ids", self.invalidated_evidence_ids)
        _require_uuid_tuple("invalidated_verdict_ids", self.invalidated_verdict_ids)
        if self.operation not in {
            "freeze_criteria",
            "record_evidence",
            "record_verdict",
            "change_candidate",
        }:
            raise ValueError("proof operation is outside the authored event contract")
        if self.proof_version < 1:
            raise ValueError("proof version must be positive")
        if _DIGEST_TEXT.fullmatch(self.candidate_digest) is None:
            raise ValueError("candidate digest must be content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "invalidated_evidence_ids": [str(item) for item in self.invalidated_evidence_ids],
            "invalidated_verdict_ids": [str(item) for item in self.invalidated_verdict_ids],
            "operation": self.operation,
            "proof_version": self.proof_version,
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class WorkflowChangedPayload:
    operation: str
    ticket_id: UUID
    workflow_ref: str
    workflow_version: int
    stage: str
    lifecycle_facts: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("ticket_id",))
        if self.operation not in {"transition", "resolve_close"}:
            raise ValueError("workflow operation is outside the authored event contract")
        if self.workflow_version < 1:
            raise ValueError("workflow version must be positive")
        if _VERSIONED_REFERENCE.fullmatch(self.workflow_ref) is None:
            raise ValueError("workflow reference must be versioned")
        if _STABLE_KEY.fullmatch(self.stage) is None:
            raise ValueError("workflow stage must be stable")
        if self.lifecycle_facts not in {(), ("resolved", "closed")}:
            raise ValueError("workflow lifecycle facts must preserve terminal order")

    def to_mapping(self) -> dict[str, object]:
        return {
            "lifecycle_facts": list(self.lifecycle_facts),
            "operation": self.operation,
            "stage": self.stage,
            "ticket_id": str(self.ticket_id),
            "workflow_ref": self.workflow_ref,
            "workflow_version": self.workflow_version,
        }


type EventPayload = (
    BootstrapCreatedPayload
    | TicketCreatedPayload
    | CustodyTransferredPayload
    | ProofChangedPayload
    | WorkflowChangedPayload
)
type TicketEventPayload = TicketCreatedPayload | CustodyTransferredPayload


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    actor_principal_id: UUID
    aggregate_id: UUID
    causation_id: UUID | None
    client_command_id: UUID
    correlation_id: UUID
    event_id: UUID
    kind: EventKind
    origin: EventOrigin
    payload: EventPayload
    prev_hash: bytes
    request_sha256: bytes
    sequence: int
    server_time: datetime
    stream_id: str
    tenant_id: UUID
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_variant(self)
        _validate_envelope_values(self)
        _validate_event_identity(self)

    def to_mapping(self) -> dict[str, object]:
        return {
            "actor_principal_id": str(self.actor_principal_id),
            "aggregate_id": str(self.aggregate_id),
            "causation_id": str(self.causation_id) if self.causation_id is not None else None,
            "client_command_id": str(self.client_command_id),
            "correlation_id": str(self.correlation_id),
            "event_id": str(self.event_id),
            "kind": self.kind.value,
            "origin": self.origin.value,
            "payload": self.payload.to_mapping(),
            "prev_hash": f"sha256:{self.prev_hash.hex()}",
            "request_sha256": f"sha256:{self.request_sha256.hex()}",
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "server_time": _timestamp(self.server_time),
            "stream_id": self.stream_id,
            "tenant_id": str(self.tenant_id),
        }


def canonical_event_bytes(event: EventEnvelope) -> bytes:
    """Render the event-domain JSON subset with RFC 8785 ordering and encoding."""

    if not isinstance(event, EventEnvelope):
        raise TypeError("event hashing requires a validated EventEnvelope")
    return _canonical(event.to_mapping()).encode("utf-8")


def event_digest(event: EventEnvelope) -> bytes:
    return hashlib.sha256(canonical_event_bytes(event)).digest()


def ticket_payload_from_mapping(
    kind: EventKind, payload: Mapping[str, object]
) -> TicketEventPayload:
    """Rebuild one typed ticket payload at the persistence read boundary."""

    if kind is EventKind.TICKET_CREATED:
        _require_keys(
            payload,
            {"custodian_id", "priority", "source_kind", "source_ref", "title"},
        )
        return TicketCreatedPayload(
            custodian_id=_uuid(payload["custodian_id"], "custodian_id"),
            priority=_string(payload["priority"], "priority"),
            source_kind=_string(payload["source_kind"], "source_kind"),
            source_ref=_string(payload["source_ref"], "source_ref"),
            title=_string(payload["title"], "title"),
        )
    if kind is EventKind.CUSTODY_TRANSFERRED:
        _require_keys(payload, {"from_custodian_id", "reason", "to_custodian_id"})
        return CustodyTransferredPayload(
            from_custodian_id=_uuid(payload["from_custodian_id"], "from_custodian_id"),
            reason=_string(payload["reason"], "reason"),
            to_custodian_id=_uuid(payload["to_custodian_id"], "to_custodian_id"),
        )
    raise ValueError(f"{kind} is not a ticket timeline event")


_EVENT_VARIANTS: dict[EventKind, tuple[type[object], EventOrigin]] = {
    EventKind.BOOTSTRAP_CREATED: (BootstrapCreatedPayload, EventOrigin.BOOTSTRAP),
    EventKind.TICKET_CREATED: (TicketCreatedPayload, EventOrigin.API),
    EventKind.CUSTODY_TRANSFERRED: (CustodyTransferredPayload, EventOrigin.API),
    EventKind.PROOF_CHANGED: (ProofChangedPayload, EventOrigin.API),
    EventKind.WORKFLOW_CHANGED: (WorkflowChangedPayload, EventOrigin.API),
}


def _validate_variant(event: EventEnvelope) -> None:
    if not isinstance(event.kind, EventKind) or not isinstance(event.origin, EventOrigin):
        raise TypeError("event kind and origin must use authored enums")
    expected_payload, expected_origin = _EVENT_VARIANTS[event.kind]
    if not isinstance(event.payload, expected_payload):
        raise TypeError(f"{event.kind} requires {expected_payload.__name__}")
    if event.origin is not expected_origin:
        raise ValueError(f"{event.kind} requires origin {expected_origin}")


def _validate_envelope_values(event: EventEnvelope) -> None:
    _require_uuid_fields(
        event,
        (
            "actor_principal_id",
            "aggregate_id",
            "client_command_id",
            "correlation_id",
            "event_id",
            "tenant_id",
        ),
    )
    if event.causation_id is not None and not isinstance(event.causation_id, UUID):
        raise TypeError("causation_id must be a UUID or None")
    _validate_sequence(event)
    _validate_digest("prev_hash", event.prev_hash)
    _validate_digest("request_sha256", event.request_sha256)
    _validate_timestamp(event.server_time)


def _validate_sequence(event: EventEnvelope) -> None:
    if type(event.sequence) is not int or type(event.schema_version) is not int:
        raise TypeError("event sequence and schema version must be integers")
    if event.sequence < 1 or event.schema_version != 1:
        raise ValueError("event sequence and schema version are outside the authored contract")


def _validate_digest(label: str, value: object) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{label} must be bytes")
    if len(value) != _DIGEST_BYTES:
        raise ValueError(f"{label} must contain exactly 32 bytes")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("event timestamps must be datetimes")
    if value.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")


def _validate_event_identity(event: EventEnvelope) -> None:
    if event.stream_id != _stream_id(event.kind, event.aggregate_id):
        raise ValueError("event stream does not match its kind and aggregate identity")
    if isinstance(event.payload, BootstrapCreatedPayload) and (
        event.aggregate_id != event.tenant_id or event.payload.tenant_id != event.tenant_id
    ):
        raise ValueError("bootstrap aggregate, payload, and tenant identity must match")


def _stream_id(kind: EventKind, aggregate_id: UUID) -> str:
    if kind is EventKind.BOOTSTRAP_CREATED:
        return f"tenant:{aggregate_id}:bootstrap"
    if kind is EventKind.PROOF_CHANGED:
        return f"proof:{aggregate_id}"
    if kind is EventKind.WORKFLOW_CHANGED:
        return f"workflow:{aggregate_id}"
    return f"ticket:{aggregate_id}"


def _bounded(label: str, value: object, *, minimum: int, maximum: int | None = None) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise ValueError(f"{label} is outside the authored event contract")


def _require_uuid_fields(value: object, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(getattr(value, name), UUID):
            raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, UUID) for item in value):
        raise TypeError(f"{label} must be a UUID tuple")


def _require_keys(payload: Mapping[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ValueError("event payload fields do not match the authored variant")


def _uuid(value: object, label: str) -> UUID:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a UUID string")
    return UUID(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _canonical(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        items = sorted(value.items(), key=lambda item: item[0].encode("utf-16be"))
        return "{" + ",".join(f"{_canonical(key)}:{_canonical(item)}" for key, item in items) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    raise TypeError(f"unsupported canonical event value: {type(value).__name__}")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
