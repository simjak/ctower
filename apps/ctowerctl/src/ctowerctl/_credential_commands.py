"""Explicit online-only generated-client calls for project-seat credentials."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from ctower_client import CtowerClient
from ctower_client.models import (
    CredentialScope,
    SeatCredentialIssueRequest,
    SeatCredentialReceipt,
    SeatCredentialRevocationRequest,
)
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build one strict secret-free credential mutation."""

    if arguments.cli_name == "credential seat issue":
        issuance = SeatCredentialIssueRequest(
            credential_digest=cast(str, arguments.credential_digest),
            credential_ref=cast(str, arguments.credential_ref),
            display_name=cast(str, arguments.display_name),
            project_key=cast(str, arguments.project_key),
            scopes=tuple(CredentialScope(scope) for scope in arguments.scopes),
            seat_key=cast(str, arguments.seat_key),
        )
        return MutationPayload(request=issuance, path_parameters={})
    if arguments.cli_name == "credential seat revoke":
        revocation = SeatCredentialRevocationRequest(reason=cast(str, arguments.reason))
        return MutationPayload(
            request=revocation,
            path_parameters={"credential_id": str(cast(UUID, arguments.credential_id))},
        )
    raise ValueError("usage: unsupported credential mutation")


def execute_online(arguments: argparse.Namespace, client: CtowerClient) -> SeatCredentialReceipt:
    """Send one unspoolable operator credential mutation."""

    payload = build_mutation(arguments)
    command_id = cast(UUID, arguments.command_id)
    if arguments.cli_name == "credential seat issue":
        return client.issue_seat_credential(
            cast(SeatCredentialIssueRequest, payload.request),
            command_id=command_id,
        )
    if arguments.cli_name == "credential seat revoke":
        return client.revoke_seat_credential(
            UUID(payload.path_parameters["credential_id"]),
            cast(SeatCredentialRevocationRequest, payload.request),
            command_id=command_id,
        )
    raise ValueError("usage: unsupported credential mutation")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"credential seat issue", "credential seat revoke"})
