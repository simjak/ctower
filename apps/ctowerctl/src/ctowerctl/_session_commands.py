"""Explicit generated-client commands for recorded work sessions."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    SessionCloseFact,
    SessionFactRequest,
    SessionOutcome,
    SessionStartRequest,
    SessionState,
    SessionTransitionFact,
)
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build one strict session fact without inventing a duration or a state."""

    cli_name = cast(str, arguments.cli_name)
    ticket_id = str(cast(UUID, arguments.ticket_id))
    if cli_name == "session start":
        return MutationPayload(
            request=SessionStartRequest(
                branch_ref=cast(str, arguments.branch_ref),
                crew_name=cast(str, arguments.crew_name),
                harness_ref=cast(str, arguments.harness_ref),
                model_ref=cast(str, arguments.model_ref),
                seat_key=cast(str, arguments.seat_key),
                worktree_ref=cast(str, arguments.worktree_ref),
            ),
            path_parameters={"ticket_id": ticket_id},
        )
    path_parameters = {
        "ticket_id": ticket_id,
        "session_id": str(cast(UUID, arguments.session_id)),
    }
    if cli_name == "session transition":
        return MutationPayload(
            request=SessionFactRequest(
                fact=SessionTransitionFact(
                    kind="transition",
                    reason=cast(str, arguments.reason),
                    to_state=SessionState(cast(str, arguments.to_state)),
                )
            ),
            path_parameters=path_parameters,
        )
    if cli_name == "session close":
        return MutationPayload(
            request=SessionFactRequest(
                fact=SessionCloseFact(
                    evidence_ref=cast(str | None, arguments.evidence_ref),
                    input_tokens=cast(int, arguments.input_tokens),
                    kind="close",
                    outcome=SessionOutcome(cast(str, arguments.outcome)),
                    output_tokens=cast(int, arguments.output_tokens),
                )
            ),
            path_parameters=path_parameters,
        )
    raise ValueError("usage: unsupported session mutation")


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Read recorded sessions for exactly one ticket or exactly one project."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "session ticket":
        return client.list_ticket_sessions(
            cast(UUID, arguments.ticket_id),
            project_key=cast(str, arguments.project_key),
        )
    if cli_name == "session project":
        return client.list_project_sessions(
            cast(str, arguments.project_key),
            cursor=cast(int | None, arguments.cursor),
            limit=cast(int | None, arguments.limit),
        )
    raise ValueError("usage: unsupported session query")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"session start", "session transition", "session close"})


def query_command_names() -> frozenset[str]:
    return frozenset({"session ticket", "session project"})
