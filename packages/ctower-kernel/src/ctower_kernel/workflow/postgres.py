"""Postgres implementation behind the Workflow Interface."""

from __future__ import annotations

from datetime import datetime

from ctower_kernel.record import RecordProblem
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.workflow import (
    ResolveClose,
    Workflow,
    WorkflowActor,
    WorkflowMutation,
    WorkflowReceipt,
)
from ctower_kernel.workflow._postgres_sql import ProofGate
from ctower_kernel.workflow._postgres_sql import advance_workflow as _advance
from ctower_kernel.workflow._postgres_sql import close_workflow as _close

__all__ = ["PostgresWorkflow"]


class PostgresWorkflow:
    """Own graph/lifecycle SQL with an injected current-proof capability."""

    def __init__(
        self,
        dsn: str,
        *,
        proof_gate: ProofGate,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._dsn = dsn
        self._proof_gate = proof_gate
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

        outcome = _advance(
            self._dsn,
            evaluator,
            self._proof_gate,
            actor,
            mutation,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        self._emit("workflow.advance", telemetry, outcome)
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

        outcome = _close(
            self._dsn,
            evaluator,
            self._proof_gate,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        self._emit("workflow.close", telemetry, outcome)
        return outcome

    def _emit(self, name: str, telemetry: TelemetryContext, outcome: object) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
