"""Strict canonical payload for one Request-maintenance proposal fact."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = ["RequestProposalChangedPayload"]

_KINDS = frozenset({"duplicate", "completed-but-open", "supersession", "kill", "keep"})


@dataclass(frozen=True, slots=True)
class RequestProposalChangedPayload:
    """One append or terminal decision without claiming a Request mutation."""

    operation: str
    proposal_id: UUID
    proposal_kind: str
    proposal_state: str
    target_request_id: UUID
    target_command_id: UUID | None
    target_outcome: str | None
    target_problem_code: str | None

    def __post_init__(self) -> None:
        _validate_fields(self)
        _validate_operation_state(self)

    def to_mapping(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "proposal_id": str(self.proposal_id),
            "proposal_kind": self.proposal_kind,
            "proposal_state": self.proposal_state,
            "target_command_id": (
                None if self.target_command_id is None else str(self.target_command_id)
            ),
            "target_outcome": self.target_outcome,
            "target_problem_code": self.target_problem_code,
            "target_request_id": str(self.target_request_id),
        }


def _validate_identity(payload: object, aggregate_id: UUID) -> None:
    if isinstance(payload, RequestProposalChangedPayload) and payload.proposal_id != aggregate_id:
        raise ValueError("proposal event aggregate and payload identity must match")


def _validate_fields(payload: RequestProposalChangedPayload) -> None:
    if payload.operation not in {"appended", "confirmed", "rejected"}:
        raise ValueError("proposal operation is outside the authored contract")
    if payload.proposal_kind not in _KINDS:
        raise ValueError("proposal kind is outside the authored contract")
    if payload.proposal_state not in {"OPEN", "CONFIRMED", "REJECTED"}:
        raise ValueError("proposal state is outside the authored contract")
    _validate_identity_fields(payload)
    if payload.target_outcome not in {None, "accepted", "refused"}:
        raise ValueError("proposal target outcome is outside the authored contract")


def _validate_identity_fields(payload: RequestProposalChangedPayload) -> None:
    if not isinstance(payload.proposal_id, UUID) or not isinstance(payload.target_request_id, UUID):
        raise TypeError("proposal and target Request identities must be UUIDs")
    if payload.target_command_id is not None and not isinstance(payload.target_command_id, UUID):
        raise TypeError("proposal target command identity must be a UUID or None")


def _validate_operation_state(payload: RequestProposalChangedPayload) -> None:
    if payload.operation == "appended":
        _validate_append_state(payload)
        return
    if payload.operation == "rejected":
        _validate_rejection_state(payload)
        return
    _validate_confirmation_state(payload)


def _validate_append_state(payload: RequestProposalChangedPayload) -> None:
    if (
        payload.proposal_state != "OPEN"
        or payload.target_command_id is not None
        or payload.target_outcome is not None
        or payload.target_problem_code is not None
    ):
        raise ValueError("proposal append cannot claim a target outcome")


def _validate_rejection_state(payload: RequestProposalChangedPayload) -> None:
    if payload.proposal_state != "REJECTED":
        raise ValueError("proposal rejection must remain visibly rejected")


def _validate_confirmation_state(payload: RequestProposalChangedPayload) -> None:
    has_problem = payload.target_problem_code is not None
    refused = payload.target_outcome == "refused"
    if payload.proposal_state != "CONFIRMED" or payload.target_command_id is None:
        raise ValueError("proposal confirmation must carry its exact target result")
    if payload.target_outcome is None or refused != has_problem:
        raise ValueError("proposal confirmation must carry its exact target result")
