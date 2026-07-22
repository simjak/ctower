"""Accepted-outbox delivery, validation, poison, cursor, and recovery mechanics."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from ctower_kernel.projections._board_sql import apply_message
from ctower_kernel.record.events import (
    EventKind,
    WorkflowChangedPayload,
    ticket_payload_from_mapping,
)
from ctower_kernel.record.work_events import WorkChangedPayload

__all__: tuple[str, ...] = ()
_CONSUMER = "board_projection"
_TOPIC = "record.events"
_TERMINAL_ATTEMPTS = 3
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


def consume_one(dsn: str, tenant_id: UUID) -> bool:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        _ensure_cursor(connection, tenant_id)
        cursor = _locked_cursor(connection, tenant_id)
        generation = int(cast(int, cursor["generation"]))
        message = _recover_or_next(connection, tenant_id, cursor)
        if message is None:
            if cursor["blocked_outbox_id"] is None:
                source = _source_watermark(connection, tenant_id)
                position = int(cast(int, cursor["acceptance_position"]))
                _advance(connection, tenant_id, position, source)
            return False
        if message.get("recovery_action") == "tombstone":
            _tombstone(connection, tenant_id, message)
            return True
        attempt = _attempt_number(
            connection, tenant_id, cast(UUID, message["outbox_id"]), generation
        )
        try:
            _validate_message(message)
        except (TypeError, ValueError) as error:
            _poison(connection, tenant_id, message, generation, attempt, str(error))
            return False
        try:
            with connection.transaction():
                apply_message(connection, tenant_id, message)
        except psycopg.Error as error:
            _retryable_failure(connection, tenant_id, message, generation, attempt, error)
            return False
        except (TypeError, ValueError) as error:
            _poison(connection, tenant_id, message, generation, attempt, str(error))
            return False
        _attempt(
            connection,
            tenant_id,
            message,
            generation,
            attempt,
            "delivered",
            "fold-committed",
        )
        _advance_if_position_drained(connection, tenant_id, message, cursor)
        return True


def read_source(dsn: str, tenant_id: UUID) -> int:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        return _source_watermark(connection, tenant_id)


def mark_requested_unknown(dsn: str, tenant_id: UUID, target: int, source: int) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        _ensure_cursor(connection, tenant_id)
        cursor = _locked_cursor(connection, tenant_id)
        _set_cursor(
            connection,
            tenant_id,
            int(cast(int, cursor["acceptance_position"])),
            "STATE_UNKNOWN",
            f"requested-watermark:{target}:source:{source}",
            cast(UUID | None, cursor["blocked_outbox_id"]),
        )


def reset_projection(dsn: str, tenant_id: UUID) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        connection.execute("DELETE FROM board_projection_rows WHERE tenant_id = %s", (tenant_id,))
        connection.execute(
            """
            INSERT INTO outbox_consumer_cursors (
                consumer_key, tenant_id, topic, generation, acceptance_position,
                health, detail, blocked_outbox_id, updated_at
            ) VALUES (%s, %s, %s, 1, 0, 'STATE_UNKNOWN', 'rebuild', NULL,
                transaction_timestamp())
            ON CONFLICT (consumer_key, tenant_id, topic) DO UPDATE SET
                generation = outbox_consumer_cursors.generation + 1,
                acceptance_position = 0, health = 'STATE_UNKNOWN', detail = 'rebuild',
                blocked_outbox_id = NULL, updated_at = EXCLUDED.updated_at
            """,
            (_CONSUMER, tenant_id, _TOPIC),
        )
        _projection_cursor(connection, tenant_id, 0, "STATE_UNKNOWN", "rebuild")


def _recover_or_next(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    cursor: dict[str, object],
) -> dict[str, object] | None:
    blocked = cast(UUID | None, cursor["blocked_outbox_id"])
    if blocked is None:
        return _next_message(
            connection,
            tenant_id,
            int(cast(int, cursor["acceptance_position"])),
            int(cast(int, cursor["generation"])),
        )
    message = _message_by_outbox(connection, tenant_id, blocked)
    if message is None:
        raise RuntimeError("blocked outbox message disappeared")
    recovery = connection.execute(
        """
        SELECT disposition.action, disposition.recorded_at
        FROM outbox_poison_dispositions AS disposition
        WHERE disposition.consumer_key = %s AND disposition.tenant_id = %s
          AND disposition.topic = %s AND disposition.outbox_id = %s
        ORDER BY disposition.recorded_at DESC, disposition.client_command_id DESC LIMIT 1
        """,
        (_CONSUMER, tenant_id, _TOPIC, blocked),
    ).fetchone()
    latest = connection.execute(
        """
        SELECT outcome, recorded_at FROM outbox_delivery_attempts
        WHERE consumer_key = %s AND tenant_id = %s AND topic = %s AND outbox_id = %s
          AND generation = %s
        ORDER BY attempt_number DESC LIMIT 1
        """,
        (_CONSUMER, tenant_id, _TOPIC, blocked, cursor["generation"]),
    ).fetchone()
    if latest is not None and str(latest["outcome"]) in {"delivered", "tombstoned"}:
        return message
    if recovery is None or (
        latest is not None
        and cast(datetime, recovery["recorded_at"]) <= cast(datetime, latest["recorded_at"])
    ):
        return None
    message["recovery_action"] = str(recovery["action"])
    return message


def _next_message(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    cursor: int,
    generation: int,
) -> dict[str, object] | None:
    query = sql.SQL(
        "{} AND confirmation.acceptance_position > %s"
        " AND NOT EXISTS ("
        " SELECT 1 FROM outbox_delivery_attempts AS delivered"
        " WHERE delivered.consumer_key = %s"
        " AND delivered.tenant_id = confirmation.tenant_id"
        " AND delivered.topic = outbox.topic"
        " AND delivered.outbox_id = outbox.outbox_id"
        " AND delivered.generation = %s"
        " AND delivered.outcome IN ('delivered', 'tombstoned'))"
        " ORDER BY confirmation.acceptance_position, event.record_position LIMIT 1"
    ).format(sql.SQL(_MESSAGE_SQL))
    return connection.execute(
        query,
        (tenant_id, _TOPIC, cursor, _CONSUMER, generation),
    ).fetchone()


def _advance_if_position_drained(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    cursor: dict[str, object],
) -> None:
    position = int(cast(int, message["acceptance_position"]))
    next_message = _next_message(
        connection,
        tenant_id,
        int(cast(int, cursor["acceptance_position"])),
        int(cast(int, cursor["generation"])),
    )
    if next_message is not None and int(cast(int, next_message["acceptance_position"])) == position:
        _set_cursor(
            connection,
            tenant_id,
            int(cast(int, cursor["acceptance_position"])),
            "STATE_UNKNOWN",
            "draining-accepted-batch",
            None,
        )
        return
    _advance(connection, tenant_id, position, _source_watermark(connection, tenant_id))


def _message_by_outbox(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, outbox_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        _MESSAGE_SQL + " AND outbox.outbox_id = %s LIMIT 1",
        (tenant_id, _TOPIC, outbox_id),
    ).fetchone()


_MESSAGE_SQL = """
    SELECT outbox.outbox_id, outbox.payload AS outbox_payload,
        confirmation.acceptance_position,
        event.event_id, event.tenant_id, event.stream_id, event.aggregate_id,
        event.sequence, event.kind, event.schema_version, event.actor_principal_id,
        event.client_command_id, event.request_sha256, event.correlation_id,
        event.causation_id, event.origin, event.server_time,
        event.payload AS event_payload, event.prev_hash, event.event_hash,
        COALESCE(start.activity_class, transition.activity_class) AS workflow_activity_class
    FROM durability_acceptance_confirmations AS confirmation
    JOIN events AS event
      ON event.tenant_id = confirmation.tenant_id
     AND event.actor_principal_id = confirmation.principal_id
     AND event.client_command_id = confirmation.client_command_id
    JOIN outbox ON outbox.event_id = event.event_id AND outbox.tenant_id = event.tenant_id
    JOIN principals AS actor
      ON actor.principal_id = event.actor_principal_id AND actor.tenant_id = event.tenant_id
    LEFT JOIN workflow_start_facts AS start ON start.event_id = event.event_id
    LEFT JOIN LATERAL (
        SELECT fact.activity_class FROM workflow_transition_facts AS fact
        WHERE fact.tenant_id = event.tenant_id
          AND fact.workflow_run_id = event.aggregate_id
          AND fact.client_command_id = event.client_command_id
        ORDER BY fact.fact_sequence DESC LIMIT 1
    ) AS transition ON true
    WHERE confirmation.tenant_id = %s AND outbox.topic = %s
