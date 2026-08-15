"""Accepted-only reads for Request-maintenance proposal facts."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from random import SystemRandom
from typing import cast
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
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
_LOGGER = logging.getLogger(__name__)
_RANDOM = SystemRandom()
_MAXIMUM_ATTEMPTS = 3
_MAXIMUM_ELAPSED_SECONDS = 20.0
_CONNECT_TIMEOUT_SECONDS = 2
_STATEMENT_TIMEOUT_MS = 5_000
_INITIAL_BACKOFF_SECONDS = 0.05
_MAXIMUM_BACKOFF_SECONDS = 0.5
_TRANSIENT_SQLSTATES = frozenset(
    {
        "53300",  # too_many_connections
        "55P03",  # lock_not_available
        "57014",  # query_canceled, including statement_timeout
        "57P01",  # admin_shutdown
        "57P02",  # crash_shutdown
        "57P03",  # cannot_connect_now
    }
)


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
    return _read_with_retry(
        lambda: _list_request_proposals_once(
            _bounded_dsn(dsn),
            actor,
            proposal_id=proposal_id,
            project_key=project_key,
            kind=kind,
            state=state,
            now=now,
        )
    )


def _list_request_proposals_once(
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


def _read_with_retry[Outcome](
    operation: Callable[[], Outcome],
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    jitter: Callable[[float], float] | None = None,
) -> Outcome | RecordProblem:
    """Retry an idempotent accepted-only read inside one finite database policy."""

    started = monotonic()
    random_delay = jitter or (lambda ceiling: _RANDOM.uniform(ceiling / 2, ceiling))
    last_failure: psycopg.Error | None = None
    attempt = 0
    for attempt in range(1, _MAXIMUM_ATTEMPTS + 1):
        try:
            return operation()
        except psycopg.Error as error:
            if not _retryable_database_failure(error):
                return _problem(
                    "proposal-read-database-error",
                    "Request proposal database read failed terminally",
                    503,
                )
            last_failure = error
            if not _back_off(
                started,
                attempt,
                failure=error,
                sleep=sleep,
                monotonic=monotonic,
                jitter=random_delay,
            ):
                break
    if last_failure is None:
        raise RuntimeError("proposal read retry policy ended without a classified failure")
    elapsed = monotonic() - started
    _LOGGER.error(
        "Request proposal database read retry policy exhausted",
        extra={
            "attempt_count": attempt,
            "elapsed_seconds": elapsed,
            "last_failure_type": type(last_failure).__name__,
            "last_sqlstate": last_failure.sqlstate,
        },
    )
    return _problem(
        "proposal-read-retry-exhausted",
        "Request proposal database read retry policy exhausted",
        503,
    )


def _back_off(
    started: float,
    attempt: int,
    *,
    failure: psycopg.Error,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
    jitter: Callable[[float], float],
) -> bool:
    if attempt >= _MAXIMUM_ATTEMPTS:
        return False
    remaining = _MAXIMUM_ELAPSED_SECONDS - (monotonic() - started)
    if remaining <= 0:
        return False
    ceiling = min(
        _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
        _MAXIMUM_BACKOFF_SECONDS,
        remaining,
    )
    delay = jitter(ceiling)
    if not 0 <= delay <= ceiling:
        raise RuntimeError("proposal read retry jitter escaped its bounded interval") from failure
    sleep(delay)
    return monotonic() - started < _MAXIMUM_ELAPSED_SECONDS


def _retryable_database_failure(error: psycopg.Error) -> bool:
    sqlstate = error.sqlstate
    return sqlstate is None or sqlstate.startswith("08") or sqlstate in _TRANSIENT_SQLSTATES


def _bounded_dsn(dsn: str) -> str:
    parameters = conninfo_to_dict(dsn)
    existing_options = parameters.get("options", "")
    timeout_option = f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}"
    return make_conninfo(
        dsn,
        connect_timeout=str(_CONNECT_TIMEOUT_SECONDS),
        options=f"{existing_options} {timeout_option}".strip(),
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
