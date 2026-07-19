"""Typed Record authority for canonical event envelopes and hashes."""

from __future__ import annotations

import hashlib
import json
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
    "TicketCreatedPayload",
    "canonical_event_bytes",
    "event_digest",
]


class EventKind(StrEnum):
    BOOTSTRAP_CREATED = "bootstrap.first_tenant_created"
    TICKET_CREATED = "ticket.created"
    CUSTODY_TRANSFERRED = "ticket.custody_transferred"


class EventOrigin(StrEnum):
    API = "api"
    BOOTSTRAP = "bootstrap"


_DIGEST_BYTES = 32


@dataclass(frozen=True, slots=True)
class BootstrapCreatedPayload:
    commander_id: UUID
    commander_vault_ref: str
    operator_credential_ref: str
    operator_id: UUID
    operator_vault_ref: str
    tenant_id: UUID
    tenant_slug: str

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

    def to_mapping(self) -> dict[str, object]:
        return {
            "from_custodian_id": str(self.from_custodian_id),
            "reason": self.reason,
            "to_custodian_id": str(self.to_custodian_id),
        }


type EventPayload = BootstrapCreatedPayload | TicketCreatedPayload | CustodyTransferredPayload


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
        expected_payload = {
            EventKind.BOOTSTRAP_CREATED: BootstrapCreatedPayload,
            EventKind.TICKET_CREATED: TicketCreatedPayload,
            EventKind.CUSTODY_TRANSFERRED: CustodyTransferredPayload,
        }[self.kind]
        if not isinstance(self.payload, expected_payload):
            raise TypeError(f"{self.kind} requires {expected_payload.__name__}")
        if self.sequence < 1 or self.schema_version != 1:
            raise ValueError("event sequence and schema version are outside the authored contract")
        if len(self.prev_hash) != _DIGEST_BYTES or len(self.request_sha256) != _DIGEST_BYTES:
            raise ValueError("event digests must contain exactly 32 bytes")

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


def canonical_event_bytes(event: EventEnvelope | Mapping[str, object]) -> bytes:
    """Render the event-domain JSON subset with RFC 8785 ordering and encoding."""

    payload = event.to_mapping() if isinstance(event, EventEnvelope) else event
    return _canonical(payload).encode("utf-8")


def event_digest(event: EventEnvelope | Mapping[str, object]) -> bytes:
    return hashlib.sha256(canonical_event_bytes(event)).digest()


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
