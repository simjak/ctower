"""Canonical semantic command-root computation for durability comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()

_MAX_SAFE_INTEGER = (1 << 53) - 1


@dataclass(frozen=True, slots=True)
class CommandSnapshot:
    """Exact command identity and canonical root read from one Record copy."""

    tenant_id: UUID
    principal_id: UUID
    command_id: UUID
    request_digest: bytes
    root: bytes


def command_snapshot(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, command_id: UUID
) -> CommandSnapshot | RecordProblem:
    """Read and hash the one semantic result, its ordered events, and outbox identity."""

    rows = connection.execute(
        """
        SELECT tenant_id, principal_id, client_command_id, request_sha256,
            status_code, response_body, event_ids
        FROM command_results
        WHERE tenant_id = %s AND client_command_id = %s
        ORDER BY principal_id
        LIMIT 2
        """,
        (tenant_id, command_id),
    ).fetchall()
    if len(rows) != 1:
        return RecordProblem(
            "tenant-scope-denied",
            "The command is unavailable in the requested tenant scope.",
            404,
            "Command unavailable",
            command_id,
        )
    result = rows[0]
    principal_id = cast(UUID, result["principal_id"])
    event_ids = tuple(cast(list[UUID], result["event_ids"]))
    events = connection.execute(
        """
        SELECT event_id, event_hash, record_position
        FROM events
        WHERE tenant_id = %s AND event_id = ANY(%s)
        ORDER BY record_position, event_id
        """,
        (tenant_id, list(event_ids)),
    ).fetchall()
    outbox = connection.execute(
        """
        SELECT item.outbox_id, item.event_id, item.topic, item.payload, item.telemetry
        FROM outbox AS item
        JOIN events AS event ON event.event_id = item.event_id
        WHERE item.tenant_id = %s AND item.event_id = ANY(%s)
        ORDER BY event.record_position, item.outbox_id
        """,
        (tenant_id, list(event_ids)),
    ).fetchall()
    payload = _root_payload(
        tenant_id,
        principal_id,
        command_id,
        result,
        event_ids,
        events,
        outbox,
    )
    return CommandSnapshot(
        tenant_id,
        principal_id,
        command_id,
        bytes(cast(bytes, result["request_sha256"])),
        hashlib.sha256(_rfc8785_bytes(payload)).digest(),
    )


def digest(value: bytes) -> str:
    """Render one SHA-256 value in the contract's digest form."""

    return f"sha256:{value.hex()}"


def _root_payload(
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    result: dict[str, object],
    event_ids: tuple[UUID, ...],
    events: list[dict[str, object]],
    outbox: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "command": {
            "tenant_id": str(tenant_id),
            "principal_id": str(principal_id),
            "client_command_id": str(command_id),
            "request_sha256": digest(bytes(cast(bytes, result["request_sha256"]))),
        },
        "result": {
            "status_code": int(cast(int, result["status_code"])),
            "response_body": cast(dict[str, object], result["response_body"]),
            "event_ids": [str(item) for item in event_ids],
        },
        "events": [
            {
                "event_id": str(row["event_id"]),
                "event_hash": digest(bytes(cast(bytes, row["event_hash"]))),
                "record_position": int(cast(int, row["record_position"])),
            }
            for row in events
        ],
        "outbox": [
            {
                "outbox_id": str(row["outbox_id"]),
                "event_id": str(row["event_id"]),
                "topic": str(row["topic"]),
                "payload_sha256": _mapping_digest(cast(dict[str, object], row["payload"])),
                "telemetry_sha256": _mapping_digest(cast(dict[str, object], row["telemetry"])),
            }
            for row in outbox
        ],
    }


def _mapping_digest(payload: dict[str, object]) -> str:
    return digest(hashlib.sha256(_rfc8785_bytes(payload)).digest())


def _rfc8785_bytes(value: object) -> bytes:
    """Canonicalize Ctower's integer/string JSON subset using RFC 8785 key ordering."""

    normalized = _canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ValueError("canonical Record roots require I-JSON safe integers")
        return value
    if isinstance(value, float):
        raise TypeError("canonical Record roots do not admit floating-point values")
    if isinstance(value, list | tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical Record roots require string object keys")
        return {
            key: _canonical_value(value[key])
            for key in sorted(value, key=lambda item: item.encode("utf-16-be"))
        }
    raise TypeError(f"unsupported canonical Record-root value: {type(value).__name__}")
