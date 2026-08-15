"""Atomic append and evidence validation for Request-maintenance proposals."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.request_proposal_events import RequestProposalChangedPayload
from ctower_kernel.record.transaction import (
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_proposal_types import (
    ProofEvidencePointer,
    RecordEventEvidencePointer,
    RequestMaintenanceProposalAppend,
    RequestMaintenanceProposalAppendResult,
    RequestProposalEvidencePointer,
    append_result_from_committed,
)

__all__: tuple[str, ...] = ()


def append_request_proposal(
    dsn: str,
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalAppendResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return (
                replay
                if isinstance(replay, RecordProblem)
                else append_result_from_committed(replay)
            )
        authority = _authority_refusal(connection, actor, command)
        if authority is not None:
            return _refuse(transaction, actor, command, request_digest, authority, now)
        prepared = _prepare_append(connection, actor, command)
        if isinstance(prepared, RecordProblem):
            return _refuse(transaction, actor, command, request_digest, prepared, now)
        ambiguity = prepared
        return _commit(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            ambiguity=ambiguity,
            now=now,
            telemetry=telemetry,
        )


def _prepare_append(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
) -> str | RecordProblem | None:
    target = _accepted_request(connection, actor.tenant_id, command.target_request_id)
    related = (
        None
        if command.related_request_id is None
        else _accepted_request(connection, actor.tenant_id, command.related_request_id)
    )
    problem = _request_refusal(command, target, related)
    if problem is not None:
        return problem
    if command.source_record_position > _watermark(connection):
        return _problem(
            command,
            "proposal-watermark-invalid",
            "Proposal source watermark is in the future",
        )
    if not all(
        _evidence_is_accepted(connection, actor.tenant_id, item, command.source_record_position)
        for item in command.evidence
    ):
        return _problem(
            command,
            "proposal-evidence-unavailable",
            "Proposal evidence is not accepted at the source watermark",
        )
    if target is None:
        raise RuntimeError("validated proposal target disappeared")
    return _ambiguity(connection, actor.tenant_id, command, target, related)


def _authority_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
) -> RecordProblem | None:
    scope = project_scope_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        project_keys=(command.project_key,),
        command_id=command.client_command_id,
    )
    if scope is not None:
        return scope
    if _credential_is_active(connection, actor, command):
        return None
    return _problem(
        command,
        "proposal-credential-invalid",
        "Proposal seat credential is not active",
    )


def _commit(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
    *,
    request_digest: bytes,
    ambiguity: str | None,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalAppendResult:
    proposal_id, event_id = uuid7(now), uuid7(now)
    subjects = _subjects(command, proposal_id)
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=proposal_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.REQUEST_PROPOSAL_CHANGED,
        origin=EventOrigin.API,
        payload=RequestProposalChangedPayload(
            "appended",
            proposal_id,
            command.kind,
            "OPEN",
            command.target_request_id,
            None,
            None,
            None,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"request-proposal:{proposal_id}",
        tenant_id=actor.tenant_id,
    )
    result = RequestMaintenanceProposalAppendResult(
        command.client_command_id,
        (event_id,),
        proposal_id,
        command.project_key,
        command.kind,
        "OPEN",
        ambiguity,
        actor.principal_id,
        command.source_record_position,
        command.target_request_id,
    )
    transaction.commit(
        event,
        outbox_id=uuid7(now),
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=subjects,
    )
    _persist_proposal(connection, actor, command, result, now=now)
    return result


def _persist_proposal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
    result: RequestMaintenanceProposalAppendResult,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_maintenance_proposals (
            proposal_id, tenant_id, project_key, kind, basis, target_request_id,
            target_expected_version, target_text, related_request_id,
            related_expected_version, related_text, source_record_position,
            proposer_principal_id, seat_credential_id, ambiguity_reason, proposal_version,
            append_command_id, append_event_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
        """,
        (
            result.proposal_id,
            actor.tenant_id,
            command.project_key,
            command.kind,
            command.basis,
            command.target_request_id,
            command.target_expected_version,
            command.target_text,
            command.related_request_id,
            command.related_expected_version,
            command.related_text,
            command.source_record_position,
            actor.principal_id,
            actor.seat_credential_id,
            result.ambiguity_reason,
            command.client_command_id,
            result.event_ids[0],
            now,
        ),
    )
    for pointer in command.evidence:
        _persist_evidence(connection, actor.tenant_id, result.proposal_id, pointer, now)


