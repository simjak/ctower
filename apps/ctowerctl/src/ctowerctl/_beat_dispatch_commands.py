"""Generated-client CLI boundary for fleet-beat routines and effects."""

from __future__ import annotations

import argparse
from typing import cast

from pydantic import BaseModel

from ctower_client import CtowerClient

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
