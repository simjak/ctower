"""Generated-client CLI boundary for nightly dream effects."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import DreamDispatchConsumeRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    if cast(str, arguments.cli_name) != "dream-dispatch consume":
        raise ValueError("usage: unsupported dream-dispatch mutation")
    return MutationPayload(
        request=DreamDispatchConsumeRequest(output_digest=cast(str, arguments.output_digest)),
        path_parameters={"effect_id": str(cast(UUID, arguments.effect_id))},
    )


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    if cast(str, arguments.cli_name) != "dream-dispatch list":
        raise ValueError("usage: unsupported dream-dispatch query")
    return client.list_dream_dispatch_effects()


def mutation_command_names() -> frozenset[str]:
    return frozenset({"dream-dispatch consume"})


def query_command_names() -> frozenset[str]:
    return frozenset({"dream-dispatch list"})
