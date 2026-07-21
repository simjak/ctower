"""Postgres Adapter implementing the kernel's atomic Record Interface."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import (
    Actor,
    AuditPage,
    BootstrapCommand,
    BootstrapReceipt,
    CustodyCommand,
    RecordProblem,
    Ticket,
    TicketCommand,
    TicketCommandResult,
    TicketTimeline,
)
from ctower_kernel.record._audit_sql import ticket_audit as _ticket_audit
from ctower_kernel.record._bootstrap_sql import (
    bootstrap_problem,
    bootstrap_transaction,
)
from ctower_kernel.record._custody_sql import transfer_custody as _transfer_custody
from ctower_kernel.record._setup_sql import (
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)
from ctower_kernel.record._ticket_sql import actor_for_credential as _actor_for_credential
from ctower_kernel.record._ticket_sql import create_ticket as _create_ticket
from ctower_kernel.record._ticket_sql import get_ticket as _get_ticket
from ctower_kernel.record._ticket_sql import ticket_timeline as _ticket_timeline
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = [
    "PostgresRecord",
    "apply_migrations",
    "provision_bootstrap",
    "provision_database_roles",
]

_BOOTSTRAP_SERIALIZATION_ATTEMPTS = 3


class PostgresRecord:
    """Password-agnostic Postgres implementation of atomic Record commands."""

    def __init__(self, dsn: str, *, telemetry: Telemetry | None = None) -> None:
        self._dsn = dsn
        self._telemetry = telemetry or NoopTelemetry()

    def authorize_bootstrap(
        self, capability_digest: bytes, *, origin: str, now: datetime
    ) -> RecordProblem | None:
        """Preauthorize raw bootstrap transport fields without mutation."""

        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute("SET ROLE ctower_svc")
            capability = connection.execute(
                """
                SELECT capability_digest, host(allowed_origin) AS allowed_origin, expires_at,
                    consumed_at
                FROM bootstrap_capability WHERE singleton
                """
            ).fetchone()
        if capability is None or not hmac.compare_digest(
            bytes(cast(bytes, capability["capability_digest"])), capability_digest
        ):
            return _transport_problem("unauthorized", 401, "Bootstrap capability refused")
        if capability["allowed_origin"] != origin:
            return _transport_problem("bootstrap-origin", 403, "Bootstrap origin refused")
        if capability["consumed_at"] is None and cast(datetime, capability["expires_at"]) <= now:
            return _transport_problem("bootstrap-expired", 410, "Bootstrap capability expired")
        return None

    def bootstrap_first_tenant(
        self,
        command: BootstrapCommand,
        *,
        capability_digest: bytes,
        request_digest: bytes,
        origin: str,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> BootstrapReceipt | RecordProblem:
        """Serialize, deduplicate, and commit the complete trust root."""

        for attempt in range(_BOOTSTRAP_SERIALIZATION_ATTEMPTS):
            try:
                outcome = bootstrap_transaction(
                    self._dsn,
                    command,
                    capability_digest=capability_digest,
                    request_digest=request_digest,
                    origin=origin,
                    now=now,
                    telemetry=telemetry,
                )
                break
            except psycopg.errors.SerializationFailure:
                if attempt + 1 == _BOOTSTRAP_SERIALIZATION_ATTEMPTS:
                    outcome = bootstrap_problem(
                        command,
                        "bootstrap-consumed",
                        409,
                        "Bootstrap lost a concurrent serialization race",
                    )
        self._emit("record.bootstrap_first_tenant", telemetry, outcome)
        return outcome

    def actor_for_credential(self, credential_digest: bytes) -> Actor | None:
        """Resolve one active principal through the credential index."""

        return _actor_for_credential(self._dsn, credential_digest)

    def create_ticket(
        self,
        actor: Actor,
        command: TicketCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult | RecordProblem:
        """Append or replay one ticket transaction."""

        outcome = _create_ticket(
            self._dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        self._emit("record.create_ticket", telemetry, outcome)
        return outcome

    def get_ticket(
        self, actor: Actor, ticket_id: UUID, *, telemetry: TelemetryContext
    ) -> Ticket | RecordProblem:
        """Read one tenant-scoped ticket."""

        outcome = _get_ticket(self._dsn, actor, ticket_id, telemetry=telemetry)
        self._emit("record.get_ticket", telemetry, outcome)
        return outcome

    def ticket_timeline(
        self, actor: Actor, ticket_id: UUID, *, telemetry: TelemetryContext
    ) -> TicketTimeline | RecordProblem:
        """Read one tenant-scoped event timeline."""

        outcome = _ticket_timeline(self._dsn, actor, ticket_id, telemetry=telemetry)
        self._emit("record.ticket_timeline", telemetry, outcome)
        return outcome

    def ticket_audit(
        self,
        actor: Actor,
        ticket_id: UUID,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> AuditPage | RecordProblem:
        """Read explicitly linked cross-aggregate events by global position."""

        outcome = _ticket_audit(self._dsn, actor, ticket_id, cursor=cursor, limit=limit)
        self._emit("record.ticket_audit", telemetry, outcome)
        return outcome

    def transfer_custody(
        self,
        actor: Actor,
        command: CustodyCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult | RecordProblem:
        """Atomically replace one current ticket custodian."""

        outcome = _transfer_custody(
            self._dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        self._emit("record.transfer_custody", telemetry, outcome)
        return outcome

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: object,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


def _transport_problem(code: str, status: int, title: str) -> RecordProblem:
    return RecordProblem(code=code, detail=title, status=status, title=title)
