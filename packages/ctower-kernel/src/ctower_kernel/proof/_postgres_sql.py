"""Proof-owned atomic Postgres persistence."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.proof import (
    ChangeCandidate,
    FreezeCriteria,
    Proof,
    ProofActor,
    ProofDecision,
    ProofMutation,
    ProofReceipt,
    RecordEvidence,
    RecordVerdict,
)
from ctower_kernel.proof._snapshot_sql import load_snapshot
from ctower_kernel.record import RecordProblem
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    ProofChangedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

ZERO_HASH = bytes(32)


def mutate_proof(
    dsn: str,
    evaluator: Proof,
    actor: ProofActor,
    mutation: ProofMutation,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ProofReceipt | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _reserve_proof_outcome(
            transaction, actor, mutation, request_digest=request_digest
        )
        if reserved is not None:
            return reserved
        if not _lock_ticket(connection, actor, mutation.ticket_id):
            problem = _problem(mutation, "tenant-scope-denied", 404, "Ticket not found")
            return _refuse(transaction, actor, mutation, request_digest, problem, now)
        bundle = _lock_bundle(connection, actor, mutation.ticket_id)
        current_version = int(cast(int, bundle["version"])) if bundle is not None else 0
        if mutation.expected_version != current_version:
            problem = _version_problem(mutation, current_version)
            return _refuse(transaction, actor, mutation, request_digest, problem, now)
        snapshot = load_snapshot(connection, bundle, actor.tenant_id)
        decision = evaluator.decide(actor, snapshot, mutation.command)
        if not decision.accepted:
            problem = _decision_problem(mutation, decision, current_version)
            return _refuse(transaction, actor, mutation, request_digest, problem, now)
        return _commit_decision(
            connection,
            evaluator,
            actor,
            mutation,
            decision,
            bundle,
            current_version=current_version,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _reserve_proof_outcome(
    transaction: RecordTransaction,
    actor: ProofActor,
    mutation: ProofMutation,
    *,
    request_digest: bytes,
) -> ProofReceipt | RecordProblem | None:
    existing = transaction.reserve(actor.principal_id, mutation.client_command_id, request_digest)
    if isinstance(existing, RecordProblem):
        return existing
    return _receipt_from_payload(existing) if existing is not None else None


def _refuse(
    transaction: RecordTransaction,
    actor: ProofActor,
    mutation: ProofMutation,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        mutation.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _commit_decision(
    connection: psycopg.Connection[dict[str, object]],
    evaluator: Proof,
    actor: ProofActor,
    mutation: ProofMutation,
    decision: ProofDecision,
    bundle: dict[str, object] | None,
    *,
    current_version: int,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ProofReceipt:
    proof_id = cast(UUID, bundle["proof_id"]) if bundle is not None else _uuid7(now)
    version = current_version + 1
    _persist_decision(
        connection,
        actor,
        mutation,
        decision,
        proof_id=proof_id,
        version=version,
        now=now,
    )
    receipt = _receipt(evaluator, mutation, decision, proof_id=proof_id, version=version)
    return _append_change(
        connection,
        actor,
        mutation,
        receipt,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )


def _lock_ticket(
    connection: psycopg.Connection[dict[str, object]], actor: ProofActor, ticket_id: UUID
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s FOR UPDATE",
        (actor.tenant_id, ticket_id),
    ).fetchone()
    return row is not None


def _lock_bundle(
    connection: psycopg.Connection[dict[str, object]], actor: ProofActor, ticket_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT proof_id, version, candidate_digest, candidate_author_id
        FROM proof_bundles WHERE tenant_id = %s AND ticket_id = %s
        FOR UPDATE
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _persist_decision(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    decision: ProofDecision,
    *,
    proof_id: UUID,
    version: int,
    now: datetime,
) -> None:
    command = mutation.command
    if isinstance(command, FreezeCriteria):
        _insert_frozen(connection, actor, mutation, proof_id=proof_id, now=now)
        return
    connection.execute(
        "UPDATE proof_bundles SET version = %s, candidate_digest = %s WHERE proof_id = %s",
        (version, _digest_bytes(decision.snapshot.candidate_digest), proof_id),
    )
    if isinstance(command, RecordEvidence):
        _insert_evidence(connection, actor, mutation, command, proof_id=proof_id, now=now)
    elif isinstance(command, RecordVerdict):
        _insert_verdict(
            connection,
            actor,
            mutation,
            command,
            proof_id=proof_id,
            proof_sequence=version,
            now=now,
        )
    elif isinstance(command, ChangeCandidate):
        _insert_invalidations(connection, actor, mutation, decision, proof_id=proof_id, now=now)


def _insert_frozen(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    *,
    proof_id: UUID,
    now: datetime,
) -> None:
    command = cast(FreezeCriteria, mutation.command)
    connection.execute(
        """
        INSERT INTO proof_bundles (
            proof_id, ticket_id, tenant_id, version, candidate_digest,
            candidate_author_id, frozen_at
        ) VALUES (%s, %s, %s, 1, %s, %s, %s)
        """,
        (
            proof_id,
            mutation.ticket_id,
            actor.tenant_id,
            _digest_bytes(command.candidate_digest),
            command.candidate_author_id,
            now,
        ),
    )
    connection.cursor().executemany(
        """
        INSERT INTO proof_criteria (
            proof_id, tenant_id, criterion_key, description, candidate_dependent,
            requires_verdict, frozen_by, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (
                proof_id,
                actor.tenant_id,
                item.key,
                item.description,
                item.candidate_dependent,
                item.requires_verdict,
                actor.principal_id,
                mutation.client_command_id,
                now,
            )
            for item in command.criteria
        ),
    )


