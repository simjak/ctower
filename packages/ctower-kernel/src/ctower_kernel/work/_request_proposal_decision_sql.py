"""Atomic proposal decisions and separately identified Request commands."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import cast
from uuid import UUID, uuid5

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.request_proposal_events import RequestProposalChangedPayload
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_change_sql import _change_reserved
from ctower_kernel.work._request_proposal_types import (
    RequestMaintenanceProposalConfirm,
    RequestMaintenanceProposalDecisionResult,
    RequestMaintenanceProposalReject,
    decision_result_from_committed,
)
from ctower_kernel.work._request_types import (
    RequestChange,
    RequestChangeResult,
    RequestClosureEvaluation,
    RequestTriage,
)

__all__: tuple[str, ...] = ()

_TARGET_COMMAND_NAMESPACE = UUID("5662d544-6e98-5ea4-a03b-8e553fb04b40")
type ProposalDecisionCommand = RequestMaintenanceProposalConfirm | RequestMaintenanceProposalReject


def confirm_request_proposal(
    dsn: str,
    actor: Actor,
    command: RequestMaintenanceProposalConfirm,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
    return _decide(dsn, actor, command, request_digest=request_digest, now=now, telemetry=telemetry)


def reject_request_proposal(
    dsn: str,
    actor: Actor,
    command: RequestMaintenanceProposalReject,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
    return _decide(dsn, actor, command, request_digest=request_digest, now=now, telemetry=telemetry)


def _decide(
    dsn: str,
    actor: Actor,
    command: ProposalDecisionCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return (
                replay
                if isinstance(replay, RecordProblem)
                else decision_result_from_committed(replay)
            )
        return _decide_reserved(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _decide_reserved(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: ProposalDecisionCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalDecisionResult | RecordProblem:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{actor.tenant_id}:request-proposal:{command.proposal_id}",),
    )
    proposal = _accepted_proposal(connection, actor.tenant_id, command.proposal_id)
    problem = _decision_problem(connection, actor, command, proposal)
    if problem is not None:
        return _refuse(transaction, actor, command, request_digest, problem, now)
    accepted_proposal = cast(dict[str, object], proposal)
    if isinstance(command, RequestMaintenanceProposalReject):
        target_command_id = None
        target_result = None
        target_problem = None
    else:
        target_command = _target_command(command, accepted_proposal)
        target_command_id = target_command.client_command_id
        target_result, target_problem = _execute_target(
            connection,
            actor,
            target_command,
            accepted_proposal,
            now=now,
            telemetry=telemetry,
        )
    return _commit_decision(
        connection,
        transaction,
        actor,
        command,
        accepted_proposal,
        request_digest=request_digest,
        target_command_id=target_command_id,
        target_result=target_result,
        target_problem=target_problem,
        now=now,
        telemetry=telemetry,
    )


def _decision_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ProposalDecisionCommand,
    proposal: dict[str, object] | None,
) -> RecordProblem | None:
    if proposal is None:
        return _problem(command, "proposal-not-found", "Proposal is not accepted or available")
    if _has_decision(connection, actor.tenant_id, command.proposal_id):
        return _problem(
            command, "proposal-already-decided", "Proposal already has a terminal decision"
        )
    if command.expected_proposal_version != int(cast(int, proposal["proposal_version"])):
        return _problem(command, "proposal-version-conflict", "Proposal version is stale")
    return None


def _execute_target(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    target_command: RequestChange,
    proposal: dict[str, object],
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[RequestChangeResult | None, RecordProblem | None]:
    target_digest = _digest(target_command.request_payload())
    target_transaction = RecordTransaction(connection)
    replay = target_transaction.reserve(
        actor.principal_id, target_command.client_command_id, target_digest
    )
    if isinstance(replay, RecordProblem):
        return None, replay
    if replay is not None:
        return _target_result(replay), None
    preflight = _confirmation_refusal(connection, actor, target_command, proposal)
    if preflight is not None:
        target_transaction.refuse(
            actor.tenant_id,
            actor.principal_id,
            target_command.client_command_id,
            target_digest,
            preflight,
            now=now,
        )
        return None, preflight
    outcome = _change_reserved(
        connection,
        target_transaction,
        actor,
        target_command,
        request_digest=target_digest,
        now=now,
        telemetry=telemetry,
    )
    return (None, outcome) if isinstance(outcome, RecordProblem) else (outcome, None)


def _commit_decision(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: ProposalDecisionCommand,
    proposal: dict[str, object],
    *,
    request_digest: bytes,
    target_command_id: UUID | None,
    target_result: RequestChangeResult | None,
    target_problem: RecordProblem | None,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestMaintenanceProposalDecisionResult:
    operation = "rejected" if isinstance(command, RequestMaintenanceProposalReject) else "confirmed"
    target_outcome = _target_outcome(target_command_id, target_result)
    target_problem_code = None if target_problem is None else target_problem.code
    event_id, decision_id = uuid7(now), uuid7(now)
    result = RequestMaintenanceProposalDecisionResult(
        command.client_command_id,
        (event_id,),
        decision_id,
        command.proposal_id,
        operation,
        actor.principal_id,
        now,
        command.reason if isinstance(command, RequestMaintenanceProposalReject) else None,
        target_command_id,
        target_outcome,
        target_problem_code,
        None if target_result is None else target_result.version,
    )
    event = _decision_event(
        actor,
        command,
        proposal,
        result,
        previous=_previous_proposal_event(connection, actor, command),
        request_digest=request_digest,
        telemetry=telemetry,
    )
    transaction.commit(
        event,
        outbox_id=uuid7(now),
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=_subjects(proposal, command.proposal_id),
    )
    _store_decision(connection, actor, command, result)
    return result


def _target_outcome(
    target_command_id: UUID | None, target_result: RequestChangeResult | None
) -> str | None:
    if target_command_id is None:
        return None
    return "accepted" if target_result is not None else "refused"


def _previous_proposal_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ProposalDecisionCommand,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT event_id, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"request-proposal:{command.proposal_id}"),
    ).fetchone()


def _decision_event(
    actor: Actor,
    command: ProposalDecisionCommand,
    proposal: dict[str, object],
    result: RequestMaintenanceProposalDecisionResult,
    *,
    previous: dict[str, object] | None,
    request_digest: bytes,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.proposal_id,
        causation_id=cast(UUID, previous["event_id"]) if previous is not None else None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=result.event_ids[0],
        kind=EventKind.REQUEST_PROPOSAL_CHANGED,
        origin=EventOrigin.API,
        payload=RequestProposalChangedPayload(
            result.operation,
            command.proposal_id,
            str(proposal["kind"]),
            result.operation.upper(),
            cast(UUID, proposal["target_request_id"]),
            result.target_command_id,
            result.target_outcome,
            result.target_problem_code,
        ),
        prev_hash=bytes(cast(bytes, previous["event_hash"])) if previous is not None else bytes(32),
        request_sha256=request_digest,
        sequence=2,
        server_time=result.decided_at,
        stream_id=f"request-proposal:{command.proposal_id}",
        tenant_id=actor.tenant_id,
    )


def _store_decision(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ProposalDecisionCommand,
    result: RequestMaintenanceProposalDecisionResult,
) -> None:
    connection.execute(
        """
        INSERT INTO request_maintenance_proposal_decisions (
            decision_id, proposal_id, tenant_id, operation, expected_proposal_version,
            decided_by, decision_command_id, decision_event_id, reason,
            target_command_id, target_outcome, target_problem_code,
            target_request_version, decided_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.decision_id,
            command.proposal_id,
            actor.tenant_id,
            result.operation,
            command.expected_proposal_version,
            actor.principal_id,
            command.client_command_id,
            result.event_ids[0],
            result.reason,
            result.target_command_id,
            result.target_outcome,
            result.target_problem_code,
            result.target_request_version,
            result.decided_at,
        ),
    )


