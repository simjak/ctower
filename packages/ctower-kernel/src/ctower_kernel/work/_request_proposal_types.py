"""Typed Request-maintenance proposal commands, receipts, and read rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

__all__ = [
    "ProofEvidencePointer",
    "RecordEventEvidencePointer",
    "RequestMaintenanceProposalAppend",
    "RequestMaintenanceProposalAppendResult",
    "RequestMaintenanceProposalConfirm",
    "RequestMaintenanceProposalDecisionResult",
    "RequestMaintenanceProposalList",
    "RequestMaintenanceProposalReject",
    "RequestMaintenanceProposalRow",
    "RequestProposalEvidencePointer",
]


@dataclass(frozen=True, slots=True)
class RecordEventEvidencePointer:
    event_id: UUID
    event_kind: str
    event_digest: str
    kind: str = "record-event"

    def request_payload(self) -> dict[str, object]:
        return {
            "event_digest": self.event_digest,
            "event_id": str(self.event_id),
            "event_kind": self.event_kind,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class ProofEvidencePointer:
    ticket_id: UUID
    proof_id: UUID
    evidence_id: UUID
    artifact_digest: str
    kind: str = "proof-evidence"

    def request_payload(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "evidence_id": str(self.evidence_id),
            "kind": self.kind,
            "proof_id": str(self.proof_id),
            "ticket_id": str(self.ticket_id),
        }


type RequestProposalEvidencePointer = RecordEventEvidencePointer | ProofEvidencePointer


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalAppend:
    client_command_id: UUID
    project_key: str
    kind: str
    basis: str
    target_request_id: UUID
    target_expected_version: int
    target_text: str
    source_record_position: int
    evidence: tuple[RequestProposalEvidencePointer, ...]
    related_request_id: UUID | None = None
    related_expected_version: int | None = None
    related_text: str | None = None
    ambiguity_reason: str | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            "ambiguity_reason": self.ambiguity_reason,
            "basis": self.basis,
            "evidence": [item.request_payload() for item in self.evidence],
            "kind": self.kind,
            "project_key": self.project_key,
            "related_expected_version": self.related_expected_version,
            "related_request_id": (
                None if self.related_request_id is None else str(self.related_request_id)
            ),
            "related_text": self.related_text,
            "source_record_position": self.source_record_position,
            "target_expected_version": self.target_expected_version,
            "target_request_id": str(self.target_request_id),
            "target_text": self.target_text,
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalConfirm:
    client_command_id: UUID
    proposal_id: UUID
    expected_proposal_version: int

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_proposal_version": self.expected_proposal_version,
            "proposal_id": str(self.proposal_id),
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalReject:
    client_command_id: UUID
    proposal_id: UUID
    expected_proposal_version: int
    reason: str | None

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_proposal_version": self.expected_proposal_version,
            "proposal_id": str(self.proposal_id),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalAppendResult:
    command_id: UUID
    event_ids: tuple[UUID, ...]
    proposal_id: UUID
    project_key: str
    kind: str
    state: str
    ambiguity_reason: str | None
    proposer_principal_id: UUID
    source_record_position: int
    target_request_id: UUID
    proposal_version: int = 1

    def response_payload(self) -> dict[str, object]:
        return {
            "accepted_position": None,
            "ambiguity_reason": self.ambiguity_reason,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "kind": self.kind,
            "project_key": self.project_key,
            "proposal_id": str(self.proposal_id),
            "proposal_version": self.proposal_version,
            "proposer_principal_id": str(self.proposer_principal_id),
            "source_record_position": self.source_record_position,
            "state": self.state,
            "target_request_id": str(self.target_request_id),
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalDecisionResult:
    command_id: UUID
    event_ids: tuple[UUID, ...]
    decision_id: UUID
    proposal_id: UUID
    operation: str
    decided_by: UUID
    decided_at: datetime
    reason: str | None
    target_command_id: UUID | None
    target_outcome: str | None
    target_problem_code: str | None
    target_request_version: int | None
    expected_proposal_version: int = 1
    accepted_position: int | None = None

    def response_payload(self) -> dict[str, object]:
        return {
            "accepted_position": self.accepted_position,
            "command_id": str(self.command_id),
            "decided_at": self.decided_at.isoformat(),
            "decided_by": str(self.decided_by),
            "decision_id": str(self.decision_id),
            "durability_state": (
                "accepted" if self.accepted_position is not None else "durability_pending"
            ),
            "event_ids": [str(item) for item in self.event_ids],
            "expected_proposal_version": self.expected_proposal_version,
            "operation": self.operation,
            "proposal_id": str(self.proposal_id),
            "reason": self.reason,
            "target_command_id": (
                None if self.target_command_id is None else str(self.target_command_id)
            ),
            "target_outcome": self.target_outcome,
            "target_problem_code": self.target_problem_code,
            "target_request_version": self.target_request_version,
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalRow:
    proposal_id: UUID
    project_key: str
    kind: str
    basis: str
    state: str
    ambiguity_reason: str | None
    target_request_id: UUID
    target_expected_version: int
    target_text: str
    related_request_id: UUID | None
    related_expected_version: int | None
    related_text: str | None
    source_record_position: int
    proposer_principal_id: UUID
    seat_credential_id: UUID | None
    created_at: datetime
    evidence: tuple[RequestProposalEvidencePointer, ...]
    decision: RequestMaintenanceProposalDecisionResult | None
    proposal_version: int = 1

    def response_payload(self) -> dict[str, object]:
        return {
            "ambiguity_reason": self.ambiguity_reason,
            "basis": self.basis,
            "created_at": self.created_at.isoformat(),
            "decision": None if self.decision is None else self.decision.response_payload(),
            "evidence": [item.request_payload() for item in self.evidence],
            "kind": self.kind,
            "project_key": self.project_key,
            "proposal_id": str(self.proposal_id),
            "proposal_version": self.proposal_version,
            "proposer_principal_id": str(self.proposer_principal_id),
            "related_expected_version": self.related_expected_version,
            "related_request_id": (
                None if self.related_request_id is None else str(self.related_request_id)
            ),
            "related_text": self.related_text,
            "seat_credential_id": (
                None if self.seat_credential_id is None else str(self.seat_credential_id)
            ),
            "source_record_position": self.source_record_position,
            "state": self.state,
            "target_expected_version": self.target_expected_version,
            "target_request_id": str(self.target_request_id),
            "target_text": self.target_text,
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalList:
    rows: tuple[RequestMaintenanceProposalRow, ...]
    watermark: int
    observed_at: datetime
    unanswered_projects: tuple[str, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "rows": [row.response_payload() for row in self.rows],
            "unanswered_projects": list(self.unanswered_projects),
            "watermark": self.watermark,
        }


def append_result_from_committed(
    payload: dict[str, object],
) -> RequestMaintenanceProposalAppendResult:
    return RequestMaintenanceProposalAppendResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        proposal_id=UUID(str(payload["proposal_id"])),
        project_key=str(payload["project_key"]),
        kind=str(payload["kind"]),
        state=str(payload["state"]),
        ambiguity_reason=cast(str | None, payload["ambiguity_reason"]),
        proposer_principal_id=UUID(str(payload["proposer_principal_id"])),
        source_record_position=int(cast(int, payload["source_record_position"])),
        target_request_id=UUID(str(payload["target_request_id"])),
        proposal_version=int(cast(int, payload["proposal_version"])),
    )


def decision_result_from_committed(
    payload: dict[str, object],
) -> RequestMaintenanceProposalDecisionResult:
    return RequestMaintenanceProposalDecisionResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        decision_id=UUID(str(payload["decision_id"])),
        proposal_id=UUID(str(payload["proposal_id"])),
        operation=str(payload["operation"]),
        decided_by=UUID(str(payload["decided_by"])),
        decided_at=datetime.fromisoformat(str(payload["decided_at"])),
        reason=cast(str | None, payload["reason"]),
        target_command_id=(
            None
            if payload["target_command_id"] is None
            else UUID(str(payload["target_command_id"]))
        ),
        target_outcome=cast(str | None, payload["target_outcome"]),
        target_problem_code=cast(str | None, payload["target_problem_code"]),
        target_request_version=cast(int | None, payload["target_request_version"]),
        expected_proposal_version=int(cast(int, payload["expected_proposal_version"])),
        accepted_position=cast(int | None, payload.get("accepted_position")),
    )
