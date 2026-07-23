"""Strict accepted-event validation before disposable projection folding."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from ctower_kernel.record.events import (
    EventKind,
    WorkflowChangedPayload,
    ticket_payload_from_mapping,
)
from ctower_kernel.record.work_events import WorkChangedPayload

__all__: tuple[str, ...] = ()

_ENVELOPE_FIELDS = frozenset(
    {
        "actor_principal_id",
        "aggregate_id",
        "causation_id",
        "client_command_id",
        "correlation_id",
        "event_id",
        "kind",
        "origin",
        "payload",
        "prev_hash",
        "request_sha256",
        "schema_version",
        "sequence",
        "server_time",
        "stream_id",
        "tenant_id",
    }
)


def validate_message(message: dict[str, object]) -> None:
    payload = message["outbox_payload"]
    if not isinstance(payload, Mapping) or set(payload) != _ENVELOPE_FIELDS:
        raise ValueError("schema-unknown: envelope fields")
    if payload["schema_version"] != 1:
        raise ValueError("schema-unknown: event version")
    try:
        kind = EventKind(str(payload["kind"]))
    except ValueError as error:
        raise ValueError("kind-unknown") from error
    if payload["actor_principal_id"] != str(message["actor_principal_id"]):
        raise ValueError("auth-mismatch")
    if dict(payload) != _expected_envelope(message):
        raise ValueError("digest-mismatch: outbox and event differ")
    digest = hashlib.sha256(_canonical(payload).encode()).digest()
    if digest != bytes(cast(bytes, message["event_hash"])):
        raise ValueError("digest-mismatch: event hash")
    _validate_payload(kind, cast(Mapping[str, object], payload["payload"]))


def safe_payload_bytes(value: object) -> bytes:
    try:
        return _canonical(value).encode()
    except TypeError:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()


def _validate_payload(kind: EventKind, payload: Mapping[str, object]) -> None:
    if kind in {EventKind.TICKET_CREATED, EventKind.CUSTODY_TRANSFERRED}:
        ticket_payload_from_mapping(kind, payload)
    elif kind is EventKind.WORK_CHANGED:
        WorkChangedPayload(
            operation=str(payload["operation"]),
            ticket_id=UUID(str(payload["ticket_id"])),
            work_version=int(cast(int, payload["work_version"])),
            data=cast(Mapping[str, object], payload["data"]),
        )
    elif kind is EventKind.WORKFLOW_CHANGED:
        WorkflowChangedPayload(
            operation=str(payload["operation"]),
            ticket_id=UUID(str(payload["ticket_id"])),
            workflow_ref=str(payload["workflow_ref"]),
            workflow_version=int(cast(int, payload["workflow_version"])),
            stage=str(payload["stage"]),
            lifecycle_facts=tuple(
                str(item) for item in cast(list[object], payload["lifecycle_facts"])
            ),
        )


def _expected_envelope(message: dict[str, object]) -> dict[str, object]:
    causation = cast(UUID | None, message["causation_id"])
    return {
        "actor_principal_id": str(message["actor_principal_id"]),
        "aggregate_id": str(message["aggregate_id"]),
        "causation_id": str(causation) if causation else None,
        "client_command_id": str(message["client_command_id"]),
        "correlation_id": str(message["correlation_id"]),
        "event_id": str(message["event_id"]),
        "kind": str(message["kind"]),
        "origin": str(message["origin"]),
        "payload": message["event_payload"],
        "prev_hash": "sha256:" + bytes(cast(bytes, message["prev_hash"])).hex(),
        "request_sha256": "sha256:" + bytes(cast(bytes, message["request_sha256"])).hex(),
        "schema_version": int(cast(int, message["schema_version"])),
        "sequence": int(cast(int, message["sequence"])),
        "server_time": _timestamp(cast(datetime, message["server_time"])),
        "stream_id": str(message["stream_id"]),
        "tenant_id": str(message["tenant_id"]),
    }


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
        items = sorted(value.items(), key=lambda item: str(item[0]).encode("utf-16be"))
        return "{" + ",".join(f"{_canonical(key)}:{_canonical(item)}" for key, item in items) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    raise TypeError(f"unsupported canonical event value: {type(value).__name__}")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