def _target_command(
    command: RequestMaintenanceProposalConfirm, proposal: dict[str, object]
) -> RequestChange:
    target_command_id = uuid5(_TARGET_COMMAND_NAMESPACE, str(command.client_command_id))
    request_id = cast(UUID, proposal["target_request_id"])
    version = int(cast(int, proposal["target_expected_version"]))
    kind = str(proposal["kind"])
    reason = f"Confirmed Request-maintenance proposal {command.proposal_id}"
    if kind == "completed-but-open":
        return RequestClosureEvaluation(target_command_id, request_id, version, reason)
    if kind in {"duplicate", "supersession"}:
        return RequestTriage(
            target_command_id,
            request_id,
            version,
            "DUPLICATE",
            reason,
            cast(UUID, proposal["related_request_id"]),
        )
    if kind == "kill":
        return RequestTriage(target_command_id, request_id, version, "REJECTED", reason)
    return RequestTriage(target_command_id, request_id, version, "ACCEPTED")


def _confirmation_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    target_command: RequestChange,
    proposal: dict[str, object],
) -> RecordProblem | None:
    target = _accepted_request(
        connection, actor.tenant_id, cast(UUID, proposal["target_request_id"])
    )
    if not _request_matches(
        target,
        expected_version=None,
        exact_text=str(proposal["target_text"]),
    ):
        return _target_problem(
            target_command.client_command_id,
            "proposal-target-changed",
            "Proposal target Request changed before confirmation",
        )
    related_id = cast(UUID | None, proposal["related_request_id"])
    if related_id is None:
        return None
    related = _accepted_request(connection, actor.tenant_id, related_id)
    if not _request_matches(
        related,
        expected_version=int(cast(int, proposal["related_expected_version"])),
        exact_text=str(proposal["related_text"]),
    ):
        return _target_problem(
            target_command.client_command_id,
            "proposal-related-changed",
            "Proposal related Request changed before confirmation",
        )
    return None


