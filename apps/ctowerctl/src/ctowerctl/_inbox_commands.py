"""Generated-client builders and reads for the native inbox."""

from __future__ import annotations

import argparse
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    InboxAcknowledgeRequest,
    InboxNotificationRequest,
    InboxPromotionRequest,
    InboxSendRequest,
)
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
                severity=cast(Literal["P0", "P1", "info"], arguments.severity),
                project_key=cast(str, arguments.project_key),
            ),
            path_parameters={},
        )
    if cli_name == "inbox notify":
        return MutationPayload(
            request=InboxNotificationRequest(
                to=cast(str, arguments.to),
                text=cast(str, arguments.text),
                severity=cast(Literal["P0", "P1", "info"], arguments.severity),
                project_key=cast(str, arguments.project_key),
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
    if cli_name == "inbox promote":
        return MutationPayload(
            request=InboxPromotionRequest(ticket_id=cast(UUID | None, arguments.ticket_id)),
            path_parameters={"thread_id": str(cast(UUID, arguments.thread_id))},
        )
    raise ValueError("usage: unsupported inbox mutation")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"inbox ack", "inbox notify", "inbox promote", "inbox send"})


def query_command_names() -> frozenset[str]:
    return frozenset({"inbox correspondents", "inbox list", "inbox read", "inbox read-state"})


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    cli_name = cast(str, arguments.cli_name)
    if cli_name == "inbox list":
        return client.list_inbox_threads(unread=cast(bool, arguments.unread))
    if cli_name == "inbox correspondents":
        return client.list_inbox_correspondents(project_key=cast(str | None, arguments.project_key))
    if cli_name == "inbox read":
        return client.read_inbox_thread(cast(UUID, arguments.thread_id))
    if cli_name == "inbox read-state":
        return client.read_inbox_message_state(cast(UUID, arguments.thread_id))
    raise ValueError("usage: unsupported inbox query")
