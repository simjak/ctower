"""PostgreSQL receipts for the one fixed synthetic operation."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    RoutineOccurrenceRecordedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.runtime import (
    FixedOperationAttempt,
    FixedOperationCompletion,
    FixedOperationJob,
    FixedOperationResult,
    RoutineRevision,
    SyntheticRun,
    SyntheticRunCommand,
    SyntheticRunReceipt,
    SyntheticRunState,
)
from ctower_kernel.runtime._routine_sql import _revision as _stored_revision

__all__: tuple[str, ...] = ()

_WORKFLOW_REF = "ctower.trust-spine-four-stage@1"
_CLAIM_SECONDS = 30
_MAX_ATTEMPTS = 8


def start_synthetic(
    dsn: str,
    tenant_id: UUID,
    principal_id: UUID,
    command: SyntheticRunCommand,
    revision: RoutineRevision,
) -> SyntheticRunReceipt | RecordProblem:
    if command.workflow_ref != _WORKFLOW_REF or revision.handler_kind != "synthetic_four_stage":
        raise ValueError("synthetic run is outside the fixed I1 operation")
    request_digest = hashlib.sha256(_canonical(command.request_payload())).digest()
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(principal_id, command.client_command_id, request_digest)
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt(existing)
        now = _database_now(connection)
        _ensure_revision(connection, revision, now)
        run_id, job_id, event_id, outbox_id = (
            _uuid7(now, command.client_command_id.bytes + label)
            for label in (b"run", b"job", b"event", b"outbox")
        )
        event = _event(
            tenant_id,
            principal_id,
            command.client_command_id,
            run_id,
            job_id,
            event_id,
            revision,
            request_digest,
            now,
        )
        receipt = SyntheticRunReceipt(
            command.client_command_id,
            (event_id,),
            run_id,
            job_id,
            command.workflow_ref,
        )
        transaction.commit_control(
            event,
            outbox_id=outbox_id,
            response_body=receipt.response_payload(),
            status_code=201,
            now=now,
            topic="runtime.occurrences",
            job_id=job_id,
        )
        _insert_run(connection, tenant_id, principal_id, command, revision, receipt, now)
        return receipt


def claim_synthetic(dsn: str, worker_ref: str) -> FixedOperationAttempt | None:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        row = connection.execute(
            """
            SELECT job.*
            FROM operation_jobs AS job
            JOIN routine_occurrences AS occurrence
              ON occurrence.tenant_id = job.tenant_id
             AND occurrence.occurrence_id = job.occurrence_id
            JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = occurrence.tenant_id
             AND confirmation.principal_id = occurrence.actor_principal_id
             AND confirmation.client_command_id = occurrence.client_command_id
            WHERE job.operation = 'synthetic_four_stage'
              AND NOT EXISTS (
                  SELECT 1 FROM fixed_operation_results AS result
                  WHERE result.job_id = job.job_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM fixed_operation_attempts AS attempt
                  WHERE attempt.job_id = job.job_id AND attempt.claim_expires_at > %s
              )
              AND (
                  SELECT count(*) FROM fixed_operation_attempts AS attempt
                  WHERE attempt.job_id = job.job_id
              ) < %s
              AND pg_try_advisory_xact_lock(hashtextextended(job.job_id::text, 0))
            ORDER BY job.created_at, job.job_id
            LIMIT 1
            """,
            (now, _MAX_ATTEMPTS),
        ).fetchone()
        if row is None:
            return None
        attempt_number = _attempt_count(connection, cast(UUID, row["job_id"])) + 1
        attempt = FixedOperationAttempt(
            attempt_id=_uuid7(
                now,
                cast(UUID, row["job_id"]).bytes + attempt_number.to_bytes(2, "big") + b"attempt",
            ),
            job=_job(row),
            attempt_number=attempt_number,
            fencing_token=UUID(bytes=secrets.token_bytes(16), version=4),
            worker_ref=worker_ref,
            claimed_at=now,
            claim_expires_at=now + timedelta(seconds=_CLAIM_SECONDS),
        )
        connection.execute(
            """
            INSERT INTO fixed_operation_attempts (
                attempt_id, job_id, tenant_id, attempt_number, fencing_token,
                worker_ref, claimed_at, claim_expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                attempt.attempt_id,
                attempt.job.job_id,
                attempt.job.tenant_id,
                attempt.attempt_number,
                attempt.fencing_token,
                attempt.worker_ref,
                attempt.claimed_at,
                attempt.claim_expires_at,
            ),
        )
        return attempt


