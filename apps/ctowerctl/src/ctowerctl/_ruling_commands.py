"""Generated-client builders and reads for the Agreements ledger."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import RulingAppendRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    return MutationPayload(
        request=RulingAppendRequest(
            request_id=cast(UUID | None, arguments.request_id),
            supersedes_ruling_id=cast(UUID | None, arguments.supersedes_ruling_id),
            verbatim=cast(str, arguments.verbatim),
        ),
        path_parameters={},
    )


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    name = cast(str, arguments.cli_name)
    if name == "ruling list":
        return client.list_rulings(project_key=cast(str | None, arguments.project_key))
    if name == "ruling get":
        return client.get_ruling(ruling_id=cast(UUID, arguments.ruling_id))
    raise ValueError("usage: unsupported Ruling query")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"ruling append"})


def query_command_names() -> frozenset[str]:
    return frozenset({"ruling get", "ruling list"})