def _insert_evidence(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    command: RecordEvidence,
    *,
    proof_id: UUID,
    now: datetime,
) -> None:
    artifact_digest = _digest_bytes(command.artifact_digest)
    connection.execute(
        """
        INSERT INTO proof_objects (tenant_id, artifact_digest, content, producer_id, recorded_at)
        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, artifact_digest) DO NOTHING
        """,
        (actor.tenant_id, artifact_digest, command.content, actor.principal_id, now),
    )
    connection.execute(
        """
        INSERT INTO proof_evidence (
            evidence_id, proof_id, tenant_id, criterion_key, candidate_digest,
            artifact_digest, producer_id, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.evidence_id,
            proof_id,
            actor.tenant_id,
            command.criterion_key,
            _digest_bytes(command.candidate_digest),
            artifact_digest,
            actor.principal_id,
            mutation.client_command_id,
            now,
        ),
    )


def _insert_verdict(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    command: RecordVerdict,
    *,
    proof_id: UUID,
    proof_sequence: int,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO proof_verdicts (
            verdict_id, proof_id, tenant_id, criterion_key, candidate_digest,
            reviewer_id, decision, protected, client_command_id, recorded_at,
            proof_sequence
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s)
        """,
        (
            command.verdict_id,
            proof_id,
            actor.tenant_id,
            command.criterion_key,
            _digest_bytes(command.candidate_digest),
            actor.principal_id,
            command.decision.value,
            mutation.client_command_id,
            now,
            proof_sequence,
        ),
    )


def _insert_invalidations(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    decision: ProofDecision,
    *,
    proof_id: UUID,
    now: datetime,
) -> None:
    targets = (
        *(("evidence", item) for item in decision.invalidated_evidence_ids),
        *(("verdict", item) for item in decision.invalidated_verdict_ids),
    )
    connection.cursor().executemany(
        """
        INSERT INTO proof_invalidations (
            invalidation_id, proof_id, tenant_id, target_kind, target_id,
            candidate_digest, reason, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, 'candidate-digest-changed', %s, %s)
        """,
        (
            (
                _uuid7(now),
                proof_id,
                actor.tenant_id,
                kind,
                target_id,
                _digest_bytes(decision.snapshot.candidate_digest),
                mutation.client_command_id,
                now,
            )
            for kind, target_id in targets
        ),
    )


def _receipt(
    evaluator: Proof,
    mutation: ProofMutation,
    decision: ProofDecision,
    *,
    proof_id: UUID,
    version: int,
) -> ProofReceipt:
    return ProofReceipt(
        command_id=mutation.client_command_id,
        event_ids=(),
        proof_id=proof_id,
        ticket_id=mutation.ticket_id,
        version=version,
        candidate_digest=cast(str, decision.snapshot.candidate_digest),
        satisfied=evaluator.is_satisfied(decision.snapshot),
        invalidated_evidence_ids=decision.invalidated_evidence_ids,
        invalidated_verdict_ids=decision.invalidated_verdict_ids,
    )


