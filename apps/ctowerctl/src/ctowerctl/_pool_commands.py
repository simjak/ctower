"""Generated-client builders and reads for harness credential-pool limits."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctowerctl._command_types import MutationPayload
from ctowerctl._pool_feeder import observation_request

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Sweep one local harness profile home into one observation request."""

    if cast(str, arguments.cli_name) != "pools observe":
        raise ValueError("usage: unsupported pools mutation")
    profile_home = cast(Path, arguments.profile_home)
    if not profile_home.is_dir():
        raise ValueError("usage: pools observe needs an existing harness profile home")
    return MutationPayload(
        request=observation_request(
            profile_home,
            profile_key=cast(str, arguments.profile_key),
            observed_at=datetime.now(UTC),
        ),
        path_parameters={},
    )


def mutation_command_names() -> frozenset[str]:
    return frozenset({"pools observe"})


def query_command_names() -> frozenset[str]:
    return frozenset({"pools show"})


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    if cast(str, arguments.cli_name) != "pools show":
        raise ValueError("usage: unsupported pools query")
    return client.read_pool_limits(profile_key=cast(str | None, arguments.profile_key))
