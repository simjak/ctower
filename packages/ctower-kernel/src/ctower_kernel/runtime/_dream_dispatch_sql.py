"""Nightly dream effect reads and substrate-bound consumption."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.dream_dispatch_events import DreamDispatchConsumedPayload
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.transaction import (
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.runtime import (
    DreamDispatchConsumeCommand,
    DreamDispatchConsumption,
    DreamDispatchEffect,
    DreamDispatchReceipt,
    DreamDispatchSpec,
)

__all__: tuple[str, ...] = ()


def list_dream_dispatches(dsn: str, actor: Actor) -> tuple[DreamDispatchEffect, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute(
            """
            WITH authenticated_scope AS (
                SELECT principal.kind, seat.project_key
                FROM principals AS principal
                LEFT JOIN project_seats AS seat
                  ON seat.tenant_id = principal.tenant_id
                 AND seat.principal_id = principal.principal_id
                WHERE principal.tenant_id = %s AND principal.principal_id = %s
            )
            SELECT effect.*, consumption.executor_principal_id, consumption.lane_ref,
                consumption.crew_name, consumption.harness_ref, consumption.model_ref,
                consumption.model_family, consumption.reasoning_effort,
                consumption.model_tier, consumption.consumed_at, consumption.output_digest
            FROM runtime_dream_dispatch_effects AS effect
            LEFT JOIN runtime_dream_dispatch_consumptions AS consumption
              ON consumption.effect_id = effect.effect_id
             AND consumption.tenant_id = effect.tenant_id
            WHERE effect.tenant_id = %s
              AND (
                EXISTS (
                    SELECT 1 FROM authenticated_scope WHERE kind = 'operator'
                )
                OR (
                    effect.scope_kind = 'project'
                    AND EXISTS (
                        SELECT 1 FROM authenticated_scope
                        WHERE project_key = effect.project_key
                    )
                )
              )
            ORDER BY effect.scheduled_for, effect.effect_id
            """,
            (actor.tenant_id, actor.principal_id, actor.tenant_id),
        ).fetchall()
    return tuple(_effect(row) for row in rows)


def consume_dream_dispatch(
    dsn: str, actor: Actor, command: DreamDispatchConsumeCommand
) -> DreamDispatchReceipt | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        request_digest = hashlib.sha256(_canonical_bytes(command.request_payload())).digest()
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt(existing)
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"dream-dispatch:{actor.tenant_id}:{command.effect_id}",),
        )
        effect = connection.execute(
            """
            SELECT * FROM runtime_dream_dispatch_effects
            WHERE tenant_id = %s AND effect_id = %s
            """,
            (actor.tenant_id, command.effect_id),
        ).fetchone()
        problem = _consumption_problem(connection, actor, command, effect)
        if problem is not None:
            transaction.refuse(
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                request_digest,
                problem,
                now=now,
            )
            return problem
        if effect is None:
            raise RuntimeError("dream dispatch disappeared after its refusal check")
        binding = connection.execute(
            """
            SELECT * FROM runtime_dream_lane_bindings
            WHERE tenant_id = %s AND principal_id = %s
            """,
            (actor.tenant_id, actor.principal_id),
        ).fetchone()
        if binding is None:
            raise RuntimeError("dream lane binding disappeared after its refusal check")
        return _commit_consumption(
            connection, transaction, actor, command, binding, request_digest, now
        )


def _commit_consumption(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: DreamDispatchConsumeCommand,
    binding: dict[str, object],
    request_digest: bytes,
    now: datetime,
) -> DreamDispatchReceipt:
    event_id = _uuid7(now)
    receipt = DreamDispatchReceipt(
        command.client_command_id, event_id, command.effect_id, command.output_digest
    )
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.effect_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=event_id,
        kind=EventKind.DREAM_DISPATCH_CONSUMED,
        origin=EventOrigin.API,
        payload=DreamDispatchConsumedPayload(
            command.effect_id,
            str(binding["lane_ref"]),
            str(binding["model_ref"]),
            command.output_digest,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"dream-dispatch:{command.effect_id}",
        tenant_id=actor.tenant_id,
    )
    transaction.commit_control(
        event,
        outbox_id=_uuid7(now),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="runtime.dream-dispatches",
    )
    connection.execute(
        """
        INSERT INTO runtime_dream_dispatch_consumptions (
            effect_id, tenant_id, event_id, executor_principal_id, lane_ref,
            crew_name, harness_ref, model_ref, model_family, reasoning_effort,
            model_tier, output_digest, consumed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.effect_id,
            actor.tenant_id,
            event_id,
            actor.principal_id,
            binding["lane_ref"],
            binding["crew_name"],
            binding["harness_ref"],
            binding["model_ref"],
            binding["model_family"],
            binding["reasoning_effort"],
            binding["model_tier"],
            _digest(command.output_digest),
            now,
        ),
    )
    return receipt