def complete_synthetic(
    dsn: str,
    attempt: FixedOperationAttempt,
    completion: FixedOperationCompletion,
) -> FixedOperationResult:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s::text, 0))",
            (attempt.job.job_id,),
        )
        existing = _load_result(connection, attempt.job.job_id)
        if existing is not None:
            return existing
        now = _database_now(connection)
        latest = connection.execute(
            """
            SELECT attempt_id, fencing_token, claim_expires_at
            FROM fixed_operation_attempts
            WHERE job_id = %s
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (attempt.job.job_id,),
        ).fetchone()
        identity = (attempt.attempt_id, attempt.fencing_token)
        if (
            latest is None
            or (latest["attempt_id"], latest["fencing_token"]) != identity
            or cast(datetime, latest["claim_expires_at"]) <= now
        ):
            raise RuntimeError("fixed synthetic completion lost its attempt fence")
        result = FixedOperationResult(
            result_id=_uuid7(now, attempt.job.job_id.bytes + b"result"),
            job_id=attempt.job.job_id,
            attempt_id=attempt.attempt_id,
            fencing_token=attempt.fencing_token,
            state=(
                SyntheticRunState.SUCCEEDED if completion.succeeded else SyntheticRunState.FAILED
            ),
            ticket_id=completion.ticket_id,
            lifecycle_facts=completion.lifecycle_facts,
            detail_code=completion.detail_code,
            recorded_at=now,
        )
        _insert_result(connection, attempt.job.tenant_id, result)
        return result


def synthetic_run(dsn: str, tenant_id: UUID, run_id: UUID) -> SyntheticRun | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        now = _database_now(connection)
        row = connection.execute(
            """
            SELECT occurrence.occurrence_id, job.job_id, job.created_at,
                result.result_id, result.outcome, result.ticket_id,
                result.lifecycle_facts, result.detail_code, result.recorded_at,
                count(attempt.attempt_id) AS attempt_count,
                max(attempt.claim_expires_at) AS latest_expiry
            FROM routine_occurrences AS occurrence
            JOIN operation_jobs AS job
              ON job.tenant_id = occurrence.tenant_id
             AND job.occurrence_id = occurrence.occurrence_id
            LEFT JOIN fixed_operation_attempts AS attempt ON attempt.job_id = job.job_id
            LEFT JOIN fixed_operation_results AS result ON result.job_id = job.job_id
            WHERE occurrence.tenant_id = %s AND occurrence.occurrence_id = %s
              AND job.operation = 'synthetic_four_stage'
            GROUP BY occurrence.occurrence_id, job.job_id, job.created_at,
                result.result_id, result.outcome, result.ticket_id,
                result.lifecycle_facts, result.detail_code, result.recorded_at
            """,
            (tenant_id, run_id),
        ).fetchone()
    if row is None:
        return None
    state = SyntheticRunState.PENDING
    if row["result_id"] is not None:
        state = SyntheticRunState(str(row["outcome"]))
    elif row["latest_expiry"] is not None and row["latest_expiry"] > now:
        state = SyntheticRunState.RUNNING
    return SyntheticRun(
        run_id=cast(UUID, row["occurrence_id"]),
        job_id=cast(UUID, row["job_id"]),
        workflow_ref=_WORKFLOW_REF,
        state=state,
        attempt_count=int(cast(int, row["attempt_count"])),
        ticket_id=cast(UUID | None, row["ticket_id"]),
        lifecycle_facts=tuple(cast(list[str] | None, row["lifecycle_facts"]) or ()),
        detail_code=cast(str | None, row["detail_code"]),
        created_at=cast(datetime, row["created_at"]),
        completed_at=cast(datetime | None, row["recorded_at"]),
    )


def _ensure_revision(
    connection: psycopg.Connection[dict[str, object]],
    revision: RoutineRevision,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO routine_revisions (
            revision_digest, routine_ref, schedule_kind, timezone, local_time,
            dst_policy, concurrency, catch_up, catch_up_cap, timeout_seconds,
            handler_kind, component_digests, registered_at
        ) VALUES (%s, %s, %s, %s, %s, 'wall_clock_once', %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (revision_digest) DO NOTHING
        """,
        (
            _digest(revision.revision_digest),
            revision.routine_ref,
            revision.schedule_kind.value,
            revision.timezone,
            revision.local_time,
            revision.concurrency.value,
            revision.catch_up.value,
            revision.catch_up_cap,
            revision.timeout_seconds,
            revision.handler_kind,
            [_digest(item) for item in revision.component_digests],
            now,
        ),
    )
    stored = connection.execute(
        "SELECT * FROM routine_revisions WHERE revision_digest = %s",
        (_digest(revision.revision_digest),),
    ).fetchone()
    if stored is None or _stored_revision(stored) != revision:
        raise ValueError("Routine revision digest conflicts with stored content")


