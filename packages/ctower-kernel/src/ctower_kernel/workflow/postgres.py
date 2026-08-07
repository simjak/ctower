"""Postgres implementation behind the Workflow Interface."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.workflow import (
    ResolveClose,
    ReviewDispatchEffect,
    Workflow,
    WorkflowActor,
    WorkflowMutation,
    WorkflowReceipt,
    WorkflowStart,
)
from ctower_kernel.workflow._close_sql import close_workflow as _close
from ctower_kernel.workflow._postgres_sql import ProofGate, WorkReadinessGate
from ctower_kernel.workflow._postgres_sql import advance_workflow as _advance
from ctower_kernel.workflow._review_dispatch_sql import review_dispatches as _review_dispatches
from ctower_kernel.workflow._start_sql import start_workflow as _start

__all__ = ["PostgresWorkflow", "PostgresWorkflowPolicyPins"]


class PostgresWorkflowPolicyPins:
    """Expose only current immutable proof pins to the composed Proof adapter."""

    def proof_policy_pin(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, str, str, str, str] | None:
        row = connection.execute(
            """
            SELECT workflow_key, workflow_revision, gate_policy_ref, gate_policy_digest,
                evidence_policy_ref, evidence_policy_digest
            FROM workflow_runs AS run
            WHERE run.tenant_id = %s AND run.ticket_id = %s
              AND run.episode_number = (
                  SELECT current_episode FROM tickets
                  WHERE tenant_id = %s AND ticket_id = %s
              )
            """,
            (tenant_id, ticket_id, tenant_id, ticket_id),
        ).fetchone()
        if row is None:
            return None
        return (
            f"{row['workflow_key']}@{row['workflow_revision']}",
            str(row["gate_policy_ref"]),
            _digest(row["gate_policy_digest"]),
            str(row["evidence_policy_ref"]),
            _digest(row["evidence_policy_digest"]),
        )


def _digest(value: object) -> str:
    return "sha256:" + bytes(cast(bytes, value)).hex()


class PostgresWorkflow:
    """Own graph/lifecycle SQL with an injected current-proof capability."""

    def __init__(
        self,
        dsn: str,
        *,
        proof_gate: ProofGate,
        readiness_gate: WorkReadinessGate,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._dsn = dsn
        self._proof_gate = proof_gate
        self._readiness_gate = readiness_gate
        self._telemetry = telemetry or NoopTelemetry()

    def advance_workflow(
        self,
        evaluator: Workflow,
        actor: WorkflowActor,
        mutation: WorkflowMutation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem:
        """Atomically persist one legal Workflow transition."""

        outcome = recover_ambiguous_commit(
            lambda: _advance(
                self._dsn,
                evaluator,
                self._proof_gate,
                self._readiness_gate,
                actor,
                mutation,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("workflow.advance", telemetry, outcome)
        return outcome

    def start_workflow(
        self,
        evaluator: Workflow,
        actor: WorkflowActor,
        command: WorkflowStart,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem:
        """Atomically persist one exact Workflow and policy pin."""

        outcome = recover_ambiguous_commit(
            lambda: _start(
                self._dsn,
                evaluator,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("workflow.start", telemetry, outcome)
        return outcome

    def close_workflow(
        self,
        evaluator: Workflow,
        actor: WorkflowActor,
        command: ResolveClose,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem:
        """Atomically append proof-gated terminal lifecycle facts."""

        outcome = recover_ambiguous_commit(
            lambda: _close(
                self._dsn,
                evaluator,
                self._proof_gate,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("workflow.close", telemetry, outcome)
        return outcome

    def review_dispatches(
        self, actor: WorkflowActor, ticket_id: UUID
    ) -> tuple[ReviewDispatchEffect, ...] | RecordProblem:
        """Return ticket-visible review dispatch joins."""

        return _review_dispatches(self._dsn, actor, ticket_id)

    def _emit(self, name: str, telemetry: TelemetryContext, outcome: object) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