def _consumption_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: DreamDispatchConsumeCommand,
    effect: dict[str, object] | None,
) -> RecordProblem | None:
    if effect is None:
        return _problem(command, "dream-dispatch-unavailable", "Dream dispatch unavailable", 404)
    scope_refusal = _scope_refusal(connection, actor, command, effect)
    if scope_refusal is not None:
        return scope_refusal
    consumed = connection.execute(
        "SELECT 1 FROM runtime_dream_dispatch_consumptions WHERE effect_id = %s",
        (command.effect_id,),
    ).fetchone()
    if consumed is not None:
        return _problem(
            command, "dream-dispatch-already-consumed", "Dream dispatch already consumed"
        )
    binding = connection.execute(
        """
        SELECT * FROM runtime_dream_lane_bindings
        WHERE tenant_id = %s AND principal_id = %s
        """,
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    if binding is None:
        return _problem(command, "dream-dispatch-lane-unbound", "Dream lane is unbound", 403)
    return _binding_problem(command, effect, binding)


def _scope_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: DreamDispatchConsumeCommand,
    effect: dict[str, object],
) -> RecordProblem | None:
    scope_kind = str(effect["scope_kind"])
    if scope_kind == "fleet":
        return project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(),
            command_id=command.client_command_id,
            operator_only=True,
        )
    if scope_kind != "project" or effect["project_key"] is None:
        raise RuntimeError("dream dispatch carries an invalid persisted scope")
    return project_scope_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        project_keys=(str(effect["project_key"]),),
        command_id=command.client_command_id,
    )


def _binding_problem(
    command: DreamDispatchConsumeCommand,
    effect: dict[str, object],
    binding: dict[str, object],
) -> RecordProblem | None:
    if str(binding["model_family"]) in cast(list[str], effect["excluded_model_families"]):
        return _problem(
            command, "dream-dispatch-family-excluded", "Dream model family is excluded", 403
        )
    if binding["model_tier"] != effect["minimum_model_tier"]:
        return _problem(command, "dream-dispatch-tier-refused", "Dream model tier is refused", 403)
    selected = str(binding["model_ref"])
    effort = str(binding["reasoning_effort"])
    allowed = {
        str(effect["primary_model_ref"]): str(effect["primary_reasoning_effort"]),
        str(effect["fallback_model_ref"]): str(effect["fallback_reasoning_effort"]),
    }
    if selected not in allowed or allowed[selected] != effort:
        return _problem(
            command,
            "dream-dispatch-model-requirement-mismatch",
            "Dream model requirement does not match",
            403,
        )
    return None


def _effect(row: dict[str, object]) -> DreamDispatchEffect:
    consumption = None
    if row["executor_principal_id"] is not None:
        consumption = DreamDispatchConsumption(
            cast(UUID, row["executor_principal_id"]),
            str(row["lane_ref"]),
            str(row["crew_name"]),
            str(row["harness_ref"]),
            str(row["model_ref"]),
            str(row["model_family"]),
            str(row["reasoning_effort"]),
            str(row["model_tier"]),
            cast(datetime, row["consumed_at"]),
            "sha256:" + bytes(cast(bytes, row["output_digest"])).hex(),
        )
    spec = DreamDispatchSpec(
        str(row["scope_kind"]),
        str(row["project_key"]) if row["project_key"] is not None else None,
        str(row["skill_path"]),
        str(row["primary_model_ref"]),
        str(row["primary_reasoning_effort"]),
        str(row["fallback_model_ref"]),
        str(row["fallback_reasoning_effort"]),
        str(row["minimum_model_tier"]),
        tuple(cast(list[str], row["excluded_model_families"])),
    )
    return DreamDispatchEffect(
        cast(UUID, row["effect_id"]),
        cast(UUID, row["occurrence_id"]),
        cast(UUID, row["tenant_id"]),
        str(row["routine_ref"]),
        "sha256:" + bytes(cast(bytes, row["revision_digest"])).hex(),
        cast(datetime, row["scheduled_for"]),
        spec,
        cast(datetime, row["emitted_at"]),
        consumption,
    )


def _receipt(payload: dict[str, object]) -> DreamDispatchReceipt:
    return DreamDispatchReceipt(
        UUID(str(payload["command_id"])),
        UUID(str(payload["event_id"])),
        UUID(str(payload["effect_id"])),
        str(payload["output_digest"]),
    )


def _problem(
    command: DreamDispatchConsumeCommand, code: str, title: str, status: int = 409
) -> RecordProblem:
    return RecordProblem(code, title, status, title, command.client_command_id)


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = connection.execute("SELECT transaction_timestamp() AS value").fetchone()
    return cast(datetime, cast(dict[str, object], row)["value"])


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= secrets.randbits(12) << 64
    value |= 0b10 << 62
    value |= secrets.randbits(62)
    return UUID(int=value)
