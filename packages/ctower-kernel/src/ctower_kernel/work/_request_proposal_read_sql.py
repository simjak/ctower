"""Accepted-only reads for Request-maintenance proposal facts."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.transaction import project_scope_refusal
from ctower_kernel.work._request_proposal_types import (
    ProofEvidencePointer,
    RecordEventEvidencePointer,
    RequestMaintenanceProposalDecisionResult,
    RequestMaintenanceProposalList,
    RequestMaintenanceProposalRow,
    RequestProposalEvidencePointer,
)
from ctower_kernel.work._request_read_sql import _requested_projects

__all__: tuple[str, ...] = ()


def list_request_proposals(
    dsn: str,
    actor: Actor,
    *,
    proposal_id: UUID | None,
    project_key: str | None,
    kind: str | None,
    state: str | None,
    now: datetime,
) -> RequestMaintenanceProposalList | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        requested = _requested_projects(connection, actor.tenant_id, project_key)
        if project_key is not None and not requested:
            return _problem("proposal-project-unavailable", "Proposal Project is unavailable", 404)
        scope = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=requested,
            operator_only=project_key is None and actor.kind is not PrincipalKind.OPERATOR,
        )
        if scope is not None:
            return scope
        rows = connection.execute(
            _LIST_SQL,
            (
                actor.tenant_id,
                list(requested),
                proposal_id,
                proposal_id,
                kind,
                kind,
                state,
                state,
            ),
        ).fetchall()
        evidence = _evidence_by_proposal(
            connection,
            actor.tenant_id,
            tuple(cast(UUID, row["proposal_id"]) for row in rows),
        )
        watermark_row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
        watermark = 0 if watermark_row is None else int(cast(int, watermark_row["last_position"]))
    return RequestMaintenanceProposalList(
        tuple(_row(item, evidence.get(cast(UUID, item["proposal_id"]), ())) for item in rows),
        watermark,
        now,
    )


_LIST_SQL = """
WITH accepted_decision AS (
    SELECT decision.*, confirmation.acceptance_position
    FROM request_maintenance_proposal_decisions AS decision
    JOIN durability_acceptance_confirmations AS confirmation
      ON confirmation.tenant_id = decision.tenant_id
     AND confirmation.principal_id = decision.decided_by
     AND confirmation.client_command_id = decision.decision_command_id
)
SELECT proposal.*,
       decision.decision_id, decision.operation, decision.decided_by,
       decision.decision_command_id, decision.decision_event_id, decision.reason,
       decision.target_command_id, decision.target_outcome, decision.target_problem_code,
       decision.target_request_version, decision.decided_at, decision.acceptance_position,
       CASE WHEN decision.operation = 'confirmed' THEN 'CONFIRMED'
            WHEN decision.operation = 'rejected' THEN 'REJECTED'
            ELSE 'OPEN' END AS derived_state
FROM request_maintenance_proposals AS proposal
JOIN durability_acceptance_confirmations AS append_confirmation
  ON append_confirmation.tenant_id = proposal.tenant_id
 AND append_confirmation.principal_id = proposal.proposer_principal_id
 AND append_confirmation.client_command_id = proposal.append_command_id
LEFT JOIN accepted_decision AS decision
  ON decision.tenant_id = proposal.tenant_id AND decision.proposal_id = proposal.proposal_id
WHERE proposal.tenant_id = %s AND proposal.project_key = ANY(%s)
  AND (%s::uuid IS NULL OR proposal.proposal_id = %s)
  AND (%s::text IS NULL OR proposal.kind = %s)
  AND (%s::text IS NULL OR CASE WHEN decision.operation = 'confirmed' THEN 'CONFIRMED'
            WHEN decision.operation = 'rejected' THEN 'REJECTED' ELSE 'OPEN' END = %s)
ORDER BY proposal.created_at DESC, proposal.proposal_id DESC
"""


def _evidence_by_proposal(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    proposal_ids: tuple[UUID, ...],
) -> dict[UUID, tuple[RequestProposalEvidencePointer, ...]]:
    if not proposal_ids:
        return {}
    rows = connection.execute(
        """
        SELECT * FROM request_maintenance_proposal_evidence
        WHERE tenant_id = %s AND proposal_id = ANY(%s)
        ORDER BY proposal_id, evidence_pointer_id
        """,
        (tenant_id, list(proposal_ids)),
    ).fetchall()
    grouped: dict[UUID, list[RequestProposalEvidencePointer]] = {}
    for row in rows:
        grouped.setdefault(cast(UUID, row["proposal_id"]), []).append(_evidence(row))
    return {key: tuple(value) for key, value in grouped.items()}


def _evidence(row: dict[str, object]) -> RequestProposalEvidencePointer:
    if str(row["pointer_kind"]) == "record-event":
        return RecordEventEvidencePointer(
            cast(UUID, row["record_event_id"]),
            str(row["record_event_kind"]),
            f"sha256:{bytes(cast(bytes, row['record_event_digest'])).hex()}",
        )
    return ProofEvidencePointer(
        cast(UUID, row["ticket_id"]),
        cast(UUID, row["proof_id"]),
        cast(UUID, row["evidence_id"]),
        f"sha256:{bytes(cast(bytes, row['artifact_digest'])).hex()}",
    )


def _row(
    row: dict[str, object], evidence: tuple[RequestProposalEvidencePointer, ...]
) -> RequestMaintenanceProposalRow:
    decision = None if row["decision_id"] is None else _decision(row)
    return RequestMaintenanceProposalRow(
        proposal_id=cast(UUID, row["proposal_id"]),
        project_key=str(row["project_key"]),
        kind=str(row["kind"]),
        basis=str(row["basis"]),
        state=str(row["derived_state"]),
        ambiguity_reason=cast(str | None, row["ambiguity_reason"]),
        target_request_id=cast(UUID, row["target_request_id"]),
        target_expected_version=int(cast(int, row["target_expected_version"])),
        target_text=str(row["target_text"]),
        related_request_id=cast(UUID | None, row["related_request_id"]),
        related_expected_version=cast(int | None, row["related_expected_version"]),
        related_text=cast(str | None, row["related_text"]),
        source_record_position=int(cast(int, row["source_record_position"])),
        proposer_principal_id=cast(UUID, row["proposer_principal_id"]),
        seat_credential_id=cast(UUID | None, row["seat_credential_id"]),
        created_at=cast(datetime, row["created_at"]),
        evidence=evidence,
        decision=decision,
        proposal_version=int(cast(int, row["proposal_version"])),
    )


def _decision(row: dict[str, object]) -> RequestMaintenanceProposalDecisionResult:
    return RequestMaintenanceProposalDecisionResult(
        command_id=cast(UUID, row["decision_command_id"]),
        event_ids=(cast(UUID, row["decision_event_id"]),),
        decision_id=cast(UUID, row["decision_id"]),
        proposal_id=cast(UUID, row["proposal_id"]),
        operation=str(row["operation"]),
        decided_by=cast(UUID, row["decided_by"]),
        decided_at=cast(datetime, row["decided_at"]),
        reason=cast(str | None, row["reason"]),
        target_command_id=cast(UUID | None, row["target_command_id"]),
        target_outcome=cast(str | None, row["target_outcome"]),
        target_problem_code=cast(str | None, row["target_problem_code"]),
        target_request_version=cast(int | None, row["target_request_version"]),
        expected_proposal_version=1,
        accepted_position=int(cast(int, row["acceptance_position"])),
    )


def _problem(code: str, detail: str, status: int) -> RecordProblem:
    return RecordProblem(
        code=code, detail=detail, status=status, title="Request proposal unavailable"
    )
