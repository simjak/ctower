"""In-memory Record test doubles for Access human-plane unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import (
    HumanBrowserSessionRecord,
    HumanRole,
    HumanRoleBindingIssue,
    HumanRoleBindingReceipt,
    HumanRoleBindingRevocation,
    HumanSessionReceipt,
)
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["FakeHumanIdentity", "FakeRecord"]


@dataclass(slots=True)
class _StoredBinding:
    binding_id: UUID
    oidc_issuer: str
    oidc_subject: str
    principal_id: UUID
    project_keys: tuple[str, ...]
    role: HumanRole


@dataclass(slots=True)
class _StoredSession:
    principal_id: UUID
    tenant_id: UUID
    binding_id: UUID
    role: HumanRole
    expires_at: datetime
    session_id: UUID
    csrf_digest: bytes


class FakeHumanIdentity:
    """Mirrors the real Postgres semantics closely enough to drive Access tests."""

    def __init__(self, *, tenant_id: UUID | None = None) -> None:
        self.tenant_id = tenant_id or uuid4()
        self._bindings: dict[UUID, _StoredBinding] = {}
        self._by_identity: dict[tuple[str, str], UUID] = {}
        self._revoked_bindings: set[UUID] = set()
        self._sessions: dict[bytes, _StoredSession] = {}
        self._revoked_sessions: set[bytes] = set()

    def bind_role(
        self,
        actor: Actor,
        command: HumanRoleBindingIssue,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem:
        del request_digest, now, telemetry
        if actor.kind is not PrincipalKind.OPERATOR:
            return _problem("human-role-binding-refused", 403, "operator only")
        identity = (command.oidc_issuer, command.oidc_subject)
        existing = self._by_identity.get(identity)
        if existing is not None and existing not in self._revoked_bindings:
            return _problem("human-role-binding-active", 409, "already bound")
        binding = _StoredBinding(
            binding_id=uuid4(),
            oidc_issuer=command.oidc_issuer,
            oidc_subject=command.oidc_subject,
            principal_id=uuid4(),
            project_keys=command.project_keys,
            role=command.role,
        )
        self._bindings[binding.binding_id] = binding
        self._by_identity[identity] = binding.binding_id
        return _receipt(binding, state="active", command_id=command.client_command_id)

    def revoke_role(
        self,
        actor: Actor,
        command: HumanRoleBindingRevocation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem:
        del request_digest, now, telemetry
        if actor.kind is not PrincipalKind.OPERATOR:
            return _problem("human-role-binding-refused", 403, "operator only")
        binding = self._bindings.get(command.binding_id)
        if binding is None:
            return _problem("human-role-binding-unavailable", 404, "missing")
        if command.binding_id in self._revoked_bindings:
            return _problem("human-role-binding-already-revoked", 409, "already revoked")
        self._revoked_bindings.add(command.binding_id)
        return _receipt(binding, state="revoked", command_id=command.client_command_id)

    def resolve_role_binding(
        self, oidc_issuer: str, oidc_subject: str
    ) -> tuple[UUID, Actor] | None:
        binding_id = self._by_identity.get((oidc_issuer, oidc_subject))
        if binding_id is None or binding_id in self._revoked_bindings:
            return None
        binding = self._bindings[binding_id]
        actor = Actor(
            principal_id=binding.principal_id,
            tenant_id=self.tenant_id,
            kind=PrincipalKind(binding.role),
            project_grants=frozenset(binding.project_keys),
        )
        return binding_id, actor

    def issue_session(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        binding_id: UUID,
        role: HumanRole,
        *,
        session_digest: bytes,
        csrf_digest: bytes,
        now: datetime,
        ttl_seconds: int,
    ) -> HumanSessionReceipt:
        expires_at = now + timedelta(seconds=ttl_seconds)
        session_id = uuid4()
        self._sessions[session_digest] = _StoredSession(
            principal_id=principal_id,
            tenant_id=tenant_id,
            binding_id=binding_id,
            role=role,
            expires_at=expires_at,
            session_id=session_id,
            csrf_digest=csrf_digest,
        )
        return HumanSessionReceipt(
            binding_id=binding_id,
            expires_at=expires_at,
            principal_id=principal_id,
            role=role,
            session_id=session_id,
        )

    def actor_for_session(
        self, session_digest: bytes, *, now: datetime
    ) -> Actor | RecordProblem | None:
        if session_digest in self._revoked_sessions:
            return _problem("auth-session-invalid", 401, "revoked")
        session = self._sessions.get(session_digest)
        if session is None:
            return None
        if session.expires_at <= now:
            return _problem("reauthentication-required", 401, "expired")
        return Actor(
            principal_id=session.principal_id,
            tenant_id=session.tenant_id,
            kind=PrincipalKind(session.role),
            human_binding_id=session.binding_id,
            human_session_id=session.session_id,
        )

    def browser_session(
        self,
        session_digest: bytes,
        csrf_digest: bytes,
        *,
        now: datetime,
    ) -> HumanBrowserSessionRecord | RecordProblem | None:
        actor = self.actor_for_session(session_digest, now=now)
        if actor is None or isinstance(actor, RecordProblem):
            return actor
        session = self._sessions[session_digest]
        if session.csrf_digest != csrf_digest:
            return _problem("auth-csrf-invalid", 403, "csrf mismatch")
        return HumanBrowserSessionRecord(
            actor=actor,
            binding_id=session.binding_id,
            session_id=session.session_id,
        )

    def revoke_session(self, session_digest: bytes, *, reason: str, now: datetime) -> None:
        del reason, now
        self._revoked_sessions.add(session_digest)

    def is_session_revoked(self, session_digest: bytes) -> bool:
        return session_digest in self._revoked_sessions


@dataclass(slots=True)
class FakeRecord:
    """The minimal `Record`-shaped surface Access's human plane actually touches."""

    human_identity: FakeHumanIdentity = field(default_factory=FakeHumanIdentity)


def _receipt(
    binding: _StoredBinding, *, state: Literal["active", "revoked"], command_id: UUID
) -> HumanRoleBindingReceipt:
    return HumanRoleBindingReceipt(
        binding_id=binding.binding_id,
        command_id=command_id,
        oidc_issuer=binding.oidc_issuer,
        oidc_subject=binding.oidc_subject,
        principal_id=binding.principal_id,
        project_keys=binding.project_keys,
        role=binding.role,
        state=state,
    )


def _problem(code: str, status: int, detail: str) -> RecordProblem:
    return RecordProblem(code=code, detail=detail, status=status, title=detail)
