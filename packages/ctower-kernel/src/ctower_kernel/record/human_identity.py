"""Typed human OIDC role-binding commands, receipts, and session records.

A human role binding is an operator-issued, append-only grant that maps one verified
``(oidc_issuer, oidc_subject)`` identity to exactly one of the three v1 human roles. It is
disjoint from a project-seat credential grant: it confers no ``capture|transition|evidence``
scope, only the coarse role that D31 authorizes. A session is a short-lived, revocable
pointer to one active binding, minted after a successful PKCE login.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from ctower_kernel.record.interface import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = [
    "HUMAN_ROLES",
    "HumanIdentityRecord",
    "HumanIdentityStore",
    "HumanRole",
    "HumanRoleBindingIssue",
    "HumanRoleBindingReceipt",
    "HumanRoleBindingRevocation",
    "HumanSessionReceipt",
]

type HumanRole = Literal["operator", "commander", "viewer"]

HUMAN_ROLES: frozenset[str] = frozenset({"operator", "commander", "viewer"})

_ISSUER_MAX = 512
_SUBJECT_MAX = 255
_MAX_DISPLAY_NAME = 120
_MAX_REASON = 500
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


@dataclass(frozen=True, slots=True)
class HumanRoleBindingIssue:
    """Operator request to bind one verified ``(issuer, subject)`` to a human role."""

    client_command_id: UUID
    display_name: str
    oidc_issuer: str
    oidc_subject: str
    project_keys: tuple[str, ...]
    role: HumanRole

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID):
            raise TypeError("human role binding command ID must be a UUID")
        if not 1 <= len(self.display_name) <= _MAX_DISPLAY_NAME:
            raise ValueError("human role binding display name is outside the authored contract")
        if not 1 <= len(self.oidc_issuer) <= _ISSUER_MAX:
            raise ValueError("human role binding issuer is outside the authored contract")
        if not 1 <= len(self.oidc_subject) <= _SUBJECT_MAX:
            raise ValueError("human role binding subject is outside the authored contract")
        if self.role not in HUMAN_ROLES:
            raise ValueError("human role binding role must be operator, commander, or viewer")
        if any(_PROJECT_KEY.fullmatch(key) is None for key in self.project_keys):
            raise ValueError("human role binding project keys are outside the authored contract")
        if len(set(self.project_keys)) != len(self.project_keys):
            raise ValueError("human role binding project keys must be unique")

    def request_payload(self) -> dict[str, object]:
        return {
            "display_name": self.display_name,
            "oidc_issuer": self.oidc_issuer,
            "oidc_subject": self.oidc_subject,
            "project_keys": list(self.project_keys),
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class HumanRoleBindingRevocation:
    """Operator request to revoke one exact human role binding."""

    binding_id: UUID
    client_command_id: UUID
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.binding_id, UUID):
            raise TypeError("human role binding revocation IDs must be UUIDs")
        if not 1 <= len(self.reason) <= _MAX_REASON:
            raise ValueError(
                "human role binding revocation reason is outside the authored contract"
            )

    def request_payload(self) -> dict[str, object]:
        return {"binding_id": str(self.binding_id), "reason": self.reason}


@dataclass(frozen=True, slots=True)
class HumanRoleBindingReceipt:
    """Public receipt for one human role binding issuance or revocation."""

    binding_id: UUID
    command_id: UUID
    oidc_issuer: str
    oidc_subject: str
    principal_id: UUID
    project_keys: tuple[str, ...]
    role: HumanRole
    state: Literal["active", "revoked"]

    def response_payload(self) -> dict[str, object]:
        return {
            "binding_id": str(self.binding_id),
            "command_id": str(self.command_id),
            "oidc_issuer": self.oidc_issuer,
            "oidc_subject": self.oidc_subject,
            "principal_id": str(self.principal_id),
            "project_keys": list(self.project_keys),
            "role": self.role,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class HumanSessionReceipt:
    """Internal receipt for one issued human session; never carries the bearer value."""

    binding_id: UUID
    expires_at: datetime
    principal_id: UUID
    role: HumanRole
    session_id: UUID


class HumanIdentityStore(Protocol):
    """Cohesive persistence boundary for human role bindings and their sessions."""

    def bind_role(
        self,
        actor: Actor,
        command: HumanRoleBindingIssue,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem: ...

    def revoke_role(
        self,
        actor: Actor,
        command: HumanRoleBindingRevocation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> HumanRoleBindingReceipt | RecordProblem: ...

    def resolve_role_binding(
        self, oidc_issuer: str, oidc_subject: str
    ) -> tuple[UUID, Actor] | None: ...

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
    ) -> HumanSessionReceipt: ...

    def actor_for_session(
        self, session_digest: bytes, *, now: datetime
    ) -> Actor | RecordProblem | None: ...

    def revoke_session(self, session_digest: bytes, *, reason: str, now: datetime) -> None: ...


class HumanIdentityRecord(Protocol):
    """The minimal Record-shaped surface the human OIDC plane actually touches."""

    human_identity: HumanIdentityStore