def _accepted_request(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    request_id: UUID,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT request.version, request.content
        FROM requests AS request
        JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = request.tenant_id
         AND confirmation.principal_id = request.submitted_by
         AND confirmation.client_command_id = request.capture_command_id
        WHERE request.tenant_id = %s AND request.request_id = %s
        """,
        (tenant_id, request_id),
    ).fetchone()


def _request_matches(
    request: dict[str, object] | None,
    *,
    expected_version: int | None,
    exact_text: str,
) -> bool:
    return (
        request is not None
        and (expected_version is None or int(cast(int, request["version"])) == expected_version)
        and str(request["content"]) == exact_text
    )


def _target_problem(command_id: UUID, code: str, detail: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=detail,
        status=409,
        title="Request proposal target refused",
        command_id=command_id,
    )


def _accepted_proposal(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, proposal_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT proposal.*
        FROM request_maintenance_proposals AS proposal
        WHERE proposal.tenant_id = %s AND proposal.proposal_id = %s
          AND EXISTS (
            SELECT 1 FROM durability_acceptance_confirmations AS confirmation
            WHERE confirmation.tenant_id = proposal.tenant_id
              AND confirmation.principal_id = proposal.proposer_principal_id
              AND confirmation.client_command_id = proposal.append_command_id
          )
        """,
        (tenant_id, proposal_id),
    ).fetchone()


def _has_decision(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, proposal_id: UUID
) -> bool:
    return (
        connection.execute(
            """SELECT 1 FROM request_maintenance_proposal_decisions
               WHERE tenant_id = %s AND proposal_id = %s""",
            (tenant_id, proposal_id),
        ).fetchone()
        is not None
    )


def _subjects(proposal: dict[str, object], proposal_id: UUID) -> tuple[tuple[str, UUID], ...]:
    related_id = cast(UUID | None, proposal["related_request_id"])
    related = () if related_id is None else (("request", related_id),)
    return (
        ("request_proposal", proposal_id),
        ("request", cast(UUID, proposal["target_request_id"])),
        *related,
    )


def _target_result(payload: dict[str, object]) -> RequestChangeResult:
    return RequestChangeResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        operation=str(payload["operation"]),
        request_id=UUID(str(payload["request_id"])),
        request_number=int(cast(int, payload["request_number"])),
        version=int(cast(int, payload["version"])),
        state=str(payload["state"]),
    )


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()


def _problem(command: ProposalDecisionCommand, code: str, detail: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=detail,
        status=409 if code != "proposal-not-found" else 404,
        title="Request proposal decision refused",
        command_id=command.client_command_id,
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: ProposalDecisionCommand,
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
