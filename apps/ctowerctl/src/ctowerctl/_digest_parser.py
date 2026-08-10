"""Closed argparse grammar for the morning digest read."""

from __future__ import annotations

import argparse
from datetime import date

from ctowerctl._parser_support import _Parser

__all__: tuple[str, ...] = ()


def digest_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    morning = actions.add_parser("morning")
    morning.set_defaults(cli_name="digest morning")
    morning.add_argument("--date", type=date.fromisoformat)
    morning.add_argument("--output", choices=("text", "json"), default="text")