"""


def _validate_message(message: dict[str, object]) -> None:
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


def _retryable_failure(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    generation: int,
    attempt: int,
    error: psycopg.Error,
) -> None:
    reason = f"fold-failure:{error.sqlstate or 'database-error'}"
    if attempt >= _TERMINAL_ATTEMPTS:
        _poison(connection, tenant_id, message, generation, attempt, reason)
    else:
        _attempt(
            connection,
            tenant_id,
            message,
            generation,
            attempt,
            "retryable_failure",
            reason,
        )
        cursor = _locked_cursor(connection, tenant_id)
        _set_cursor(
            connection,
            tenant_id,
            int(cast(int, cursor["acceptance_position"])),
            "STATE_UNKNOWN",
            reason,
            None,
        )


def _poison(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    generation: int,
    attempt: int,
    reason: str,
) -> None:
    _attempt(connection, tenant_id, message, generation, attempt, "poisoned", reason)
    outbox_id = cast(UUID, message["outbox_id"])
    payload_digest = hashlib.sha256(_safe_payload_bytes(message["outbox_payload"])).digest()
    connection.execute(
        """
        INSERT INTO outbox_poison (
            poison_id, consumer_key, tenant_id, topic, outbox_id,
            acceptance_position, payload_digest, attempt_count, reason, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, transaction_timestamp())
        ON CONFLICT (consumer_key, tenant_id, topic, outbox_id) DO NOTHING
        """,
        (
            _uuid7(),
            _CONSUMER,
            tenant_id,
            _TOPIC,
            outbox_id,
            message["acceptance_position"],
            payload_digest,
            attempt,
            reason,
        ),
    )
    connection.execute(
        """
        INSERT INTO attention_findings (
            finding_id, tenant_id, finding_key, kind, severity, summary,
            source_ref, recorded_at
        ) VALUES (%s, %s, %s, 'outbox_poison', 'critical', %s, %s,
            transaction_timestamp()) ON CONFLICT (tenant_id, finding_key) DO NOTHING
        """,
        (_uuid7(), tenant_id, f"outbox-poison:{outbox_id}", reason, f"outbox:{outbox_id}"),
    )
    cursor = _locked_cursor(connection, tenant_id)
    _set_cursor(
        connection,
        tenant_id,
        int(cast(int, cursor["acceptance_position"])),
        "STATE_UNKNOWN",
        reason,
        outbox_id,
    )
    _write_health(connection, tenant_id, None, "STATE_UNKNOWN", reason)


def _tombstone(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
) -> None:
    cursor = _locked_cursor(connection, tenant_id)
    generation = int(cast(int, cursor["generation"]))
    attempt = _attempt_number(connection, tenant_id, cast(UUID, message["outbox_id"]), generation)
    _attempt(
        connection,
        tenant_id,
        message,
        generation,
        attempt,
        "tombstoned",
        "policy-tombstone",
    )
    _advance_if_position_drained(connection, tenant_id, message, cursor)


def _attempt(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    generation: int,
    attempt: int,
    outcome: str,
    reason: str,
) -> None:
    connection.execute(
        """
        INSERT INTO outbox_delivery_attempts (
            attempt_id, consumer_key, tenant_id, topic, outbox_id,
            generation, acceptance_position, attempt_number, outcome, reason, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            transaction_timestamp())
        """,
        (
            _uuid7(),
            _CONSUMER,
            tenant_id,
            _TOPIC,
            message["outbox_id"],
            generation,
            message["acceptance_position"],
            attempt,
            outcome,
            reason,
        ),
    )


def _attempt_number(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    outbox_id: UUID,
    generation: int,
) -> int:
    row = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT COALESCE(max(attempt_number), 0) + 1 AS value
            FROM outbox_delivery_attempts
            WHERE consumer_key = %s AND tenant_id = %s AND topic = %s AND outbox_id = %s
              AND generation = %s
            """,
            (_CONSUMER, tenant_id, _TOPIC, outbox_id, generation),
        ).fetchone(),
    )
    return int(cast(int, row["value"]))


