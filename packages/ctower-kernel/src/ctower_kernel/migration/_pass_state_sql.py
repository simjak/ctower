"""Explicit append-only migration pass-state transitions."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID, uuid5

import psycopg

from ctower_client.models import CtowerProjectImportBatchRequest
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._operation_result_sql import migration_sequence
from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventKind
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["transition"]
_PASS_STATE_NAMESPACE = UUID("b9af2a17-b5e0-512f-a16d-d2b10b29b5fc")


def transition(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    state: str,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> None:
    command_id = uuid5(_PASS_STATE_NAMESPACE, f"{request.run_id}:{state}")
    request_digest = hashlib.sha256(f"{request.run_id}:{state}".encode()).digest()
    fact = connection.execute(
        """
        SELECT * FROM migration_import_run_facts
        WHERE run_id = %s ORDER BY fact_sequence DESC LIMIT 1
        """,
        (request.run_id,),
    ).fetchone()
    if fact is None:
        raise RuntimeError("run fact is unavailable")
    semantic = hashlib.sha256(
        bytes(cast(bytes, fact["semantic_digest"])) + request_digest + state.encode()
    ).digest()
    event_id, position = commit_event(
        connection,
        actor,
        aggregate_id=request.run_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            state,
            run_id=request.run_id,
            cutover_id=request.cutover_id,
            target_id=str(request.run_id),
        ),
        request_digest=request_digest,
        sequence=migration_sequence(connection, actor, request.run_id),
        stream_id=f"migration:{request.run_id}",
        now=now,
        telemetry=telemetry,
        response=lambda _event_id, accepted: {
            "run_id": str(request.run_id),
            "state": state,
            "record_watermark": accepted,
        },
        subjects=(("migration", request.run_id),),
    )
    _insert_fact(
        connection,
        actor,
        request,
        fact,
        state=state,
        semantic=semantic,
        event_id=event_id,
        position=position,
        command_id=command_id,
        now=now,
    )


def _insert_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportBatchRequest,
    fact: dict[str, object],
    *,
    state: str,
    semantic: bytes,
    event_id: UUID,
    position: int,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            _uuid7(now),
            request.run_id,
            int(cast(int, fact["fact_sequence"])) + 1,
            state,
            fact["export_equality_digest"],
            fact["alias_map_digest"],
            semantic,
            position,
            fact["projection_watermark"],
            event_id,
            actor.principal_id,
            command_id,
            now,
        ),
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