def _persist_evidence(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    proposal_id: UUID,
    pointer: RequestProposalEvidencePointer,
    now: datetime,
) -> None:
    if isinstance(pointer, RecordEventEvidencePointer):
        values: tuple[object, ...] = (
            uuid7(now),
            proposal_id,
            tenant_id,
            pointer.kind,
            pointer.event_id,
            pointer.event_kind,
            bytes.fromhex(pointer.event_digest.removeprefix("sha256:")),
            None,
            None,
            None,
            None,
            now,
        )
    else:
        values = (
            uuid7(now),
            proposal_id,
            tenant_id,
            pointer.kind,
            None,
            None,
            None,
            pointer.ticket_id,
            pointer.proof_id,
            pointer.evidence_id,
            bytes.fromhex(pointer.artifact_digest.removeprefix("sha256:")),
            now,
        )
    connection.execute(
        """
        INSERT INTO request_maintenance_proposal_evidence (
            evidence_pointer_id, proposal_id, tenant_id, pointer_kind,
            record_event_id, record_event_kind, record_event_digest,
            ticket_id, proof_id, evidence_id, artifact_digest, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        values,
    )


def _accepted_request(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT request.request_id, request.project_key, request.content, request.version
        FROM requests AS request
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = request.tenant_id
         AND confirmation.principal_id = request.submitted_by
         AND confirmation.client_command_id = request.capture_command_id
        WHERE request.tenant_id = %s AND request.request_id = %s
        """,
        (tenant_id, request_id),
    ).fetchone()


def _request_refusal(
    command: RequestMaintenanceProposalAppend,
    target: dict[str, object] | None,
    related: dict[str, object] | None,
) -> RecordProblem | None:
    if target is None or str(target["project_key"]) != command.project_key:
        return _problem(
            command, "proposal-target-not-found", "Proposal target Request is unavailable"
        )
    if str(target["content"]) != command.target_text:
        return _problem(
            command, "proposal-quote-mismatch", "Proposal target text is not byte exact"
        )
    if command.related_request_id is None:
        return None
    if related is None or str(related["project_key"]) != command.project_key:
        return _problem(
            command, "proposal-related-not-found", "Proposal related Request is unavailable"
        )
    if str(related["content"]) != command.related_text:
        return _problem(
            command, "proposal-quote-mismatch", "Proposal related text is not byte exact"
        )
    return None


def _credential_is_active(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
) -> bool:
    if actor.seat_credential_id is None:
        return True
    row = connection.execute(
        """
        SELECT 1
        FROM seat_credential_issuances AS issuance
        JOIN project_seats AS seat
          ON seat.tenant_id = issuance.tenant_id AND seat.principal_id = issuance.principal_id
        JOIN seat_credential_scopes AS scope
          ON scope.tenant_id = issuance.tenant_id AND scope.credential_id = issuance.credential_id
        LEFT JOIN seat_credential_revocations AS revocation
          ON revocation.tenant_id = issuance.tenant_id
         AND revocation.credential_id = issuance.credential_id
        WHERE issuance.tenant_id = %s AND issuance.principal_id = %s
          AND issuance.credential_id = %s AND seat.project_key = %s
          AND scope.scope = 'transition' AND revocation.credential_id IS NULL
        """,
        (actor.tenant_id, actor.principal_id, actor.seat_credential_id, command.project_key),
    ).fetchone()
    return row is not None


def _evidence_is_accepted(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    pointer: RequestProposalEvidencePointer,
    watermark: int,
) -> bool:
    if isinstance(pointer, RecordEventEvidencePointer):
        row = connection.execute(
            """
            SELECT 1 FROM events AS event
            JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = event.tenant_id
             AND confirmation.principal_id = event.actor_principal_id
             AND confirmation.client_command_id = event.client_command_id
            WHERE event.tenant_id = %s AND event.event_id = %s AND event.kind = %s
              AND event.event_hash = %s AND event.record_position <= %s
              AND confirmation.acceptance_position <= %s
            """,
            (
                tenant_id,
                pointer.event_id,
                pointer.event_kind,
                bytes.fromhex(pointer.event_digest.removeprefix("sha256:")),
                watermark,
                watermark,
            ),
        ).fetchone()
        return row is not None
    row = connection.execute(
        """
        SELECT 1 FROM proof_evidence AS evidence
        JOIN proof_bundles AS proof
          ON proof.tenant_id = evidence.tenant_id AND proof.proof_id = evidence.proof_id
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = evidence.tenant_id
         AND confirmation.principal_id = evidence.producer_id
         AND confirmation.client_command_id = evidence.client_command_id
        WHERE evidence.tenant_id = %s AND evidence.evidence_id = %s
          AND evidence.proof_id = %s AND proof.ticket_id = %s
          AND evidence.artifact_digest = %s AND confirmation.acceptance_position <= %s
        """,
        (
            tenant_id,
            pointer.evidence_id,
            pointer.proof_id,
            pointer.ticket_id,
            bytes.fromhex(pointer.artifact_digest.removeprefix("sha256:")),
            watermark,
        ),
    ).fetchone()
    return row is not None


