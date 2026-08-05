"""Postgres adapter for the cohesive human role-binding/session boundary."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.record._human_identity_sql import actor_for_session as _actor_for_session
from ctower_kernel.record._human_identity_sql import bind_human_role as _bind_human_role
from ctower_kernel.record._human_identity_sql import issue_human_session as _issue_human_session
from ctower_kernel.record._human_identity_sql import (
    resolve_human_role_binding as _resolve_human_role_binding,
)
from ctower_kernel.record._human_identity_sql import revoke_human_role as _revoke_human_role
from ctower_kernel.record._human_identity_sql import revoke_human_session as _revoke_human_session
from ctower_kernel.record.human_identity import (
    HumanRole,
    HumanRoleBindingIssue,
    HumanRoleBindingReceipt,
    HumanRoleBindingRevocation,
    HumanSessionReceipt,
)
from ctower_kernel.record.interface import Actor, RecordProblem
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import Telemetry, TelemetryContext

__all__ = ["PostgresHumanIdentity"]


class PostgresHumanIdentity:
    """Postgres adapter for the cohesive human role-binding/session boundary."""

    def __init__(self, dsn: str, *, telemetry: Telemetry) -> None:
        self._dsn = dsn
        self._telemetry = telemetry

    def bind_role(
        self,
        actor: Actor,
        command: HumanRoleBindingIssue,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem:
        outcome = recover_ambiguous_commit(
            lambda: _bind_human_role(
                self._dsn, actor, command, request_digest=request_digest, now=now
            )
        )
        self._emit("record.bind_human_role", telemetry, outcome)
        return outcome

    def revoke_role(
        self,
        actor: Actor,
        command: HumanRoleBindingRevocation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem:
        outcome = recover_ambiguous_commit(
            lambda: _revoke_human_role(
                self._dsn, actor, command, request_digest=request_digest, now=now
            )
        )
        self._emit("record.revoke_human_role", telemetry, outcome)
        return outcome

    def resolve_role_binding(
        self, oidc_issuer: str, oidc_subject: str
    ) -> tuple[UUID, Actor] | None:
        return _resolve_human_role_binding(self._dsn, oidc_issuer, oidc_subject)

    def issue_session(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        binding_id: UUID,
        role: HumanRole,
        *,
        session_digest: bytes,
        now: datetime,
        ttl_seconds: int,
    ) -> HumanSessionReceipt:
        return _issue_human_session(
            self._dsn,
            principal_id,
            tenant_id,
            binding_id,
            role,
            session_digest=session_digest,
            now=now,
            ttl_seconds=ttl_seconds,
        )

    def actor_for_session(
        self, session_digest: bytes, *, now: datetime
    ) -> Actor | RecordProblem | None:
        return _actor_for_session(self._dsn, session_digest, now=now)

    def revoke_session(self, session_digest: bytes, *, reason: str, now: datetime) -> None:
        _revoke_human_session(self._dsn, session_digest, reason=reason, now=now)

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: HumanRoleBindingReceipt | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
