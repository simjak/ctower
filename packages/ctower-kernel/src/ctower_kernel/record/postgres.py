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
    DurabilityDecision,
    DurabilityFinalizationBatch,
    DurabilityHealth,
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
from ctower_kernel.record._command_root import command_snapshot as _command_snapshot
from ctower_kernel.record._comment_sql import add_comment as _add_comment
from ctower_kernel.record._custody_sql import transfer_custody as _transfer_custody
from ctower_kernel.record._durability_finalizer_sql import (
    FinalizerCursor,
)
from ctower_kernel.record._durability_finalizer_sql import (
    finalize_pending as _finalize_pending,
)
from ctower_kernel.record._durability_health_sql import durability_health as _durability_health
from ctower_kernel.record._durability_sql import reconcile_durability as _reconcile_durability
from ctower_kernel.record._intake_sql import promote_intake as _promote_intake
from ctower_kernel.record._intake_sql import submit_intake as _submit_intake
from ctower_kernel.record._setup_sql import (
    RecoveryRoleConfigurationError,
    apply_migrations,
    configure_development_durability,
    provision_bootstrap,
    provision_database_roles,
    provision_principal_credential,
)
from ctower_kernel.record._ticket_sql import actor_for_credential as _actor_for_credential
from ctower_kernel.record._ticket_sql import create_ticket as _create_ticket
from ctower_kernel.record._ticket_sql import get_ticket as _get_ticket
from ctower_kernel.record._ticket_sql import ticket_timeline as _ticket_timeline
from ctower_kernel.record.comments import TicketCommentCommand, TicketCommentResult
from ctower_kernel.record.intake import (
    IntakeCommandResult,
    IntakePromotionCommand,
    IntakeSubmitCommand,
)
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = [
    "PostgresDurabilityFinalizer",
    "PostgresRecord",
    "RecoveryRoleConfigurationError",
    "apply_migrations",
    "configure_development_durability",
    "provision_bootstrap",
    "provision_database_roles",
    "provision_principal_credential",
]

_BOOTSTRAP_SERIALIZATION_ATTEMPTS = 3


class PostgresDurabilityFinalizer:
    """Ordinary bounded finalizer over the Record durability authority."""

    def __init__(
        self,
        primary_dsn: str,
        *,
        standby_dsn: str | None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._primary_dsn = primary_dsn
        self._standby_dsn = standby_dsn
        self._telemetry = telemetry
        self._cursor: FinalizerCursor | None = None

    def finalize_pending(self, *, limit: int = 100) -> DurabilityFinalizationBatch:
        """Reconcile the oldest incomplete command receipts."""

        batch, self._cursor = _finalize_pending(
            self._primary_dsn,
            self._standby_dsn,
            limit=limit,
            after=self._cursor,
            telemetry=self._telemetry,
        )
        return batch


class PostgresRecord:
    """Password-agnostic Postgres implementation of atomic Record commands."""

    def __init__(
        self,
        dsn: str,
        *,
        standby_dsn: str | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._dsn = dsn
        self._standby_dsn = standby_dsn
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

        outcome = recover_ambiguous_commit(
            lambda: self._bootstrap_attempt(
                command,
                capability_digest=capability_digest,
                request_digest=request_digest,
                origin=origin,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("record.bootstrap_first_tenant", telemetry, outcome)
        return outcome

    def _bootstrap_attempt(
        self,
        command: BootstrapCommand,
        *,
        capability_digest: bytes,
        request_digest: bytes,
        origin: str,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> BootstrapReceipt | RecordProblem:
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
        policy_refusal: RecordProblem | None = None,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult | RecordProblem:
        """Append or replay one ticket transaction."""

        outcome = recover_ambiguous_commit(
            lambda: _create_ticket(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                policy_refusal=policy_refusal,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("record.create_ticket", telemetry, outcome)
        return outcome

    def submit_intake(
        self,
        actor: Actor,
        command: IntakeSubmitCommand,
        *,
        request_digest: bytes,
        policy_refusal: RecordProblem | None = None,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult | RecordProblem:
        """Record an inbound event before applying its explicit semantic intent."""

        outcome = recover_ambiguous_commit(
            lambda: _submit_intake(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                policy_refusal=policy_refusal,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("record.submit_intake", telemetry, outcome)
        return outcome

    def promote_intake(
        self,
        actor: Actor,
        command: IntakePromotionCommand,
        *,
        request_digest: bytes,
        policy_refusal: RecordProblem | None = None,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult | RecordProblem:
        """Attach one prior inbound event to exactly one ticket."""

        outcome = recover_ambiguous_commit(
            lambda: _promote_intake(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                policy_refusal=policy_refusal,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("record.promote_intake", telemetry, outcome)
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

        outcome = recover_ambiguous_commit(
            lambda: _transfer_custody(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("record.transfer_custody", telemetry, outcome)
        return outcome

    def add_comment(
        self,
        actor: Actor,
        command: TicketCommentCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommentResult | RecordProblem:
        """Atomically append or exactly replay one ticket comment."""

        outcome = recover_ambiguous_commit(
            lambda: _add_comment(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
        self._emit("record.add_comment", telemetry, outcome)
        return outcome

    def reconcile_durability(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        *,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> DurabilityDecision | RecordProblem:
        """Reconcile one command against the configured named standby."""

        outcome = _reconcile_durability(
            self._dsn,
            self._standby_dsn,
            tenant_id,
            principal_id,
            command_id,
            now=now,
        )
        self._emit("record.reconcile_durability", telemetry, outcome)
        return outcome

    def command_root(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
    ) -> bytes | RecordProblem:
        """Read the exact canonical root used by durability evidence fixtures."""

        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute("SET ROLE ctower_svc")
            snapshot = _command_snapshot(connection, tenant_id, principal_id, command_id)
        if isinstance(snapshot, RecordProblem):
            return snapshot
        return snapshot.root

    def durability_health(self, *, now: datetime) -> DurabilityHealth:
        """Read the fail-closed durability target health snapshot."""

        return _durability_health(self._dsn, self._standby_dsn, now=now)

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
