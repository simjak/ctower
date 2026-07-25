"""Degrade-only, contiguous fence observations without fence-arming authority."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ctower_client.models import (
    CtowerProjectFenceObservationRequest,
    CtowerProjectMigrationReceipt,
)
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._operation_result_sql import canonical
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import authority_connection, recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def report_observation(
    dsn: str,
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectMigrationReceipt | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _report(dsn, actor, request, command_id=command_id, now=now, telemetry=telemetry)
    )


def _report(
    dsn: str,
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectMigrationReceipt | RecordProblem:
    request_digest = hashlib.sha256(canonical(request)).digest()
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        replay = _replay(connection, actor, command_id, request_digest)
        if replay is not None:
            return replay
        if not _valid_observation(connection, actor, request):
            return _problem(command_id, "Fence observation is stale or may enable writes")
        return _commit_observation(
            connection,
            actor,
            request,
            command_id=command_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _valid_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
) -> bool:
    if request.status in {"detected", "unknown"} and not request.disables_writes:
        return False
    if request.status == "clear" and request.reason_code != "no_scoped_append":
        return False
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"migration-fence:{actor.tenant_id}:{request.registry_id}",),
    )
    previous = connection.execute(
        """
        SELECT sequence, observation_digest, status, disables_writes, observation_body
        FROM migration_fence_observations
        WHERE tenant_id = %s AND registry_id = %s AND registry_revision = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, request.registry_id, request.registry_revision),
    ).fetchone()
    if previous is None:
        return request.sequence == 1 and request.previous_observation_digest is None
    return _continues(previous, request)


def _continues(
    previous: dict[str, object],
    request: CtowerProjectFenceObservationRequest,
) -> bool:
    previous_body = cast(dict[str, object], previous["observation_body"])
    status_rank = {"clear": 0, "unknown": 1, "detected": 2}
    return (
        request.sequence == int(cast(int, previous["sequence"])) + 1
        and request.previous_observation_digest == _digest_text(previous["observation_digest"])
        and request.registry_digest == previous_body["registry_digest"]
        and request.from_offset == previous_body["to_offset"]
        and status_rank[request.status] >= status_rank[str(previous["status"])]
        and not (previous["disables_writes"] is True and not request.disables_writes)
    )


def _commit_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
    *,
    command_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> CtowerProjectMigrationReceipt:
    captured: list[CtowerProjectMigrationReceipt] = []

    def response(event_id: UUID, position: int) -> dict[str, object]:
        receipt = CtowerProjectMigrationReceipt(
            object_id=request.observation_id,
            revision=request.sequence,
            command_id=command_id,
            event_ids=(event_id,),
            record_position=position,
            semantic_digest=request.observation_digest,
            durability_state="durability_pending",
            accepted_position=None,
        )
        captured.append(receipt)
        return cast(dict[str, object], receipt.model_dump(mode="json"))

    event_id, _position = commit_event(
        connection,
        actor,
        aggregate_id=request.observation_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            "fence_observed",
            run_id=None,
            cutover_id=None,
            target_id=str(request.observation_id),
        ),
        request_digest=request_digest,
        sequence=1,
        stream_id=f"migration:{request.observation_id}",
        now=now,
        telemetry=telemetry,
        response=response,
    )
    _insert_observation(
        connection,
        actor,
        request,
        command_id=command_id,
        event_id=event_id,
        now=now,
    )
    return captured[0]


def _insert_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
    *,
    command_id: UUID,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_fence_observations (
            observation_id, tenant_id, registry_id, registry_revision, sequence,
            observation_digest, previous_observation_digest, status, disables_writes,
            observation_body, actor_principal_id, command_id, event_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.observation_id,
            actor.tenant_id,
            request.registry_id,
            request.registry_revision,
            request.sequence,
            _digest_bytes(request.observation_digest),
            _optional_digest(request.previous_observation_digest),
            request.status,
            request.disables_writes,
            Jsonb(request.model_dump(mode="json", by_alias=True)),
            actor.principal_id,
            command_id,
            event_id,
            now,
        ),
    )


def _replay(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
) -> CtowerProjectMigrationReceipt | RecordProblem | None:
    row = connection.execute(
        """
        SELECT request_sha256, response_body FROM command_results
        WHERE principal_id = %s AND client_command_id = %s
        """,
        (actor.principal_id, command_id),
    ).fetchone()
    if row is None:
        return None
    if bytes(cast(bytes, row["request_sha256"])) != request_digest:
        return _problem(command_id, "Fence observation replay changed")
    try:
        return CtowerProjectMigrationReceipt.model_validate_json(json.dumps(row["response_body"]))
    except ValidationError:
        return _problem(command_id, "Command identity was reused")


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _optional_digest(value: str | None) -> bytes | None:
    return _digest_bytes(value) if value is not None else None


def _digest_text(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"


def _problem(command_id: UUID, title: str) -> RecordProblem:
    return RecordProblem(
        "migration-fence-detected", title, 409, "Fence observation refused", command_id
    )
