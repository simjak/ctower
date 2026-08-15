"""Generated-client builders and reads for first-class Requests."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    Priority,
    RequestBlockerRequest,
    RequestCaptureRequest,
    RequestClosureEvaluationRequest,
    RequestMaintenanceProposalAppendRequest,
    RequestMaintenanceProposalConfirmRequest,
    RequestMaintenanceProposalRejectRequest,
    RequestOwnerRequest,
    RequestPriorityRequest,
    RequestTicketRelationRequest,
    RequestTriageRequest,
)
from ctowerctl._command_types import MutationPayload
from ctowerctl._input import read_text

__all__: tuple[str, ...] = ()
_PROPOSAL_INPUT_MAX_BYTES = 128 * 1024


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    name = cast(str, arguments.cli_name)
    if name.startswith("request proposal "):
        return _proposal_mutation(name, arguments)
    if name == "request capture":
        return MutationPayload(
            request=RequestCaptureRequest(
                project_key=cast(str, arguments.project_key), text=cast(str, arguments.text)
            ),
            path_parameters={},
        )
    return MutationPayload(
        request=_change_payload(name, arguments),
        path_parameters={"request_id": str(cast(UUID, arguments.request_id))},
    )


def _proposal_mutation(name: str, arguments: argparse.Namespace) -> MutationPayload:
    if name == "request proposal append":
        content = read_text(
            cast(Path, arguments.input_file),
            maximum_bytes=_PROPOSAL_INPUT_MAX_BYTES,
            label="Request proposal input",
        )
        append_request = RequestMaintenanceProposalAppendRequest.model_validate_json(content)
        return MutationPayload(request=append_request, path_parameters={})
    proposal_id = cast(UUID, arguments.proposal_id)
    expected = cast(Literal[1], arguments.expected_version)
    decision_request: BaseModel
    if name == "request proposal confirm":
        decision_request = RequestMaintenanceProposalConfirmRequest(
            expected_proposal_version=expected
        )
    elif name == "request proposal reject":
        decision_request = RequestMaintenanceProposalRejectRequest(
            expected_proposal_version=expected,
            reason=cast(str | None, arguments.reason),
        )
    else:
        raise ValueError("usage: unsupported Request proposal mutation")
    return MutationPayload(
        request=decision_request, path_parameters={"proposal_id": str(proposal_id)}
    )


def _change_payload(name: str, arguments: argparse.Namespace) -> BaseModel:
    expected_version = cast(int, arguments.expected_version)
    if name == "request prioritize":
        return RequestPriorityRequest(
            expected_version=expected_version,
            priority=Priority(cast(str, arguments.priority)),
            reason=cast(str, arguments.reason),
        )
    if name == "request triage":
        return RequestTriageRequest(
            canonical_request_id=cast(UUID | None, arguments.canonical_request_id),
            disposition=cast(Literal["ACCEPTED", "DUPLICATE", "REJECTED"], arguments.disposition),
            expected_version=expected_version,
            reason=cast(str | None, arguments.reason),
        )
    if name == "request owner assign":
        return RequestOwnerRequest(
            expected_version=expected_version,
            owner_id=cast(UUID, arguments.owner_id),
            reason=cast(str, arguments.reason),
        )
    if name == "request ticket relate":
        return RequestTicketRelationRequest(
            active=not cast(bool, arguments.inactive),
            expected_ticket_version=cast(int, arguments.expected_ticket_version),
            expected_version=expected_version,
            purpose=cast(Literal["required", "optional"], arguments.purpose),
            reason=cast(str, arguments.reason),
            ticket_id=cast(UUID, arguments.ticket_id),
        )
    if name == "request blocker set":
        return RequestBlockerRequest(
            active=not cast(bool, arguments.inactive),
            blocker_key=cast(str, arguments.blocker_key),
            expected_version=expected_version,
            reason=cast(str, arguments.reason),
        )
    if name == "request closure evaluate":
        return RequestClosureEvaluationRequest(
            expected_version=expected_version,
            reason=cast(str, arguments.reason),
        )
    raise ValueError("usage: unsupported Request mutation")


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    name = cast(str, arguments.cli_name)
    if name == "request list":
        return client.list_requests(project_key=cast(str | None, arguments.project_key))
    if name == "request proposal list":
        return client.list_request_maintenance_proposals(
            proposal_id=cast(UUID | None, arguments.proposal_id),
            project_key=cast(str | None, arguments.project_key),
            kind=cast(str | None, arguments.kind),
            state=cast(str | None, arguments.state),
        )
    if name == "request proposal review":
        return client.get_request_maintenance_review()
    raise ValueError("usage: unsupported Request query")


def mutation_command_names() -> frozenset[str]:
    return frozenset(
        {
            "request blocker set",
            "request capture",
            "request closure evaluate",
            "request owner assign",
            "request proposal append",
            "request proposal confirm",
            "request proposal reject",
            "request prioritize",
            "request ticket relate",
            "request triage",
        }
    )


def query_command_names() -> frozenset[str]:
    return frozenset(
        {
            "request list",
            "request proposal list",
            "request proposal review",
        }
    )
