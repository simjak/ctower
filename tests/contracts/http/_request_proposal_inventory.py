"""Closed HTTP inventory owned by the Request-maintenance proposal surface."""

from __future__ import annotations

__all__ = ["REQUEST_PROPOSAL_OPERATION_METADATA", "REQUEST_PROPOSAL_PROBLEM_CODES"]

REQUEST_PROPOSAL_OPERATION_METADATA: dict[str, tuple[object, bool, str, object, bool]] = {
    "appendRequestMaintenanceProposal": (
        "request proposal append",
        True,
        "allowed",
        None,
        False,
    ),
    "confirmRequestMaintenanceProposal": (
        "request proposal confirm",
        True,
        "allowed",
        None,
        False,
    ),
    "getRequestMaintenanceReview": (
        "request proposal review",
        False,
        "forbidden",
        None,
        False,
    ),
    "listRequestMaintenanceProposals": (
        "request proposal list",
        False,
        "forbidden",
        None,
        False,
    ),
    "rejectRequestMaintenanceProposal": (
        "request proposal reject",
        True,
        "allowed",
        None,
        False,
    ),
}

REQUEST_PROPOSAL_PROBLEM_CODES = frozenset(
    {
        "proposal-already-decided",
        "proposal-append-forbidden",
        "proposal-credential-invalid",
        "proposal-decision-forbidden",
        "proposal-evidence-invalid",
        "proposal-evidence-unavailable",
        "proposal-invalid",
        "proposal-kind-invalid",
        "proposal-not-found",
        "proposal-project-invalid",
        "proposal-project-unavailable",
        "proposal-quote-invalid",
        "proposal-quote-mismatch",
        "proposal-reason-invalid",
        "proposal-related-not-found",
        "proposal-state-invalid",
        "proposal-target-not-found",
        "proposal-version-conflict",
        "proposal-watermark-invalid",
    }
)
