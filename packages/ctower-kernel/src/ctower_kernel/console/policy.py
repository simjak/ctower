"""Pure Phase-1 grant and bounded-stream decisions."""

from __future__ import annotations

import base64
from collections import deque
from collections.abc import Iterator
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from ctower_kernel.console.models import (
    ConsoleGrantFacts,
    ConsoleGrantIdentifiers,
    ConsolePolicy,
    ConsoleViewGrant,
)
from ctower_kernel.record import PrincipalKind, RecordProblem

__all__ = [
    "ConsoleStreamWindow",
    "StreamDisposition",
    "decide_view_grant",
    "encode_console_chunks",
    "preflight_view_grant",
]

type _RefusalCheck = tuple[bool, str, str]


def decide_view_grant(
    facts: ConsoleGrantFacts,
    identifiers: ConsoleGrantIdentifiers,
    *,
    policy: ConsolePolicy,
    now: datetime,
    previous_grant: ConsoleViewGrant | None = None,
) -> ConsoleViewGrant | RecordProblem:
    """Decide one mint/renewal from the complete durable and live fact set."""

    refusal = _authority_refusal(facts, now=now)
    if refusal is not None:
        return refusal
    binding_id = facts.actor.human_binding_id
    session_id = facts.actor.human_session_id
    if binding_id is None or session_id is None:
        return _problem("console-browser-session-required", "An exact human session is required.")
    window = _grant_window(
        facts,
        previous_grant,
        binding_id=binding_id,
        session_id=session_id,
        policy=policy,
        now=now,
    )
    if isinstance(window, RecordProblem):
        return window
    continuous_start, renewed_from = window
    absolute_end = continuous_start + timedelta(seconds=policy.maximum_continuous_view_seconds)
    expires_at = min(now + timedelta(seconds=policy.grant_ttl_seconds), absolute_end)
    return ConsoleViewGrant(
        grant_id=identifiers.grant_id,
        nonce=identifiers.nonce,
        actor_principal_id=facts.actor.principal_id,
        human_binding_id=binding_id,
        human_session_id=session_id,
        tenant_id=facts.actor.tenant_id,
        project_key=facts.session_ref.project_key,
        allowance_id=facts.allowance_id,
        session_ref=facts.session_ref,
        policy_revision=policy.policy_revision,
        issuer="ctower-control-plane",
        not_before=now,
        expires_at=expires_at,
        maximum_uses=1,
        continuous_view_started_at=continuous_start,
        renewed_from_grant_id=renewed_from,
    )


def preflight_view_grant(facts: ConsoleGrantFacts, *, now: datetime) -> RecordProblem | None:
    """Refuse from durable authority before any runtime Adapter inspection."""

    if facts.actor.human_binding_id is None or facts.actor.human_session_id is None:
        return _problem("console-browser-session-required", "An exact human session is required.")
    for checks in (_actor_checks(facts, now=now), _session_checks(facts)):
        refusal = _first_refusal(checks)
        if refusal is not None:
            return refusal
    return None


def _grant_window(
    facts: ConsoleGrantFacts,
    previous: ConsoleViewGrant | None,
    *,
    binding_id: UUID,
    session_id: UUID,
    policy: ConsolePolicy,
    now: datetime,
) -> tuple[datetime, UUID | None] | RecordProblem:
    if previous is None:
        return now, None
    if previous.expires_at <= now:
        return _problem("console-grant-expired", "An expired grant cannot be renewed.", 401)
    bindings_match = (
        previous.actor_principal_id == facts.actor.principal_id
        and previous.human_binding_id == binding_id
        and previous.human_session_id == session_id
        and previous.allowance_id == facts.allowance_id
        and previous.session_ref == facts.session_ref
    )
    if not bindings_match:
        return _problem("console-renewal-binding-mismatch", "Renewal bindings do not match.")
    continuous_start = previous.continuous_view_started_at
    if continuous_start + timedelta(seconds=policy.maximum_continuous_view_seconds) <= now:
        return _problem(
            "console-continuous-view-limit",
            "The maximum continuous view interval has elapsed.",
            401,
        )
    return continuous_start, previous.grant_id


def _authority_refusal(facts: ConsoleGrantFacts, *, now: datetime) -> RecordProblem | None:
    refusal = preflight_view_grant(facts, now=now)
    return refusal if refusal is not None else _first_refusal(_live_checks(facts))


def _actor_checks(facts: ConsoleGrantFacts, *, now: datetime) -> tuple[_RefusalCheck, ...]:
    return (
        (
            facts.actor.kind is PrincipalKind.COMMANDER,
            "console-role-refused",
            "Commander cannot view.",
        ),
        (
            facts.session_ref.project_key not in facts.actor.project_grants,
            "console-project-refused",
            "The Actor has no exact Project grant.",
        ),
        (
            facts.suspended_until is not None and facts.suspended_until > now,
            "console-actor-suspended",
            "The Actor is temporarily suspended after repeated denials.",
        ),
    )


