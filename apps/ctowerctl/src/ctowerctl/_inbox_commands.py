"""Generated-client builders and reads for the native inbox."""

from __future__ import annotations

import argparse
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import InboxAcknowledgeRequest, InboxSendRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    cli_name = cast(str, arguments.cli_name)
    if cli_name == "inbox send":
        return MutationPayload(
            request=InboxSendRequest(
                to=cast(str, arguments.to),
                thread_id=cast(UUID | None, arguments.thread_id),
                text=cast(str, arguments.text),
            ),
            path_parameters={},
        )
    if cli_name == "inbox ack":
        return MutationPayload(
            request=InboxAcknowledgeRequest(
                state=cast(Literal["delivered", "read"], arguments.state)
            ),
            path_parameters={"message_id": str(cast(UUID, arguments.message_id))},
        )
    raise ValueError("usage: unsupported inbox mutation")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"inbox ack", "inbox send"})


def query_command_names() -> frozenset[str]:
    return frozenset({"inbox list", "inbox read", "inbox read-state"})


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    cli_name = cast(str, arguments.cli_name)
    if cli_name == "inbox list":
        return client.list_inbox_threads(unread=cast(bool, arguments.unread))
    if cli_name == "inbox read":
        return client.read_inbox_thread(cast(UUID, arguments.thread_id))
    if cli_name == "inbox read-state":
        return client.read_inbox_message_state(cast(UUID, arguments.thread_id))
    raise ValueError("usage: unsupported inbox query")