def _ensure_cursor(connection: psycopg.Connection[dict[str, object]], tenant_id: UUID) -> None:
    connection.execute(
        """
        INSERT INTO outbox_consumer_cursors (
            consumer_key, tenant_id, topic, generation, acceptance_position,
            health, detail, blocked_outbox_id, updated_at
        ) VALUES (%s, %s, %s, 1, 0, 'STATE_UNKNOWN', 'not-consumed', NULL,
            transaction_timestamp()) ON CONFLICT DO NOTHING
        """,
        (_CONSUMER, tenant_id, _TOPIC),
    )


def _locked_cursor(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> dict[str, object]:
    return cast(
        dict[str, object],
        connection.execute(
            """
            SELECT * FROM outbox_consumer_cursors
            WHERE consumer_key = %s AND tenant_id = %s AND topic = %s FOR UPDATE
            """,
            (_CONSUMER, tenant_id, _TOPIC),
        ).fetchone(),
    )


def _advance(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    position: int,
    source: int,
) -> None:
    health = "CURRENT" if position == source else "STATE_UNKNOWN"
    detail = "current" if health == "CURRENT" else "catching-up"
    _set_cursor(connection, tenant_id, position, health, detail, None)
    _projection_cursor(connection, tenant_id, position, health, detail)
    _write_health(
        connection,
        tenant_id,
        position,
        "HEALTHY" if health == "CURRENT" else "STATE_UNKNOWN",
        detail,
    )


def _set_cursor(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    position: int,
    health: str,
    detail: str,
    blocked: UUID | None,
) -> None:
    connection.execute(
        """
        UPDATE outbox_consumer_cursors SET acceptance_position = %s,
            health = %s, detail = %s, blocked_outbox_id = %s,
            updated_at = transaction_timestamp()
        WHERE consumer_key = %s AND tenant_id = %s AND topic = %s
        """,
        (position, health, detail[:500], blocked, _CONSUMER, tenant_id, _TOPIC),
    )


def _projection_cursor(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    position: int,
    health: str,
    detail: str,
) -> None:
    connection.execute(
        """
        INSERT INTO projection_cursors (
            tenant_id, projection_watermark, health, detail, updated_at
        ) VALUES (%s, %s, %s, %s, transaction_timestamp())
        ON CONFLICT (tenant_id) DO UPDATE SET
            projection_watermark = EXCLUDED.projection_watermark,
            health = EXCLUDED.health, detail = EXCLUDED.detail,
            updated_at = EXCLUDED.updated_at
        """,
        (tenant_id, position, health, detail[:500]),
    )


def _write_health(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    watermark: int | None,
    status: str,
    reason: str,
) -> None:
    connection.cursor().executemany(
        """
        INSERT INTO health_watermarks (
            tenant_id, contributor, status, watermark, threshold_seconds,
            observed_at, owner, reason
        ) VALUES (%s, %s, %s, %s, 60, transaction_timestamp(), %s, %s)
        ON CONFLICT (tenant_id, contributor) DO UPDATE SET
            status = EXCLUDED.status, watermark = EXCLUDED.watermark,
            threshold_seconds = EXCLUDED.threshold_seconds,
            observed_at = EXCLUDED.observed_at, owner = EXCLUDED.owner,
            reason = EXCLUDED.reason
        """,
        (
            (tenant_id, "outbox", status, watermark, "record", reason[:500]),
            (tenant_id, "projection", status, watermark, "projections", reason[:500]),
        ),
    )


def _source_watermark(connection: psycopg.Connection[dict[str, object]], tenant_id: UUID) -> int:
    row = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT COALESCE(max(confirmation.acceptance_position), 0) AS value
            FROM durability_acceptance_confirmations AS confirmation
            JOIN events AS event
              ON event.tenant_id = confirmation.tenant_id
             AND event.actor_principal_id = confirmation.principal_id
             AND event.client_command_id = confirmation.client_command_id
            JOIN outbox ON outbox.event_id = event.event_id AND outbox.tenant_id = event.tenant_id
            WHERE confirmation.tenant_id = %s AND outbox.topic = %s
            """,
            (tenant_id, _TOPIC),
        ).fetchone(),
    )
    return int(cast(int, row["value"]))


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


def _safe_payload_bytes(value: object) -> bytes:
    try:
        return _canonical(value).encode()
    except TypeError:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _uuid7() -> UUID:
    now = datetime.now(UTC)
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
