"""Generated-client builders and reads for first-class Requests."""

from __future__ import annotations

import argparse
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    Priority,
    RequestBlockerRequest,
    RequestCaptureRequest,
    RequestClosureEvaluationRequest,
    RequestOwnerRequest,
    RequestPriorityRequest,
    RequestTicketRelationRequest,
    RequestTriageRequest,
)
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    name = cast(str, arguments.cli_name)
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
    if cast(str, arguments.cli_name) != "request list":
        raise ValueError("usage: unsupported Request query")
    return client.list_requests(project_key=cast(str | None, arguments.project_key))


def mutation_command_names() -> frozenset[str]:
    return frozenset(
        {
            "request blocker set",
            "request capture",
            "request closure evaluate",
            "request owner assign",
            "request prioritize",
            "request ticket relate",
            "request triage",
        }
    )


def query_command_names() -> frozenset[str]:
    return frozenset({"request list"})