def _append_change(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    receipt: ProofReceipt,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ProofReceipt:
    event_id, outbox_id = _uuid7(now), _uuid7(now)
    event = _proof_event(
        connection,
        actor,
        mutation,
        receipt,
        event_id=event_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    committed = _with_event(receipt, event_id)
    RecordTransaction(connection).commit(
        event,
        outbox_id=outbox_id,
        response_body=committed.response_payload(),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(mutation.client_command_id),
            ticket_id=str(mutation.ticket_id),
        ),
        now=now,
        subjects=(("ticket", receipt.ticket_id), ("proof", receipt.proof_id)),
    )
    return committed


def _proof_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: ProofActor,
    mutation: ProofMutation,
    receipt: ProofReceipt,
    *,
    event_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=receipt.proof_id,
        causation_id=None,
        client_command_id=mutation.client_command_id,
        correlation_id=telemetry.correlation_uuid(mutation.client_command_id),
        event_id=event_id,
        kind=EventKind.PROOF_CHANGED,
        origin=EventOrigin.API,
        payload=ProofChangedPayload(
            operation=_operation(mutation),
            ticket_id=mutation.ticket_id,
            proof_version=receipt.version,
            candidate_digest=receipt.candidate_digest,
            invalidated_evidence_ids=receipt.invalidated_evidence_ids,
            invalidated_verdict_ids=receipt.invalidated_verdict_ids,
        ),
        prev_hash=_previous_hash(connection, receipt.proof_id),
        request_sha256=request_digest,
        sequence=receipt.version,
        server_time=now,
        stream_id=f"proof:{receipt.proof_id}",
        tenant_id=actor.tenant_id,
    )


def _with_event(receipt: ProofReceipt, event_id: UUID) -> ProofReceipt:
    return ProofReceipt(
        command_id=receipt.command_id,
        event_ids=(event_id,),
        proof_id=receipt.proof_id,
        ticket_id=receipt.ticket_id,
        version=receipt.version,
        candidate_digest=receipt.candidate_digest,
        satisfied=receipt.satisfied,
        invalidated_evidence_ids=receipt.invalidated_evidence_ids,
        invalidated_verdict_ids=receipt.invalidated_verdict_ids,
    )


def _previous_hash(connection: psycopg.Connection[dict[str, object]], proof_id: UUID) -> bytes:
    row = connection.execute(
        """
        SELECT event_hash FROM events
        WHERE stream_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (f"proof:{proof_id}",),
    ).fetchone()
    return ZERO_HASH if row is None else bytes(cast(bytes, row["event_hash"]))


def _receipt_from_payload(payload: dict[str, object]) -> ProofReceipt:
    return ProofReceipt(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        proof_id=UUID(str(payload["proof_id"])),
        ticket_id=UUID(str(payload["ticket_id"])),
        version=int(cast(int, payload["version"])),
        candidate_digest=str(payload["candidate_digest"]),
        satisfied=bool(payload["satisfied"]),
        invalidated_evidence_ids=tuple(
            UUID(str(item)) for item in cast(list[object], payload["invalidated_evidence_ids"])
        ),
        invalidated_verdict_ids=tuple(
            UUID(str(item)) for item in cast(list[object], payload["invalidated_verdict_ids"])
        ),
    )


def _operation(mutation: ProofMutation) -> str:
    if isinstance(mutation.command, FreezeCriteria):
        return "freeze_criteria"
    if isinstance(mutation.command, RecordEvidence):
        return "record_evidence"
    if isinstance(mutation.command, RecordVerdict):
        return "record_verdict"
    return "change_candidate"


def _decision_problem(
    mutation: ProofMutation, decision: ProofDecision, current_version: int
) -> RecordProblem:
    forbidden = {
        "candidate-author-mismatch",
        "protected-authority-required",
        "self-review-refused",
    }
    return _problem(
        mutation,
        f"proof-{decision.reason}",
        403 if decision.reason in forbidden else 409,
        "Proof mutation refused",
        current_version=current_version,
    )


def _version_problem(mutation: ProofMutation, current_version: int) -> RecordProblem:
    return _problem(
        mutation,
        "version-conflict",
        409,
        "Proof version conflict",
        current_version=current_version,
    )


def _problem(
    mutation: ProofMutation,
    code: str,
    status: int,
    title: str,
    *,
    current_version: int | None = None,
) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=mutation.client_command_id,
        current_version=current_version,
    )


def _digest_bytes(value: str | None) -> bytes:
    if value is None or not value.startswith("sha256:"):
        raise ValueError("proof digest must be sha256 content addressed")
    return bytes.fromhex(value.removeprefix("sha256:"))


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
