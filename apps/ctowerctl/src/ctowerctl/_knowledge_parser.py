"""Closed argparse surface for knowledge document operations."""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from ctower_client.client import ProjectKey
from ctowerctl._parser_support import _command_id, _Parser

__all__: tuple[str, ...] = ()

_PROJECT_KEY: TypeAdapter[str] = TypeAdapter(ProjectKey)


def knowledge_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    add = actions.add_parser("add")
    add.set_defaults(cli_name="knowledge add")
    _command_id(add)
    add.add_argument("--scope", required=True, choices=("org", "project"))
    add.add_argument("--project-key", type=_PROJECT_KEY.validate_python)
    content = add.add_mutually_exclusive_group(required=True)
    content.add_argument("--body-file", type=Path)
    content.add_argument("--source-ref")
    add.add_argument("--title")
    add.add_argument("--recorded-at", type=str)
    listing = actions.add_parser("list")
    listing.set_defaults(cli_name="knowledge list")
    listing.add_argument("--scope", required=True, choices=("org", "project"))
    listing.add_argument("--project-key", type=_PROJECT_KEY.validate_python)
    get = actions.add_parser("get")
    get.set_defaults(cli_name="knowledge get")
    get.add_argument("document_id", type=UUID)
    get.add_argument("--scope", required=True, choices=("org", "project"))
    get.add_argument("--project-key", type=_PROJECT_KEY.validate_python)