def _session_checks(facts: ConsoleGrantFacts) -> tuple[_RefusalCheck, ...]:
    return (
        (
            facts.global_kill_switch_enabled,
            "console-globally-disabled",
            "Console viewing is globally disabled.",
        ),
        (facts.session_revoked, "console-session-revoked", "The console session was revoked."),
        (
            not facts.allowlist_active,
            "console-session-not-allowed",
            "The exact console session is not allowlisted.",
        ),
        (
            not facts.assignment_current,
            "console-assignment-stale",
            "The exact assignment interval is no longer current.",
        ),
        (
            not facts.session_join_current,
            "console-session-join-stale",
            "The recorded session no longer joins the current assignment.",
        ),
        (
            facts.sensitivity_class != "restricted",
            "console-sensitivity-refused",
            "Phase 1 admits only the RESTRICTED class.",
        ),
        (
            facts.loop_kind != "standard",
            "console-loop-kind-refused",
            "Phase 1 refuses non-standard loop kinds.",
        ),
        (
            not facts.adapter_registered,
            "console-adapter-unregistered",
            "The backend has no registered Adapter.",
        ),
    )


def _live_checks(facts: ConsoleGrantFacts) -> tuple[_RefusalCheck, ...]:
    ref = facts.session_ref
    return (
        (
            facts.observed_project_key != ref.project_key,
            "console-project-fence-mismatch",
            "The live tmux Project fact mismatches.",
        ),
        (
            facts.observed_runtime_attempt_id != ref.runtime_attempt_id,
            "console-runtime-attempt-fenced",
            "The runtime attempt was replaced.",
        ),
        (
            facts.observed_runner_id != ref.runner_id,
            "console-runner-fenced",
            "The runner identity was replaced.",
        ),
        (
            facts.observed_runner_epoch != ref.runner_epoch,
            "console-runner-epoch-fenced",
            "The runner epoch advanced.",
        ),
        (
            facts.observed_backend_ref != ref.opaque_backend_ref,
            "console-backend-fenced",
            "The backend reference was replaced.",
        ),
        (
            facts.observed_backend_incarnation != ref.backend_incarnation,
            "console-incarnation-fenced",
            "The backend incarnation was replaced.",
        ),
    )


def _first_refusal(checks: tuple[_RefusalCheck, ...]) -> RecordProblem | None:
    for refused, code, detail in checks:
        if refused:
            status = 404 if code in {"console-project-refused", "console-role-refused"} else 403
            return _problem(code, detail, status)
    return None


def _problem(code: str, detail: str, status: int = 403) -> RecordProblem:
    return RecordProblem(code=code, detail=detail, status=status, title="Console view refused")


class StreamDisposition(StrEnum):
    """Bounded stream admission result."""

    ADMITTED = "admitted"
    RATE_LIMITED = "rate_limited"
    SLOW_CONSUMER = "slow_consumer"


class ConsoleStreamWindow:
    """Per-stream rolling delivery/replay and queued-byte accounting."""

    def __init__(
        self,
        *,
        delivery_window_bytes: int,
        delivery_window_seconds: int,
        replay_window_bytes: int,
        replay_window_seconds: int,
        pending_bytes: int,
    ) -> None:
        self._delivery = _RollingBytes(delivery_window_bytes, delivery_window_seconds)
        self._replay = _RollingBytes(replay_window_bytes, replay_window_seconds)
        self._pending_limit = pending_bytes
        self._pending = 0
        self._gap_reason: str | None = None

    @property
    def pending(self) -> int:
        return self._pending

    @property
    def gap_required(self) -> bool:
        return self._gap_reason is not None

    @property
    def gap_reason(self) -> str | None:
        return self._gap_reason

    def admit_delivery(self, size: int, *, at: datetime) -> StreamDisposition:
        return self._delivery.admit(size, at=at)

    def admit_replay(self, size: int, *, at: datetime) -> StreamDisposition:
        return self._replay.admit(size, at=at)

    def add_pending(self, size: int) -> StreamDisposition:
        if size < 0:
            raise ValueError("pending size cannot be negative")
        if self._pending + size > self._pending_limit:
            self.mark_gap("slow-consumer")
            return StreamDisposition.SLOW_CONSUMER
        self._pending += size
        return StreamDisposition.ADMITTED

    def flush_pending(self, size: int) -> None:
        if not 0 <= size <= self._pending:
            raise ValueError("pending flush exceeds queued bytes")
        self._pending -= size

    def mark_gap(self, reason: str) -> None:
        if not reason:
            raise ValueError("gap reason cannot be empty")
        self._gap_reason = reason


class _RollingBytes:
    def __init__(self, maximum: int, seconds: int) -> None:
        if maximum < 1 or seconds < 1:
            raise ValueError("rolling byte bounds must be positive")
        self._maximum = maximum
        self._seconds = seconds
        self._entries: deque[tuple[datetime, int]] = deque()
        self._total = 0

    def admit(self, size: int, *, at: datetime) -> StreamDisposition:
        if size < 0:
            raise ValueError("stream size cannot be negative")
        threshold = at - timedelta(seconds=self._seconds)
        while self._entries and self._entries[0][0] <= threshold:
            _, expired = self._entries.popleft()
            self._total -= expired
        if self._total + size > self._maximum:
            return StreamDisposition.RATE_LIMITED
        self._entries.append((at, size))
        self._total += size
        return StreamDisposition.ADMITTED


def encode_console_chunks(payload: bytes, *, decoded_chunk_bytes: int) -> Iterator[bytes]:
    """Yield independently decodable base64 chunks within the decoded-size ceiling."""

    if decoded_chunk_bytes < 1 or decoded_chunk_bytes > 16 * 1024:
        raise ValueError("decoded_chunk_bytes must be between 1 and 16384")
    for offset in range(0, len(payload), decoded_chunk_bytes):
        yield base64.b64encode(payload[offset : offset + decoded_chunk_bytes])
