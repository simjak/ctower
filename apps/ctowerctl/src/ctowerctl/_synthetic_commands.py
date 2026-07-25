"""Strict protected CLI bindings for the fixed synthetic operation."""

from __future__ import annotations

import argparse
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient, SyntheticRunRequest
from ctowerctl._command_types import MutationPayload

__all__: tuple[str, ...] = ()


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    return MutationPayload(
        request=SyntheticRunRequest(
            workflow_ref=cast(
                Literal["ctower.trust-spine-four-stage@1"],
                arguments.workflow_ref,
            ),
        ),
        path_parameters={},
    )


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    return client.get_synthetic_workflow_run(cast(UUID, arguments.run_id))


def mutation_command_names() -> frozenset[str]:
    return frozenset({"synthetic run"})


def query_command_names() -> frozenset[str]:
    return frozenset({"synthetic query"})
