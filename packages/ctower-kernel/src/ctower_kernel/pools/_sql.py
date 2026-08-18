"""Record-owned SQL for credential-pool observation commands and limit reads."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.pools.drift import reconcile, resolve_registration
from ctower_kernel.pools.models import (
    PoolEntryState,
    PoolLimitsView,
    PoolObservationCommand,
    PoolObservationReceipt,
    PoolProfileLimits,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.pool_events import (
    PoolObservationEntryPayload,
    PoolObservationRecordedPayload,
)
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import RecordTransaction, authority_connection

__all__: tuple[str, ...] = ()


def record_observation(
    dsn: str, actor: Actor, command: PoolObservationCommand
) -> PoolObservationReceipt | RecordProblem:
    """Append one sweep, refusing before any byte if a credential value rode along."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        request_digest = _digest(command.request_payload())
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt_from_committed(actor, command, existing)
        problem = _credential_material_refusal(command)
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
        return _append_observation(connection, transaction, actor, command, request_digest, now)


def read_limits(dsn: str, actor: Actor, profile_key: str | None) -> PoolLimitsView | RecordProblem:
    """Return the latest sweep per profile as per-entry rows with their own clocks."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        observations = _latest_observations(connection, actor, profile_key)
        profiles = tuple(
            _profile_limits(connection, actor, observation) for observation in observations
        )
    return PoolLimitsView(profiles=profiles)


def _credential_material_refusal(command: PoolObservationCommand) -> RecordProblem | None:
    """Refuse a projected sweep that smuggled credential material through free text.

    The wire contract already has no field a token belongs in, and the feeder projects
    named fields rather than copying entry objects. This is the third defence, at the
    boundary that owns the byte: a label or status word carrying credential-shaped
    material refuses by class, before any event, row, or outbox entry commits.
    """

    texts = tuple(
        text
        for entry in command.entries
        for text in (entry.entry_label, entry.last_status_observed, entry.subscription_identity)
        if text is not None
    )
    return prohibited_data_refusal(texts, command_id=command.client_command_id)


def _append_observation(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: PoolObservationCommand,
    request_digest: bytes,
    now: datetime,
) -> PoolObservationReceipt:
    observation_id = uuid7(now)
    receipt = PoolObservationReceipt(
        tenant_id=actor.tenant_id,
        actor_principal_id=actor.principal_id,
        command_id=command.client_command_id,
        observation_id=observation_id,
        recorded_at=now,
        event_ids=(observation_id,),
    )
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=observation_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=command.client_command_id,
        event_id=observation_id,
        kind=EventKind.POOL_OBSERVATION_RECORDED,
        origin=EventOrigin.API,
        payload=PoolObservationRecordedPayload(
            observation_id=observation_id,
            harness_key=command.harness_key,
            profile_key=command.profile_key,
            observed_at=command.observed_at,
            entries=command.entries,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"pool-observation:{observation_id}",
        tenant_id=actor.tenant_id,
    )
    transaction.commit_control(
        event,
        outbox_id=uuid7(now),
        response_body=receipt.response_payload(),
        status_code=202,
        now=now,
        topic="pools.observations",
    )
    _insert_observation(connection, actor, command, observation_id, now)
    return receipt


def _insert_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: PoolObservationCommand,
    observation_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO pool_observations (
            observation_id, tenant_id, harness_key, profile_key, observed_at,
            event_id, actor_principal_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            observation_id,
            actor.tenant_id,
            command.harness_key,
            command.profile_key,
            command.observed_at,
            observation_id,
            actor.principal_id,
            now,
        ),
    )
    for entry in command.entries:
        connection.execute(
            """
            INSERT INTO pool_observation_entries (
                observation_id, tenant_id, provider_key, subscription_identity, entry_label,
                registration_state, auth_state, quota_state, quota_reset_at, reach_state,
                request_count, last_status_observed, secret_fingerprint, entry_ordinal
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                observation_id,
                actor.tenant_id,
                entry.provider_key,
                entry.subscription_identity,
                entry.entry_label,
                entry.registration_state,
                entry.auth_state,
                entry.quota_state,
                entry.quota_reset_at,
                entry.reach_state,
                entry.request_count,
                entry.last_status_observed,
                entry.secret_fingerprint,
                entry.entry_ordinal,
            ),
        )


def _latest_observations(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    profile_key: str | None,
) -> tuple[dict[str, object], ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT ON (harness_key, profile_key)
            observation_id, harness_key, profile_key, observed_at
        FROM pool_observations
        WHERE tenant_id = %s AND (%s::text IS NULL OR profile_key = %s)
        ORDER BY harness_key, profile_key, observed_at DESC, observation_id DESC
        """,
        (actor.tenant_id, profile_key, profile_key),
    ).fetchall()
    return tuple(rows)


def _profile_limits(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    observation: dict[str, object],
) -> PoolProfileLimits:
    observation_id = cast(UUID, observation["observation_id"])
    observed_at = cast(datetime, observation["observed_at"])
    harness_key = str(observation["harness_key"])
    rows = connection.execute(
        """
        SELECT provider_key, subscription_identity, entry_label, registration_state,
               auth_state, quota_state, quota_reset_at, reach_state, request_count,
               last_status_observed, secret_fingerprint, entry_ordinal
        FROM pool_observation_entries
        WHERE observation_id = %s AND tenant_id = %s
        ORDER BY entry_ordinal
        """,
        (observation_id, actor.tenant_id),
    ).fetchall()
    entries = resolve_registration(harness_key, tuple(_entry_payload(row) for row in rows))
    return PoolProfileLimits(
        harness_key=harness_key,
        profile_key=str(observation["profile_key"]),
        observed_at=observed_at,
        entries=tuple(PoolEntryState(entry=entry, observed_at=observed_at) for entry in entries),
        drift=reconcile(harness_key, entries),
    )


def _entry_payload(row: dict[str, object]) -> PoolObservationEntryPayload:
    return PoolObservationEntryPayload(
        entry_ordinal=int(cast(int, row["entry_ordinal"])),
        provider_key=str(row["provider_key"]),
        subscription_identity=_optional_text(row["subscription_identity"]),
        entry_label=_optional_text(row["entry_label"]),
        registration_state=str(row["registration_state"]),
        auth_state=str(row["auth_state"]),
        quota_state=str(row["quota_state"]),
        quota_reset_at=cast(datetime | None, row["quota_reset_at"]),
        reach_state=str(row["reach_state"]),
        request_count=int(cast(int, row["request_count"])),
        last_status_observed=_optional_text(row["last_status_observed"]),
        secret_fingerprint=_optional_text(row["secret_fingerprint"]),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _receipt_from_committed(
    actor: Actor, command: PoolObservationCommand, existing: dict[str, object]
) -> PoolObservationReceipt:
    body = cast(dict[str, object], existing["response_body"])
    return PoolObservationReceipt(
        tenant_id=actor.tenant_id,
        actor_principal_id=actor.principal_id,
        command_id=command.client_command_id,
        observation_id=UUID(str(body["observation_id"])),
        recorded_at=datetime.fromisoformat(str(body["recorded_at"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], body["event_ids"])),
    )


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = connection.execute("SELECT now() AS now").fetchone()
    if row is None:
        raise RuntimeError("the authority connection returned no clock")
    return cast(datetime, row["now"])


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
