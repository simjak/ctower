"""Generated-client builders and reads for the native inbox."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import InboxSendRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    if cast(str, arguments.cli_name) != "inbox send":
        raise ValueError("usage: unsupported inbox mutation")
    return MutationPayload(
        request=InboxSendRequest(
            to=cast(str, arguments.to),
            thread_id=cast(UUID | None, arguments.thread_id),
            text=cast(str, arguments.text),
        ),
        path_parameters={},
    )


def mutation_command_names() -> frozenset[str]:
    return frozenset({"inbox send"})


def query_command_names() -> frozenset[str]:
    return frozenset({"inbox list", "inbox read"})


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    cli_name = cast(str, arguments.cli_name)
    if cli_name == "inbox list":
        return client.list_inbox_threads(unread=cast(bool, arguments.unread))
    if cli_name == "inbox read":
        return client.read_inbox_thread(cast(UUID, arguments.thread_id))
    raise ValueError("usage: unsupported inbox query")
