"""Closed argparse grammar for the Agreements ledger."""

from __future__ import annotations

import argparse
from uuid import UUID

from ctowerctl._parser_support import _command_id, _Parser

__all__: tuple[str, ...] = ()


def ruling_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    append = actions.add_parser("append")
    append.set_defaults(cli_name="ruling append")
    _command_id(append)
    append.add_argument("--supersedes", dest="supersedes_ruling_id", type=UUID)
    append.add_argument("verbatim")
    listed = actions.add_parser("list")
    listed.set_defaults(cli_name="ruling list")
    listed.add_argument("--project-key")
    get = actions.add_parser("get")
    get.set_defaults(cli_name="ruling get")
    get.add_argument("ruling_id", type=UUID)
