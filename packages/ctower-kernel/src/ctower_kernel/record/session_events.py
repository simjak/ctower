"""Strict recorded-work-session payloads and the one authored session state machine.

A work session is a bounded stretch of accountable work on one ticket. It is a Record
fact, not a vendor handle: [INV-15](../../../../../SPEC.md) keeps process, tmux, and
provider session identifiers as optional metadata, so nothing here accepts one. The
session identity is a durable ctower UUID, and every field below is authored, bounded,
and free of credential, PHI, or personal content by contract.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

__all__ = [
    "INITIAL_SESSION_STATE",
    "SessionClosedPayload",
    "SessionEventPayload",
    "SessionOutcome",
    "SessionStartedPayload",
    "SessionState",
    "SessionTransitionedPayload",
    "session_payload_from_mapping",
    "session_transition_allowed",
]

MAX_SESSION_DURATION_SECONDS = 31_536_000
MAX_SESSION_TOKENS = 1_000_000_000
_MAX_EVIDENCE_REF = 256
_MAX_REASON = 500
_MAX_REFERENCE = 256
_MAX_HARNESS_REF = 64
_MAX_MODEL_REF = 128
_STABLE_NAME = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")


class SessionState(StrEnum):
    """The four named states a live work session can occupy."""

    DISPATCHED = "dispatched"
    BRIEFED = "briefed"
    WORKING = "working"
    GATED = "gated"


class SessionOutcome(StrEnum):
    """How a session ended, stated rather than inferred from silence."""

    DELIVERED = "delivered"
    BLOCKED = "blocked"
    ABANDONED = "abandoned"
    FAILED = "failed"


INITIAL_SESSION_STATE = SessionState.DISPATCHED

# The authored session lifecycle. A session is dispatched, then briefed, then working;
# it may reach a gate and return to work. Every other pair is refused by name, so a
# state cannot be reached by replaying a transition out of order.
_ALLOWED_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.DISPATCHED: frozenset({SessionState.BRIEFED}),
    SessionState.BRIEFED: frozenset({SessionState.WORKING}),
    SessionState.WORKING: frozenset({SessionState.GATED}),
    SessionState.GATED: frozenset({SessionState.WORKING}),
}


def session_transition_allowed(from_state: SessionState, to_state: SessionState) -> bool:
    """Return whether the authored lifecycle admits this exact state pair."""

    return to_state in _ALLOWED_TRANSITIONS[from_state]


@dataclass(frozen=True, slots=True)
class SessionStartedPayload:
    """Who started working, with what, and on which ticket."""

    branch_ref: str
    crew_name: str
    harness_ref: str
    model_ref: str
    seat_key: str
    session_id: UUID
    ticket_id: UUID
    worktree_ref: str

    def __post_init__(self) -> None:
        _uuid("session_id", self.session_id)
        _uuid("ticket_id", self.ticket_id)
        _stable("crew_name", self.crew_name)
        _stable("seat_key", self.seat_key)
        _bounded("harness_ref", self.harness_ref, maximum=_MAX_HARNESS_REF)
        _bounded("model_ref", self.model_ref, maximum=_MAX_MODEL_REF)
        _bounded("branch_ref", self.branch_ref, maximum=_MAX_REFERENCE)
        _bounded("worktree_ref", self.worktree_ref, maximum=_MAX_REFERENCE)

    def to_mapping(self) -> dict[str, object]:
        return {
            "branch_ref": self.branch_ref,
            "crew_name": self.crew_name,
            "harness_ref": self.harness_ref,
            "model_ref": self.model_ref,
            "seat_key": self.seat_key,
            "session_id": str(self.session_id),
            "ticket_id": str(self.ticket_id),
            "worktree_ref": self.worktree_ref,
        }


@dataclass(frozen=True, slots=True)
class SessionTransitionedPayload:
    """One authored state movement inside a live session."""

    from_state: str
    reason: str
    session_id: UUID
    ticket_id: UUID
    to_state: str
    transition_number: int

    def __post_init__(self) -> None:
        _uuid("session_id", self.session_id)
        _uuid("ticket_id", self.ticket_id)
        _bounded("reason", self.reason, maximum=_MAX_REASON)
        if type(self.transition_number) is not int or self.transition_number < 1:
            raise ValueError("session transition number must be a positive integer")
        if not session_transition_allowed(_state(self.from_state), _state(self.to_state)):
            raise ValueError("session transition is outside the authored lifecycle")

    def to_mapping(self) -> dict[str, object]:
        return {
            "from_state": self.from_state,
            "reason": self.reason,
            "session_id": str(self.session_id),
            "ticket_id": str(self.ticket_id),
            "to_state": self.to_state,
            "transition_number": self.transition_number,
        }


@dataclass(frozen=True, slots=True)
class SessionClosedPayload:
    """The terminal session fact: outcome plus the operator's cost facts."""

    duration_seconds: int
    evidence_ref: str | None
    input_tokens: int
    outcome: str
    output_tokens: int
    session_id: UUID
    ticket_id: UUID

    def __post_init__(self) -> None:
        _uuid("session_id", self.session_id)
        _uuid("ticket_id", self.ticket_id)
        if self.outcome not in set(SessionOutcome):
            raise ValueError("session outcome is outside the authored event contract")
        _counted("duration_seconds", self.duration_seconds, MAX_SESSION_DURATION_SECONDS)
        _counted("input_tokens", self.input_tokens, MAX_SESSION_TOKENS)
        _counted("output_tokens", self.output_tokens, MAX_SESSION_TOKENS)
        if self.evidence_ref is not None:
            _bounded("evidence_ref", self.evidence_ref, maximum=_MAX_EVIDENCE_REF)

    def to_mapping(self) -> dict[str, object]:
        return {
            "duration_seconds": self.duration_seconds,
            "evidence_ref": self.evidence_ref,
            "input_tokens": self.input_tokens,
            "outcome": self.outcome,
            "output_tokens": self.output_tokens,
            "session_id": str(self.session_id),
            "ticket_id": str(self.ticket_id),
        }


