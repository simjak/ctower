"""Generated-client builders and reads for spawn-custody records."""

from __future__ import annotations

import argparse
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import SpawnRecordCreateRequest, SpawnTransitionRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    name = cast(str, arguments.cli_name)
    if name == "spawn record":
        return MutationPayload(
            request=SpawnRecordCreateRequest(
                project_key=cast(str, arguments.project_key),
                seat_key=cast(str, arguments.seat_key),
                crew_name=cast(str, arguments.crew_name),
                task_file_ref=cast(str, arguments.task_file_ref),
                worktree_path=cast(str, arguments.worktree_path),
                harness=cast(str, arguments.harness),
                model=cast(str, arguments.model),
                effort=cast(str | None, arguments.effort),
                workspace_id=cast(UUID | None, arguments.workspace_id),
            ),
            path_parameters={},
        )
    if name == "spawn transition":
        spawn_id = cast(UUID, arguments.spawn_id)
        return MutationPayload(
            request=SpawnTransitionRequest(
                to_status=cast(
                    Literal["accepted", "running", "completed", "failed", "reaped"],
                    arguments.to_status,
                ),
                reason=cast(str | None, arguments.reason),
            ),
            path_parameters={"spawn_id": str(spawn_id)},
        )
    raise ValueError("usage: unsupported spawn mutation")


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    name = cast(str, arguments.cli_name)
    if name == "spawn list":
        return client.list_spawn_records(
            project_key=cast(str, arguments.project_key),
            status=cast(str | None, arguments.status),
            limit=cast(int | None, arguments.limit),
            offset=cast(int | None, arguments.offset),
        )
    if name == "spawn show":
        return client.get_spawn_record(cast(UUID, arguments.spawn_id))
    raise ValueError("usage: unsupported spawn query")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"spawn record", "spawn transition"})


def query_command_names() -> frozenset[str]:
    return frozenset({"spawn list", "spawn show"})
