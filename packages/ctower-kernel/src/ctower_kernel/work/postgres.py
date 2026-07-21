"""Postgres implementation behind the Work Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import AssignmentInterval, WorkCommand, WorkReadiness, WorkReceipt
from ctower_kernel.work._postgres_sql import assignments as _assignments
from ctower_kernel.work._postgres_sql import execute_work as _execute
from ctower_kernel.work._postgres_sql import readiness as _readiness
from ctower_kernel.work._postgres_sql import unmet_readiness as _unmet_readiness

__all__ = ["PostgresWork"]


class PostgresWork:
    """Persist authoritative Work facts while Record owns append choreography."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def execute_work(
        self,
        actor: Actor,
        command: WorkCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkReceipt | RecordProblem:
        return _execute(
            self._dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )

    def assignments(
        self, actor: Actor, ticket_id: UUID
    ) -> tuple[AssignmentInterval, ...] | RecordProblem:
        return _assignments(self._dsn, actor, ticket_id)

    def readiness(self, actor: Actor, ticket_id: UUID) -> WorkReadiness | RecordProblem:
        return _readiness(self._dsn, actor, ticket_id)

    def unmet_facts(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, ...]:
        """Supply Workflow a narrow same-transaction readiness observation."""

        return _unmet_readiness(connection, tenant_id, ticket_id)
