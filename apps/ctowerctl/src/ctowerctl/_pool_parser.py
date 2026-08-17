"""Closed argparse surface for harness credential-pool operations."""

from __future__ import annotations

import argparse
from pathlib import Path

from ctowerctl._parser_support import _command_id, _Parser

__all__: tuple[str, ...] = ()

_PROFILE_KEY_HELP = "the harness profile this sweep is about, for example engineer"


def pools_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    observe = actions.add_parser("observe")
    observe.set_defaults(cli_name="pools observe")
    _command_id(observe)
    observe.add_argument("--profile-key", required=True, help=_PROFILE_KEY_HELP)
    observe.add_argument("--profile-home", required=True, type=Path)
    show = actions.add_parser("show")
    show.set_defaults(cli_name="pools show")
    show.add_argument("--profile-key", help=_PROFILE_KEY_HELP)