type SessionEventPayload = SessionStartedPayload | SessionTransitionedPayload | SessionClosedPayload

_SESSION_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "session.started": frozenset(
        {
            "branch_ref",
            "crew_name",
            "harness_ref",
            "model_ref",
            "seat_key",
            "session_id",
            "ticket_id",
            "worktree_ref",
        }
    ),
    "session.transitioned": frozenset(
        {"from_state", "reason", "session_id", "ticket_id", "to_state", "transition_number"}
    ),
    "session.closed": frozenset(
        {
            "duration_seconds",
            "evidence_ref",
            "input_tokens",
            "outcome",
            "output_tokens",
            "session_id",
            "ticket_id",
        }
    ),
}


def session_payload_from_mapping(kind: str, payload: Mapping[str, object]) -> SessionEventPayload:
    """Rebuild one typed session payload at the persistence read boundary."""

    expected = _SESSION_PAYLOAD_FIELDS.get(kind)
    if expected is None:
        raise ValueError(f"{kind} is not a recorded work-session event")
    if set(payload) != expected:
        raise ValueError("event payload fields do not match the authored variant")
    if kind == "session.started":
        return SessionStartedPayload(
            branch_ref=_string(payload["branch_ref"], "branch_ref"),
            crew_name=_string(payload["crew_name"], "crew_name"),
            harness_ref=_string(payload["harness_ref"], "harness_ref"),
            model_ref=_string(payload["model_ref"], "model_ref"),
            seat_key=_string(payload["seat_key"], "seat_key"),
            session_id=_uuid_value(payload["session_id"], "session_id"),
            ticket_id=_uuid_value(payload["ticket_id"], "ticket_id"),
            worktree_ref=_string(payload["worktree_ref"], "worktree_ref"),
        )
    if kind == "session.transitioned":
        return SessionTransitionedPayload(
            from_state=_string(payload["from_state"], "from_state"),
            reason=_string(payload["reason"], "reason"),
            session_id=_uuid_value(payload["session_id"], "session_id"),
            ticket_id=_uuid_value(payload["ticket_id"], "ticket_id"),
            to_state=_string(payload["to_state"], "to_state"),
            transition_number=_integer(payload["transition_number"], "transition_number"),
        )
    evidence_ref = payload["evidence_ref"]
    return SessionClosedPayload(
        duration_seconds=_integer(payload["duration_seconds"], "duration_seconds"),
        evidence_ref=None if evidence_ref is None else _string(evidence_ref, "evidence_ref"),
        input_tokens=_integer(payload["input_tokens"], "input_tokens"),
        outcome=_string(payload["outcome"], "outcome"),
        output_tokens=_integer(payload["output_tokens"], "output_tokens"),
        session_id=_uuid_value(payload["session_id"], "session_id"),
        ticket_id=_uuid_value(payload["ticket_id"], "ticket_id"),
    )


def _state(value: object) -> SessionState:
    if not isinstance(value, str) or value not in set(SessionState):
        raise ValueError("session state is outside the authored event contract")
    return SessionState(value)


def _counted(label: str, value: object, maximum: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    if not 0 <= value <= maximum:
        raise ValueError(f"{label} is outside the authored event contract")


def _bounded(label: str, value: object, *, maximum: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not 1 <= len(value) <= maximum:
        raise ValueError(f"{label} is outside the authored event contract")


def _stable(label: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if _STABLE_NAME.fullmatch(value) is None:
        raise ValueError(f"{label} is outside the authored event contract")


def _uuid(label: str, value: object) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{label} must be a UUID")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _uuid_value(value: object, label: str) -> UUID:
    return UUID(_string(value, label))


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    return value
