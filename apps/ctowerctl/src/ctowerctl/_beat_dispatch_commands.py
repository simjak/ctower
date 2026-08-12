"""Generated-client CLI boundary for fleet-beat routines and effects."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import BeatRoutineRetirementReceipt

__all__: tuple[str, ...] = ()


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    command = cast(str, arguments.cli_name)
    if command == "beat-dispatch list":
        return client.list_beat_dispatch_effects()
    if command == "beat-dispatch routines":
        return client.list_beat_routines()
    raise ValueError("usage: unsupported beat-dispatch query")


def query_command_names() -> frozenset[str]:
    return frozenset({"beat-dispatch list", "beat-dispatch routines"})


def execute_online(
    arguments: argparse.Namespace, client: CtowerClient
) -> BeatRoutineRetirementReceipt:
    if cast(str, arguments.cli_name) != "beat-dispatch retire":
        raise ValueError("usage: unsupported beat-dispatch mutation")
    return client.retire_beat_routine(
        cast(str, arguments.routine_ref),
        command_id=cast(UUID, arguments.command_id),
    )


def mutation_command_names() -> frozenset[str]:
    return frozenset({"beat-dispatch retire"})
