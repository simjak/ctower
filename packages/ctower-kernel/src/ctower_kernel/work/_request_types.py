"""Typed Request commands, semantic receipts, and read model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = [
    "DecisionBrief",
    "DecisionBriefChoice",
    "DecisionBriefSelection",
    "RequestBlocker",
    "RequestCapture",
    "RequestCaptureResult",
    "RequestChange",
    "RequestChangeResult",
    "RequestClosureEvaluation",
    "RequestList",
    "RequestOwner",
    "RequestPriority",
    "RequestRow",
    "RequestTicketRelation",
    "RequestTriage",
]


@dataclass(frozen=True, slots=True)
class DecisionBriefChoice:
    """One operator choice stated as an outcome with a bounded score."""

    key: str
    outcome: str
    completeness: int

    def response_payload(self) -> dict[str, object]:
        return {
            "completeness": self.completeness,
            "key": self.key,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class DecisionBriefSelection:
    """One recommended or safe-default choice and its plain reason."""

    choice_key: str
    reason: str

    def response_payload(self) -> dict[str, object]:
        return {"choice_key": self.choice_key, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class DecisionBrief:
    """Complete operator ask derived only from one accepted Request row."""

    eli: str
    origin_quote: str
    choices: tuple[DecisionBriefChoice, ...]
    recommendation: DecisionBriefSelection
    safe_default: DecisionBriefSelection
    rendered: str
    status: str
    ruling_id: UUID | None

    def response_payload(self) -> dict[str, object]:
        return {
            "choices": [choice.response_payload() for choice in self.choices],
            "eli": self.eli,
            "origin_quote": self.origin_quote,
            "recommendation": self.recommendation.response_payload(),
            "rendered": self.rendered,
            "ruling_id": None if self.ruling_id is None else str(self.ruling_id),
            "safe_default": self.safe_default.response_payload(),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class RequestCapture:
    """Small capture command: the server derives source, Actor, and owner."""

    client_command_id: UUID
    project_key: str
    text: str

    def request_payload(self) -> dict[str, object]:
        return {"project_key": self.project_key, "text": self.text}


@dataclass(frozen=True, slots=True)
class RequestCaptureResult:
    """Exact semantic capture result retained for replay and durability overlay."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    inbound_event_id: UUID
    request_id: UUID
    request_number: int
    project_key: str
    submitted_by: UUID
    owner_id: UUID
    version: int = 1

    @property
    def reference(self) -> str:
        return f"R{self.request_number}"

    def response_payload(self) -> dict[str, object]:
        return {
            "accepted_position": None,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "inbound_event_id": str(self.inbound_event_id),
            "owner_id": str(self.owner_id),
            "project_key": self.project_key,
            "reference": self.reference,
            "request_id": str(self.request_id),
            "request_number": self.request_number,
            "submitted_by": str(self.submitted_by),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RequestPriority:
    client_command_id: UUID
    request_id: UUID
    expected_version: int
    priority: str
    reason: str

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_version": self.expected_version,
            "priority": self.priority,
            "reason": self.reason,
            "request_id": str(self.request_id),
        }


@dataclass(frozen=True, slots=True)
class RequestTriage:
    client_command_id: UUID
    request_id: UUID
    expected_version: int
    disposition: str
    reason: str | None = None
    canonical_request_id: UUID | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            "canonical_request_id": (
                None if self.canonical_request_id is None else str(self.canonical_request_id)
            ),
            "disposition": self.disposition,
            "expected_version": self.expected_version,
            "reason": self.reason,
            "request_id": str(self.request_id),
        }


@dataclass(frozen=True, slots=True)
class RequestOwner:
    client_command_id: UUID
    request_id: UUID
    expected_version: int
    owner_id: UUID
    reason: str

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_version": self.expected_version,
            "owner_id": str(self.owner_id),
            "reason": self.reason,
            "request_id": str(self.request_id),
        }


