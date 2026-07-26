"""Degrade-only, contiguous fence observations without fence-arming authority."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import psycopg
import rfc8785
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ctower_client.models import (
    CtowerProjectFenceObservationRequest,
    CtowerProjectMigrationReceipt,
    DurabilityState,
    MigrationFenceFileIdentity,
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
        if not _valid_observation(connection, actor, request, now=now):
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
    *,
    now: datetime,
) -> bool:
    del now
    if not _request_is_safe(request):
        return False
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"migration-fence:{actor.tenant_id}:{request.registry_id}",),
    )
    binding = _registry_binding(connection, actor, request)
    server_clock = connection.execute("SELECT transaction_timestamp() AS value").fetchone()
    if not _binding_is_timely(binding, server_clock, request):
        return False
    previous = _latest_observation(connection, actor, request)
    if previous is None:
        return _first(cast(dict[str, object], binding), request)
    return _continues(cast(dict[str, object], binding), previous, request)


def _request_is_safe(request: CtowerProjectFenceObservationRequest) -> bool:
    body = request.model_dump(mode="json", by_alias=True)
    claimed = body.pop("observation_digest")
    recomputed = f"sha256:{hashlib.sha256(rfc8785.dumps(body)).hexdigest()}"
    invalid_claim = claimed != recomputed
    unsafe_degradation = request.status in {"detected", "unknown"} and not request.disables_writes
    invalid_clear = request.status == "clear" and request.reason_code != "no_scoped_append"
    return not (
        invalid_claim
        or unsafe_degradation
        or invalid_clear
        or request.to_offset < request.from_offset
    )


def _registry_binding(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT registry.source_pointer_digest, registry.source_pointer_device,
            registry.source_pointer_inode, registry.source_pointer_offset,
            registry.source_pointer_scoped_digest,
            registry.max_observation_age_seconds,
            registry.max_future_clock_skew_seconds
        FROM migration_fence_observer_bindings AS binding
        JOIN migration_fence_registries AS registry ON registry.run_id = binding.run_id
        JOIN principal_credentials AS credential
          ON credential.principal_id = binding.principal_id
         AND credential.tenant_id = binding.tenant_id
         AND credential.credential_digest = binding.credential_digest
        WHERE binding.run_id = %s AND binding.tenant_id = %s
          AND binding.cutover_id = %s
          AND binding.project_key = %s AND binding.registry_id = %s
          AND binding.registry_revision = %s
          AND binding.registry_digest = %s AND binding.principal_id = %s
          AND credential.revoked_at IS NULL
        """,
        (
            request.run_id,
            actor.tenant_id,
            request.cutover_id,
            request.project_key,
            request.registry_id,
            request.registry_revision,
            _digest_bytes(request.registry_digest),
            actor.principal_id,
        ),
    ).fetchone()


def _binding_is_timely(
    binding: dict[str, object] | None,
    server_clock: dict[str, object] | None,
    request: CtowerProjectFenceObservationRequest,
) -> bool:
    if binding is None or server_clock is None:
        return False
    value = server_clock["value"]
    return isinstance(value, datetime) and _timely(binding, request, value)


def _latest_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectFenceObservationRequest,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT sequence, observation_digest, status, disables_writes, observation_body
        FROM migration_fence_observations
        WHERE tenant_id = %s AND registry_id = %s AND registry_revision = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, request.registry_id, request.registry_revision),
    ).fetchone()


def _timely(
    registry: dict[str, object],
    request: CtowerProjectFenceObservationRequest,
    now: datetime,
) -> bool:
    age = registry["max_observation_age_seconds"]
    skew = registry["max_future_clock_skew_seconds"]
    if not isinstance(age, int) or not isinstance(skew, int):
        return False
    return now - timedelta(seconds=age) <= request.observed_at <= now + timedelta(seconds=skew)


def _first(
    registry: dict[str, object],
    request: CtowerProjectFenceObservationRequest,
) -> bool:
    identity = request.file_identity
    return (
        request.sequence == 1
        and request.previous_observation_digest is None
        and request.source_pointer_digest == _digest_text(registry["source_pointer_digest"])
        and request.from_offset == int(cast(int, registry["source_pointer_offset"]))
        and identity.device == int(cast(int, registry["source_pointer_device"]))
        and identity.inode == int(cast(int, registry["source_pointer_inode"]))
        and identity.scoped_rows_digest == _digest_text(registry["source_pointer_scoped_digest"])
    )


def _continues(
    registry: dict[str, object],
    previous: dict[str, object],
    request: CtowerProjectFenceObservationRequest,
) -> bool:
    previous_body = cast(dict[str, object], previous["observation_body"])
    previous_identity = cast(dict[str, object], previous_body["file_identity"])
    current_identity = request.file_identity
    status_rank = {"clear": 0, "unknown": 1, "detected": 2}
    return (
        _chain_continues(registry, previous, previous_body, request)
        and _identity_continues(previous_identity, current_identity)
        and status_rank[request.status] >= status_rank[str(previous["status"])]
        and not (previous["disables_writes"] is True and not request.disables_writes)
    )


def _chain_continues(
    registry: dict[str, object],
    previous: dict[str, object],
    previous_body: dict[str, object],
    request: CtowerProjectFenceObservationRequest,
) -> bool:
    return (
        request.sequence == int(cast(int, previous["sequence"])) + 1
        and request.previous_observation_digest == _digest_text(previous["observation_digest"])
        and request.registry_digest == previous_body["registry_digest"]
        and request.source_pointer_digest == previous_body["source_pointer_digest"]
        and request.source_pointer_digest == _digest_text(registry["source_pointer_digest"])
        and request.from_offset == previous_body["to_offset"]
        and request.to_offset >= request.from_offset
        and request.observed_at >= datetime.fromisoformat(str(previous_body["observed_at"]))
    )


def _identity_continues(
    previous_identity: dict[str, object],
    current_identity: MigrationFenceFileIdentity,
) -> bool:
    return (
        current_identity.device == previous_identity["device"]
        and current_identity.inode == previous_identity["inode"]
        and current_identity.scoped_rows_digest == previous_identity["scoped_rows_digest"]
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
            durability_state=DurabilityState.DURABILITY_PENDING,
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
            run_id=request.run_id,
            cutover_id=request.cutover_id,
            target_id=str(request.observation_id),
        ),
        request_digest=request_digest,
        sequence=1,
        stream_id=f"migration:{request.observation_id}",
        now=now,
        telemetry=telemetry,
        response=response,
        subjects=(("migration", request.run_id),),
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
