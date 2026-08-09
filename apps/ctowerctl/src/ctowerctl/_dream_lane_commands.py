"""Generated-client CLI boundary for the operator dream-lane ceremony."""

from __future__ import annotations

import argparse
from typing import cast
from uuid import UUID

from ctower_client import CtowerClient
from ctower_client.models import DreamLaneBindingReceipt, DreamLaneBindRequest

__all__: tuple[str, ...] = ()


def execute_online(arguments: argparse.Namespace, client: CtowerClient) -> DreamLaneBindingReceipt:
    if cast(str, arguments.cli_name) != "dream-lane bind":
        raise ValueError("usage: unsupported dream-lane command")
    selection = (
        cast(str, arguments.harness_ref),
        cast(str, arguments.model_ref),
        cast(str, arguments.reasoning_effort),
        cast(str, arguments.fallback_model_ref),
        cast(str, arguments.model_tier),
    )
    if selection != ("codex", "gpt-5.6-sol", "max", "qwen3.8-max", "hard"):
        raise ValueError("usage: dream-lane selection is outside the ceremony registry")
    request = DreamLaneBindRequest(
        lane_ref=cast(str, arguments.lane_ref),
        crew_name=cast(str, arguments.crew_name),
        harness_ref="codex",
        model_ref="gpt-5.6-sol",
        reasoning_effort="max",
        fallback_model_ref="qwen3.8-max",
        model_tier="hard",
    )
    return client.bind_dream_lane(request, command_id=cast(UUID, arguments.command_id))


def mutation_command_names() -> frozenset[str]:
    return frozenset({"dream-lane bind"})