@dataclass(frozen=True, slots=True)
class RequestTicketRelation:
    client_command_id: UUID
    request_id: UUID
    expected_version: int
    expected_ticket_version: int
    ticket_id: UUID
    purpose: str
    active: bool
    reason: str

    def request_payload(self) -> dict[str, object]:
        return {
            "active": self.active,
            "expected_version": self.expected_version,
            "expected_ticket_version": self.expected_ticket_version,
            "purpose": self.purpose,
            "reason": self.reason,
            "request_id": str(self.request_id),
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class RequestBlocker:
    client_command_id: UUID
    request_id: UUID
    expected_version: int
    blocker_key: str
    active: bool
    reason: str

    def request_payload(self) -> dict[str, object]:
        return {
            "active": self.active,
            "blocker_key": self.blocker_key,
            "expected_version": self.expected_version,
            "reason": self.reason,
            "request_id": str(self.request_id),
        }


@dataclass(frozen=True, slots=True)
class RequestClosureEvaluation:
    client_command_id: UUID
    request_id: UUID
    expected_version: int
    reason: str

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_version": self.expected_version,
            "reason": self.reason,
            "request_id": str(self.request_id),
        }


type RequestChange = (
    RequestPriority
    | RequestTriage
    | RequestOwner
    | RequestTicketRelation
    | RequestBlocker
    | RequestClosureEvaluation
)


@dataclass(frozen=True, slots=True)
class RequestChangeResult:
    """Exact replay result for one append-only Request semantic fact."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    operation: str
    request_id: UUID
    request_number: int
    version: int
    state: str

    @property
    def reference(self) -> str:
        return f"R{self.request_number}"

    def response_payload(self) -> dict[str, object]:
        return {
            "accepted_position": None,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "operation": self.operation,
            "reference": self.reference,
            "request_id": str(self.request_id),
            "request_number": self.request_number,
            "state": self.state,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RequestRow:
    """Read-only accepted Request projection at a named Record watermark."""

    request_id: UUID
    request_number: int
    project_key: str
    content: str
    content_sha256: str
    state: str
    triage: str
    owner_id: UUID
    owner: str
    priority: str
    priority_default: bool
    created_at: datetime
    required_ticket_ids: tuple[UUID, ...]
    optional_ticket_ids: tuple[UUID, ...]
    blocker: str | None
    proof_coverage: int | None
    durability_state: str
    freshness: int
    source_kind: str
    source_ref: str
    original_owner_sha256: str | None
    decision_brief: DecisionBrief | None = None
    unknown_reason: str | None = None

    def response_payload(self, *, observed_at: datetime) -> dict[str, object]:
        return {
            "age_seconds": max(0, int((observed_at - self.created_at).total_seconds())),
            "blocker": self.blocker,
            "content": self.content,
            "content_sha256": self.content_sha256,
            "created_at": self.created_at.isoformat(),
            "decision_brief": (
                None if self.decision_brief is None else self.decision_brief.response_payload()
            ),
            "durability_state": self.durability_state,
            "freshness": self.freshness,
            "optional_ticket_ids": [str(item) for item in self.optional_ticket_ids],
            "owner": self.owner,
            "owner_id": str(self.owner_id),
            "priority": self.priority,
            "priority_default": self.priority_default,
            "project_key": self.project_key,
            "proof_coverage": self.proof_coverage,
            "reference": f"R{self.request_number}",
            "request_id": str(self.request_id),
            "request_number": self.request_number,
            "required_ticket_ids": [str(item) for item in self.required_ticket_ids],
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "original_owner_sha256": self.original_owner_sha256,
            "state": self.state,
            "ticket_count": len(self.required_ticket_ids) + len(self.optional_ticket_ids),
            "triage": self.triage,
            "unknown_reason": self.unknown_reason,
        }


@dataclass(frozen=True, slots=True)
class RequestList:
    """Epistemically explicit portfolio context; unanswered is never zero."""

    rows: tuple[RequestRow, ...]
    answered_projects: tuple[str, ...]
    requested_projects: tuple[str, ...]
    unanswered_projects: tuple[str, ...]
    watermark: int
    observed_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "answered_project_count": len(self.answered_projects),
            "answered_projects": list(self.answered_projects),
            "observed_at": self.observed_at.isoformat(),
            "requested_project_count": len(self.requested_projects),
            "requested_projects": list(self.requested_projects),
            "rows": [item.response_payload(observed_at=self.observed_at) for item in self.rows],
            "unanswered_projects": list(self.unanswered_projects),
            "watermark": self.watermark,
        }
