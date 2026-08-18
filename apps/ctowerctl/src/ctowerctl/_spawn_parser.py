"""Closed argparse grammar for spawn-custody record commands."""

from __future__ import annotations

import argparse
from uuid import UUID

from pydantic import TypeAdapter

from ctower_client.client import ProjectKey
from ctowerctl._argument_types import _nonnegative_int, _positive_int
from ctowerctl._parser_support import _command_id, _Parser

__all__: tuple[str, ...] = ()

_PROJECT_KEY: TypeAdapter[str] = TypeAdapter(ProjectKey)


def spawn_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    record = actions.add_parser("record")
    record.set_defaults(cli_name="spawn record")
    _command_id(record)
    record.add_argument("--project-key", required=True, type=_PROJECT_KEY.validate_python)
    record.add_argument("--seat-key", required=True)
    record.add_argument("--crew-name", required=True)
    record.add_argument("--task-file-ref", required=True)
    record.add_argument("--worktree-path", required=True)
    record.add_argument("--harness", required=True)
    record.add_argument("--model", required=True)
    record.add_argument("--effort")
    record.add_argument("--workspace-id", type=UUID)

    transition = actions.add_parser("transition")
    transition.set_defaults(cli_name="spawn transition")
    transition.add_argument("spawn_id", type=UUID)
    _command_id(transition)
    transition.add_argument(
        "--to-status",
        required=True,
        choices=("accepted", "running", "completed", "failed", "reaped"),
    )
    transition.add_argument("--reason")

    listing = actions.add_parser("list")
    listing.set_defaults(cli_name="spawn list")
    listing.add_argument("--project-key", required=True, type=_PROJECT_KEY.validate_python)
    listing.add_argument(
        "--status",
        choices=("requested", "accepted", "running", "completed", "failed", "reaped"),
    )
    listing.add_argument("--limit", type=_positive_int)
    listing.add_argument("--offset", type=_nonnegative_int)

    shown = actions.add_parser("show")
    shown.set_defaults(cli_name="spawn show")
    shown.add_argument("spawn_id", type=UUID)