def _ambiguity(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    command: RequestMaintenanceProposalAppend,
    target: dict[str, object],
    related: dict[str, object] | None,
) -> str | None:
    stale = command.target_expected_version != int(cast(int, target["version"]))
    if related is not None:
        stale = stale or command.related_expected_version != int(cast(int, related["version"]))
    if stale:
        return "target-version-stale"
    if command.basis == "similarity":
        return "duplicate-uncertain"
    proof_pointers = tuple(
        item for item in command.evidence if isinstance(item, ProofEvidencePointer)
    )
    if command.kind == "completed-but-open" and not _has_all_shipped_closure_evidence(
        connection,
        tenant_id,
        command.target_request_id,
        proof_pointers,
    ):
        return "completion-unproven"
    return command.ambiguity_reason


def _has_all_shipped_closure_evidence(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    pointers: tuple[ProofEvidencePointer, ...],
) -> bool:
    rows = connection.execute(
        """
        SELECT ticket_id FROM (
            SELECT DISTINCT ON (fact.ticket_id)
                   fact.ticket_id, fact.purpose, fact.active
            FROM request_ticket_relation_facts AS fact
            WHERE fact.tenant_id = %s AND fact.request_id = %s
            ORDER BY fact.ticket_id, fact.request_version DESC
        ) AS latest
        WHERE latest.active AND latest.purpose = 'required'
        """,
        (tenant_id, request_id),
    ).fetchall()
    required = {cast(UUID, row["ticket_id"]) for row in rows}
    proven = {
        pointer.ticket_id
        for pointer in pointers
        if _is_shipped_closure_evidence(connection, tenant_id, request_id, pointer)
    }
    return bool(required) and required <= proven


def _is_shipped_closure_evidence(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
    pointer: ProofEvidencePointer,
) -> bool:
    """Match one pointer to the current proof of a closed required Ticket."""

    row = connection.execute(
        """
        WITH latest_relation AS (
            SELECT DISTINCT ON (fact.ticket_id)
                   fact.ticket_id, fact.purpose, fact.active
            FROM request_ticket_relation_facts AS fact
            WHERE fact.tenant_id = %s AND fact.request_id = %s
            ORDER BY fact.ticket_id, fact.request_version DESC
        )
        SELECT 1
        FROM proof_evidence AS evidence
        JOIN proof_bundles AS bundle
          ON bundle.tenant_id = evidence.tenant_id
         AND bundle.proof_id = evidence.proof_id
         AND bundle.candidate_digest = evidence.candidate_digest
        JOIN tickets AS ticket
          ON ticket.tenant_id = bundle.tenant_id AND ticket.ticket_id = bundle.ticket_id
        JOIN lifecycle_episodes AS episode
          ON episode.tenant_id = ticket.tenant_id AND episode.ticket_id = ticket.ticket_id
         AND episode.episode_number = ticket.current_episode
        JOIN latest_relation AS relation ON relation.ticket_id = ticket.ticket_id
        WHERE evidence.tenant_id = %s AND evidence.evidence_id = %s
          AND evidence.proof_id = %s AND bundle.ticket_id = %s
          AND evidence.artifact_digest = %s
          AND relation.active AND relation.purpose = 'required'
          AND episode.state = 'closed' AND episode.closed_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM blocker_heads AS blocker
              WHERE blocker.tenant_id = ticket.tenant_id
                AND blocker.ticket_id = ticket.ticket_id
                AND blocker.board_impact AND blocker.resolved_at IS NULL
          )
          AND NOT EXISTS (
              SELECT 1 FROM proof_invalidations AS invalidation
              WHERE invalidation.tenant_id = bundle.tenant_id
                AND invalidation.proof_id = bundle.proof_id
                AND invalidation.recorded_at > episode.closed_at
          )
        """,
        (
            tenant_id,
            request_id,
            tenant_id,
            pointer.evidence_id,
            pointer.proof_id,
            pointer.ticket_id,
            bytes.fromhex(pointer.artifact_digest.removeprefix("sha256:")),
        ),
    ).fetchone()
    return row is not None


def _subjects(
    command: RequestMaintenanceProposalAppend, proposal_id: UUID
) -> tuple[tuple[str, UUID], ...]:
    related = (
        () if command.related_request_id is None else (("request", command.related_request_id),)
    )
    return (("request_proposal", proposal_id), ("request", command.target_request_id), *related)


def _watermark(connection: psycopg.Connection[dict[str, object]]) -> int:
    row = connection.execute(
        "SELECT last_position FROM record_position_ledger WHERE singleton"
    ).fetchone()
    return 0 if row is None else int(cast(int, row["last_position"]))


def _problem(command: RequestMaintenanceProposalAppend, code: str, detail: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=detail,
        status=409,
        title="Request proposal refused",
        command_id=command.client_command_id,
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestMaintenanceProposalAppend,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem
