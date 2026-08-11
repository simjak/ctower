"""Strict Phase-1 console authority and Adapter boundary values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from ctower_kernel.record import Actor

__all__ = [
    "ConsoleBackendObservation",
    "ConsoleCiphertext",
    "ConsoleGlobalSwitchCommand",
    "ConsoleGrantFacts",
    "ConsoleGrantIdentifiers",
    "ConsoleOutputBatch",
    "ConsolePolicy",
    "ConsoleSessionAllowCommand",
    "ConsoleSessionAllowance",
    "ConsoleSessionRef",
    "ConsoleSessionRevocation",
    "ConsoleStreamLease",
    "ConsoleViewGrant",
    "StoredConsoleGap",
    "StoredConsoleOutput",
    "StreamCloseCode",
]

type StreamCloseCode = Literal[
    "expired",
    "revoked",
    "fenced",
    "rate_limited",
    "slow_consumer",
    "reauthentication_required",
    "globally_disabled",
    "output_unavailable",
    "client_disconnected",
]

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_CREW_NAME = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._:-]{1,127}$")
_REVISION = re.compile(r"^[a-z][a-z0-9._-]{2,127}$")
_MAX_INT32 = 2_147_483_647
_MAX_INT64 = 9_223_372_036_854_775_807
_MAX_BACKEND_REF = 256
_MAX_INCARNATION = 128
_MAX_REASON = 500


@dataclass(frozen=True, slots=True)
class ConsolePolicy:
    """All Phase-1 bounds; deployment must state every field explicitly."""

    grant_ttl_seconds: int
    maximum_continuous_view_seconds: int
    revocation_poll_seconds: int
    decoded_chunk_bytes: int
    delivery_window_bytes: int
    delivery_window_seconds: int
    replay_window_bytes: int
    replay_window_seconds: int
    pending_bytes: int
    denial_limit: int
    denial_window_seconds: int
    suspension_seconds: int
    policy_revision: str

    def __post_init__(self) -> None:
        ceilings = {
            "grant_ttl_seconds": (self.grant_ttl_seconds, 300),
            "maximum_continuous_view_seconds": (self.maximum_continuous_view_seconds, 1_800),
            "revocation_poll_seconds": (self.revocation_poll_seconds, 5),
            "decoded_chunk_bytes": (self.decoded_chunk_bytes, 16 * 1024),
            "delivery_window_bytes": (self.delivery_window_bytes, 1024 * 1024),
            "delivery_window_seconds": (self.delivery_window_seconds, 60),
            "replay_window_bytes": (self.replay_window_bytes, 1024 * 1024),
            "replay_window_seconds": (self.replay_window_seconds, 60),
            "pending_bytes": (self.pending_bytes, 256 * 1024),
            "denial_limit": (self.denial_limit, 3),
            "denial_window_seconds": (self.denial_window_seconds, 300),
            "suspension_seconds": (self.suspension_seconds, 900),
        }
        for field, (value, ceiling) in ceilings.items():
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= ceiling:
                raise ValueError(f"{field} must be between 1 and {ceiling}")
        if _REVISION.fullmatch(self.policy_revision) is None:
            raise ValueError("policy_revision is outside the authored contract")


@dataclass(frozen=True, slots=True)
class ConsoleSessionRef:
    """Exact durable-to-runtime identity for one viewable crew session."""

    tenant_id: UUID
    project_key: str
    seat_principal_id: UUID
    crew_name: str
    assignment_ticket_id: UUID
    assignment_kind: str
    assignment_interval_sequence: int
    recorded_work_session_id: UUID
    runtime_attempt_id: UUID
    runner_id: str
    runner_epoch: int
    adapter_key: str
    opaque_backend_ref: str
    backend_incarnation: str

    def __post_init__(self) -> None:
        uuid_fields = (
            self.tenant_id,
            self.seat_principal_id,
            self.assignment_ticket_id,
            self.recorded_work_session_id,
            self.runtime_attempt_id,
        )
        if any(not isinstance(value, UUID) for value in uuid_fields):
            raise TypeError("ConsoleSessionRef UUID fields must be UUIDs")
        if _PROJECT_KEY.fullmatch(self.project_key) is None:
            raise ValueError("project_key is outside the authored contract")
        if _CREW_NAME.fullmatch(self.crew_name) is None:
            raise ValueError("crew_name is outside the authored contract")
        for name, value in (
            ("assignment_kind", self.assignment_kind),
            ("runner_id", self.runner_id),
            ("adapter_key", self.adapter_key),
        ):
            if _STABLE_KEY.fullmatch(value) is None:
                raise ValueError(f"{name} is outside the authored contract")
        if not 1 <= self.assignment_interval_sequence <= _MAX_INT32:
            raise ValueError("assignment_interval_sequence is outside the authored contract")
        if not 1 <= self.runner_epoch <= _MAX_INT64:
            raise ValueError("runner_epoch is outside the authored contract")
        if not 1 <= len(self.opaque_backend_ref) <= _MAX_BACKEND_REF:
            raise ValueError("opaque_backend_ref is outside the authored contract")
        if not 1 <= len(self.backend_incarnation) <= _MAX_INCARNATION:
            raise ValueError("backend_incarnation is outside the authored contract")


@dataclass(frozen=True, slots=True)
class ConsoleBackendObservation:
    """Live facts returned by a registered runtime Adapter."""

    project_key: str
    runtime_attempt_id: UUID
    runner_id: str
    runner_epoch: int
    opaque_backend_ref: str
    backend_incarnation: str


@dataclass(frozen=True, slots=True)
class ConsoleOutputBatch:
    """One cursor-addressed raw Adapter read; bytes remain RESTRICTED."""

    payload: bytes
    source_cursor: int
    gap: bool = False
    gap_reason: str | None = None

    def __post_init__(self) -> None:
        if self.source_cursor < 0:
            raise ValueError("source_cursor cannot be negative")
        if self.gap != (self.gap_reason is not None):
            raise ValueError("gap and gap_reason must be present together")


@dataclass(frozen=True, slots=True)
class ConsoleGrantFacts:
    """Complete persisted and live fact set used by one grant decision."""

    actor: Actor
    allowance_id: UUID
    session_ref: ConsoleSessionRef
    allowlist_active: bool
    assignment_current: bool
    session_join_current: bool
    adapter_registered: bool
    global_kill_switch_enabled: bool
    sensitivity_class: str
    loop_kind: str
    observed_project_key: str
    observed_runtime_attempt_id: UUID
    observed_runner_id: str
    observed_runner_epoch: int
    observed_backend_ref: str
    observed_backend_incarnation: str
    session_revoked: bool
    suspended_until: datetime | None
    human_session_current: bool
    human_binding_current: bool


@dataclass(frozen=True, slots=True)
class ConsoleGrantIdentifiers:
    """Authority-minted unpredictable identifiers supplied to the pure decision."""

    grant_id: UUID
    nonce: UUID


@dataclass(frozen=True, slots=True)
class ConsoleViewGrant:
    """Exact short-lived browser view authority persisted server-side."""

    grant_id: UUID
    nonce: UUID
    actor_principal_id: UUID
    human_binding_id: UUID
    human_session_id: UUID
    tenant_id: UUID
    project_key: str
    allowance_id: UUID
    session_ref: ConsoleSessionRef
    policy_revision: str
    issuer: Literal["ctower-control-plane"]
    not_before: datetime
    expires_at: datetime
    maximum_uses: Literal[1]
    continuous_view_started_at: datetime
    renewed_from_grant_id: UUID | None


@dataclass(frozen=True, slots=True)
class ConsoleSessionAllowCommand:
    """Operator request to expose one exact current session to grant decisions."""

    session_ref: ConsoleSessionRef
    sensitivity_class: Literal["restricted"]
    loop_kind: Literal["standard"]


@dataclass(frozen=True, slots=True)
class ConsoleSessionAllowance:
    """Secret-free receipt for one appended allowlist fact."""

    allowance_id: UUID
    tenant_id: UUID
    project_key: str
    recorded_work_session_id: UUID
    crew_name: str
    allowed_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "console_session_id": str(self.allowance_id),
            "project_key": self.project_key,
            "recorded_work_session_id": str(self.recorded_work_session_id),
            "crew_name": self.crew_name,
            "allowed_at": self.allowed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ConsoleSessionRevocation:
    """Operator request to append one exact session revocation."""

    allowance_id: UUID
    reason: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.reason) <= _MAX_REASON:
            raise ValueError("console revocation reason is outside the authored contract")


@dataclass(frozen=True, slots=True)
class ConsoleGlobalSwitchCommand:
    """Operator request to append the next global kill-switch fact."""

    enabled: bool
    reason: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.reason) <= _MAX_REASON:
            raise ValueError("console kill-switch reason is outside the authored contract")


@dataclass(frozen=True, slots=True)
class ConsoleStreamLease:
    """One append-only, single-use SSE stream claim."""

    stream_id: UUID
    grant: ConsoleViewGrant
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class StoredConsoleOutput:
    """Encrypted durable cursor returned only through the output-reader role."""

    cursor: int
    source_cursor: int
    source_generation: int
    decoded_bytes: int
    object_sha256: bytes
    envelope: ConsoleCiphertext


@dataclass(frozen=True, slots=True)
class StoredConsoleGap:
    """Durable continuity break replayed in the shared SSE cursor order."""

    cursor: int
    source_cursor: int
    source_generation: int
    reason: Literal[
        "cursor_unavailable",
        "source_truncated",
        "unprovable_range",
        "slow_consumer",
        "rate_limited",
    ]


@dataclass(frozen=True, slots=True)
class ConsoleCiphertext:
    """Envelope-encrypted output object; plaintext and key values never persist."""

    object_id: UUID
    ciphertext: bytes
    content_nonce: bytes
    wrapped_data_key: bytes
    wrapping_nonce: bytes
    wrapping_key_reference: str
    data_key_reference: UUID