def _event(
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    run_id: UUID,
    job_id: UUID,
    event_id: UUID,
    revision: RoutineRevision,
    request_digest: bytes,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=principal_id,
        aggregate_id=run_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_OCCURRENCE_RECORDED,
        origin=EventOrigin.CONTROL_WORKER,
        payload=RoutineOccurrenceRecordedPayload(
            occurrence_id=run_id,
            routine_ref=revision.routine_ref,
            revision_digest=revision.revision_digest,
            scheduled_for=now,
            local_civil_time=now.replace(tzinfo=None).isoformat(),
            timezone="UTC",
            utc_offset_seconds=0,
            offset_decision="exact",
            outcome="queued",
            job_id=job_id,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"routine-occurrence:{run_id}",
        tenant_id=tenant_id,
    )


def _insert_run(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    principal_id: UUID,
    command: SyntheticRunCommand,
    revision: RoutineRevision,
    receipt: SyntheticRunReceipt,
    now: datetime,
) -> None:
    del command
    connection.execute(
        """
        INSERT INTO routine_occurrences (
            occurrence_id, tenant_id, actor_principal_id, client_command_id,
            revision_digest, scheduled_for, local_civil_time, timezone,
            utc_offset_seconds, offset_decision, outcome, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'UTC', 0, 'exact', 'queued', %s)
        """,
        (
            receipt.run_id,
            tenant_id,
            principal_id,
            receipt.command_id,
            _digest(revision.revision_digest),
            now,
            now.replace(tzinfo=None),
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO operation_jobs (
            job_id, tenant_id, occurrence_id, operation, state,
            timeout_seconds, component_digests, created_at
        ) VALUES (%s, %s, %s, 'synthetic_four_stage', 'pending', %s, %s, %s)
        """,
        (
            receipt.job_id,
            tenant_id,
            receipt.run_id,
            revision.timeout_seconds,
            [_digest(item) for item in revision.component_digests],
            now,
        ),
    )


def _insert_result(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    result: FixedOperationResult,
) -> None:
    connection.execute(
        """
        INSERT INTO fixed_operation_results (
            result_id, job_id, tenant_id, attempt_id, fencing_token, outcome,
            ticket_id, lifecycle_facts, detail_code, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.result_id,
            result.job_id,
            tenant_id,
            result.attempt_id,
            result.fencing_token,
            result.state.value,
            result.ticket_id,
            list(result.lifecycle_facts),
            result.detail_code,
            result.recorded_at,
        ),
    )


def _load_result(
    connection: psycopg.Connection[dict[str, object]], job_id: UUID
) -> FixedOperationResult | None:
    row = connection.execute(
        "SELECT * FROM fixed_operation_results WHERE job_id = %s", (job_id,)
    ).fetchone()
    if row is None:
        return None
    return FixedOperationResult(
        cast(UUID, row["result_id"]),
        cast(UUID, row["job_id"]),
        cast(UUID, row["attempt_id"]),
        cast(UUID, row["fencing_token"]),
        SyntheticRunState(str(row["outcome"])),
        cast(UUID | None, row["ticket_id"]),
        tuple(cast(list[str], row["lifecycle_facts"])),
        str(row["detail_code"]),
        cast(datetime, row["recorded_at"]),
    )


def _job(row: dict[str, object]) -> FixedOperationJob:
    return FixedOperationJob(
        cast(UUID, row["job_id"]),
        cast(UUID, row["tenant_id"]),
        cast(UUID, row["occurrence_id"]),
        str(row["operation"]),
        int(cast(int, row["timeout_seconds"])),
        tuple(
            "sha256:" + cast(bytes, item).hex()
            for item in cast(list[object], row["component_digests"])
        ),
        cast(datetime, row["created_at"]),
    )


def _attempt_count(connection: psycopg.Connection[dict[str, object]], job_id: UUID) -> int:
    row = cast(
        dict[str, object],
        connection.execute(
            "SELECT count(*) AS value FROM fixed_operation_attempts WHERE job_id = %s",
            (job_id,),
        ).fetchone(),
    )
    return int(cast(int, row["value"]))


def _receipt(payload: dict[str, object]) -> SyntheticRunReceipt:
    return SyntheticRunReceipt(
        UUID(str(payload["command_id"])),
        tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        UUID(str(payload["run_id"])),
        UUID(str(payload["job_id"])),
        str(payload["workflow_ref"]),
    )


def _database_now(connection: psycopg.Connection[dict[str, object]]) -> datetime:
    row = cast(
        dict[str, object],
        connection.execute("SELECT transaction_timestamp() AS value").fetchone(),
    )
    return cast(datetime, row["value"])


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _uuid7(now: datetime, identity: bytes) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = int.from_bytes(hashlib.sha256(identity).digest()[:10], "big") & ((1 << 74) - 1)
    value = milliseconds << 80 | 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62 | random_bits & ((1 << 62) - 1)
    return UUID(int=value)
