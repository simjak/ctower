"""Typed recorded-work-session commands, receipts, and read models.

Duration is never a caller-supplied number: the Record subtracts the session's own
committed start time from the close time, so a session cannot claim a cost the record
does not already prove. Tokens are caller-supplied because only the harness observes
them, and they are bounded and typed like every other external payload value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ctower_kernel.record.session_events import (
    MAX_SESSION_TOKENS,
    SessionOutcome,
    SessionState,
)

__all__ = [
    "ProjectSessionPage",
    "SessionCloseCommand",
    "SessionFactCommand",
    "SessionReceipt",
    "SessionStartCommand",
    "SessionTokenUsage",
    "SessionTransitionCommand",
    "TicketSessionList",
    "WorkSession",
    "session_authored_text",
]


@dataclass(frozen=True, slots=True)
class SessionStartCommand:
    """Validated request to record that accountable work started on one ticket."""

    client_command_id: UUID
    ticket_id: UUID
    branch_ref: str
    crew_name: str
    harness_ref: str
    model_ref: str
    seat_key: str
    worktree_ref: str

    def request_payload(self) -> dict[str, object]:
        return {
            "branch_ref": self.branch_ref,
            "crew_name": self.crew_name,
            "harness_ref": self.harness_ref,
            "model_ref": self.model_ref,
            "seat_key": self.seat_key,
            "ticket_id": str(self.ticket_id),
            "worktree_ref": self.worktree_ref,
        }


@dataclass(frozen=True, slots=True)
class SessionTransitionCommand:
    """Validated request to move one live session to its next authored state."""

    client_command_id: UUID
    ticket_id: UUID
    session_id: UUID
    reason: str
    to_state: SessionState

    def request_payload(self) -> dict[str, object]:
        return {
            "kind": "transition",
            "reason": self.reason,
            "session_id": str(self.session_id),
            "ticket_id": str(self.ticket_id),
            "to_state": self.to_state.value,
        }


@dataclass(frozen=True, slots=True)
class SessionCloseCommand:
    """Validated request to close one session with its outcome and token cost."""

    client_command_id: UUID
    ticket_id: UUID
    session_id: UUID
    evidence_ref: str | None
    input_tokens: int
    outcome: SessionOutcome
    output_tokens: int

    def __post_init__(self) -> None:
        for label, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if type(value) is not int or not 0 <= value <= MAX_SESSION_TOKENS:
                raise ValueError(f"{label} is outside the authored session contract")

    def request_payload(self) -> dict[str, object]:
        return {
            "evidence_ref": self.evidence_ref,
            "input_tokens": self.input_tokens,
            "kind": "close",
            "outcome": self.outcome.value,
            "output_tokens": self.output_tokens,
            "session_id": str(self.session_id),
            "ticket_id": str(self.ticket_id),
        }


type SessionFactCommand = SessionTransitionCommand | SessionCloseCommand


def session_authored_text(
    command: SessionStartCommand | SessionFactCommand,
) -> tuple[str | None, ...]:
    """Return every caller-authored string a session command carries.

    D30 clause 3 is checked over exactly these values, so a session fact can never
    smuggle credential, PHI, customer, personal, or live-incident content into the
    Record under a seat, crew, branch, worktree, reason, or evidence field.
    """

    if isinstance(command, SessionStartCommand):
        return (
            command.branch_ref,
            command.crew_name,
            command.harness_ref,
            command.model_ref,
            command.seat_key,
            command.worktree_ref,
        )
    if isinstance(command, SessionTransitionCommand):
        return (command.reason,)
    return (command.evidence_ref,)


@dataclass(frozen=True, slots=True)
class SessionReceipt:
    """Committed session command result retained for exact replay."""

    command_id: UUID
    event_id: UUID
    session_id: UUID
    state: SessionState
    ticket_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "session_id": str(self.session_id),
            "state": self.state.value,
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class SessionTokenUsage:
    """The observed token cost of one closed session."""

    input_tokens: int
    output_tokens: int

    def response_payload(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }


@dataclass(frozen=True, slots=True)
class WorkSession:
    """One recorded work session folded from its own append-only facts."""

    branch_ref: str
    closed_at: datetime | None
    crew_name: str
    duration_seconds: int | None
    evidence_ref: str | None
    harness_ref: str
    model_ref: str
    outcome: SessionOutcome | None
    project_key: str
    seat_key: str
    session_id: UUID
    started_at: datetime
    state: SessionState
    ticket_id: UUID
    tokens: SessionTokenUsage | None
    transition_count: int
    worktree_ref: str

    def __post_init__(self) -> None:
        closed = (
            self.closed_at is not None,
            self.duration_seconds is not None,
            self.outcome is not None,
            self.tokens is not None,
        )
        if len(set(closed)) != 1:
            raise ValueError("a closed session must carry outcome, duration, and token facts")

    def response_payload(self) -> dict[str, object]:
        return {
            "branch_ref": self.branch_ref,
            "closed_at": None if self.closed_at is None else self.closed_at.isoformat(),
            "crew_name": self.crew_name,
            "duration_seconds": self.duration_seconds,
            "evidence_ref": self.evidence_ref,
            "harness_ref": self.harness_ref,
            "model_ref": self.model_ref,
            "outcome": None if self.outcome is None else self.outcome.value,
            "project_key": self.project_key,
            "seat_key": self.seat_key,
            "session_id": str(self.session_id),
            "started_at": self.started_at.isoformat(),
            "state": self.state.value,
            "ticket_id": str(self.ticket_id),
            "tokens": None if self.tokens is None else self.tokens.response_payload(),
            "transition_count": self.transition_count,
            "worktree_ref": self.worktree_ref,
        }


@dataclass(frozen=True, slots=True)
class TicketSessionList:
    """Every recorded work session on one ticket, oldest start first."""

    ticket_id: UUID
    sessions: tuple[WorkSession, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "sessions": [session.response_payload() for session in self.sessions],
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class ProjectSessionPage:
    """One record-position cursor page of a single project's work sessions."""

    project_key: str
    sessions: tuple[WorkSession, ...]
    next_cursor: int | None

    def response_payload(self) -> dict[str, object]:
        return {
            "next_cursor": self.next_cursor,
            "project_key": self.project_key,
            "sessions": [session.response_payload() for session in self.sessions],
        }
