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
    InboundEventPromotedPayload,
    InboundEventRecordedPayload,
    WorkflowChangedPayload,
    ticket_payload_from_mapping,
)
from ctower_kernel.record.inbox_events import (
    InboxMessageAppendedPayload,
    InboxParticipant,
    InboxThreadOpenedPayload,
    InboxThreadPromotedToTicketPayload,
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


def validate_message(
    message: dict[str, object],
    *,
    legacy_project_key: str | None = None,
) -> None:
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
    _validate_payload(
        kind,
        cast(Mapping[str, object], payload["payload"]),
        legacy_project_key=legacy_project_key,
    )


def safe_payload_bytes(value: object) -> bytes:
    try:
        return _canonical(value).encode()
    except TypeError:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()


def _validate_payload(
    kind: EventKind,
    payload: Mapping[str, object],
    *,
    legacy_project_key: str | None,
) -> None:
    if kind in {EventKind.TICKET_CREATED, EventKind.CUSTODY_TRANSFERRED}:
        ticket_payload_from_mapping(
            kind,
            payload,
            legacy_project_key=legacy_project_key,
        )
        return
    if kind is EventKind.WORK_CHANGED:
        WorkChangedPayload(
            operation=str(payload["operation"]),
            ticket_id=UUID(str(payload["ticket_id"])),
            work_version=int(cast(int, payload["work_version"])),
            data=cast(Mapping[str, object], payload["data"]),
        )
        return
    if kind is EventKind.WORKFLOW_CHANGED:
        _validate_workflow_payload(payload)
        return
    if kind is EventKind.INBOUND_EVENT_RECORDED:
        _validate_recorded_payload(payload)
        return
    if kind is EventKind.INBOUND_EVENT_PROMOTED:
        InboundEventPromotedPayload(
            inbound_event_id=UUID(str(payload["inbound_event_id"])),
            source_kind=str(payload["source_kind"]),
            source_ref=str(payload["source_ref"]),
            project_key=str(payload["project_key"]),
            intent=str(payload["intent"]),
            outcome=str(payload["outcome"]),
            ticket_id=UUID(str(payload["ticket_id"])),
        )
        return
    if kind in {
        EventKind.INBOX_THREAD_OPENED,
        EventKind.INBOX_MESSAGE_APPENDED,
        EventKind.INBOX_THREAD_PROMOTED_TO_TICKET,
    }:
        _validate_inbox_payload(kind, payload)


def _validate_inbox_payload(kind: EventKind, payload: Mapping[str, object]) -> None:
    if kind is EventKind.INBOX_THREAD_OPENED:
        InboxThreadOpenedPayload(
            _participant(cast(Mapping[str, object], payload["opener"])),
            _participant(cast(Mapping[str, object], payload["recipient"])),
            UUID(str(payload["thread_id"])),
        )
        return
    if kind is EventKind.INBOX_MESSAGE_APPENDED:
        InboxMessageAppendedPayload(
            UUID(str(payload["message_id"])),
            int(cast(int, payload["position"])),
            _participant(cast(Mapping[str, object], payload["recipient"])),
            _participant(cast(Mapping[str, object], payload["sender"])),
            str(payload["text"]),
            UUID(str(payload["thread_id"])),
        )
        return
    if kind is EventKind.INBOX_THREAD_PROMOTED_TO_TICKET:
        InboxThreadPromotedToTicketPayload(
            UUID(str(payload["thread_id"])), UUID(str(payload["ticket_id"]))
        )


def _participant(payload: Mapping[str, object]) -> InboxParticipant:
    return InboxParticipant(UUID(str(payload["principal_id"])), str(payload["seat_key"]))


def _validate_workflow_payload(payload: Mapping[str, object]) -> None:
    WorkflowChangedPayload(
        operation=str(payload["operation"]),
        ticket_id=UUID(str(payload["ticket_id"])),
        workflow_ref=str(payload["workflow_ref"]),
        workflow_version=int(cast(int, payload["workflow_version"])),
        stage=str(payload["stage"]),
        lifecycle_facts=tuple(str(item) for item in cast(list[object], payload["lifecycle_facts"])),
    )


def _validate_recorded_payload(payload: Mapping[str, object]) -> None:
    ticket_id = payload["ticket_id"]
    InboundEventRecordedPayload(
        inbound_event_id=UUID(str(payload["inbound_event_id"])),
        source_kind=str(payload["source_kind"]),
        source_ref=str(payload["source_ref"]),
        project_key=str(payload["project_key"]),
        position=int(cast(int, payload["position"])),
        intent=str(payload["intent"]),
        taint=str(payload["taint"]),
        outcome=str(payload["outcome"]),
        content_digest=str(payload["content_digest"]),
        ticket_id=UUID(str(ticket_id)) if ticket_id is not None else None,
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
