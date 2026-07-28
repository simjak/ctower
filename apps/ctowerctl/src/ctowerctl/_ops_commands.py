"""Explicit Board, health, and protected operations command handlers."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    PoisonDispositionAction,
    PoisonDispositionRequest,
)
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build the single explicit protected outbox disposition command."""

    request = PoisonDispositionRequest(
        consumer_key=cast(str, arguments.consumer_key),
        topic=cast(str, arguments.topic),
        action=PoisonDispositionAction(cast(str, arguments.action)),
        reason=cast(str, arguments.reason),
    )
    return MutationPayload(
        request=request,
        path_parameters={"outbox_id": str(cast(UUID, arguments.outbox_id))},
    )


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Invoke one explicit Board or control-health read."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "control health":
        return client.get_control_health()
    if cli_name == "board query":
        return client.get_board(
            lane=cast(str | None, arguments.lane),
            priority=cast(str | None, arguments.priority),
            stage_key=cast(str | None, arguments.stage_key),
            custodian_id=cast(UUID | None, arguments.custodian_id),
            assignee_id=cast(UUID | None, arguments.assignee_id),
            source_kind=cast(str | None, arguments.source_kind),
            source_ref=cast(str | None, arguments.source_ref),
        )
    raise ValueError("usage: unsupported operations query")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"ops outbox poison dispose"})


def query_command_names() -> frozenset[str]:
    return frozenset({"board query", "control health"})
