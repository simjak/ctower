"""Shared argparse building blocks for the authored ctower CLI command families."""

from __future__ import annotations

import argparse
from typing import Never
from uuid import UUID

from ctowerctl._argument_types import _positive_int

__all__: tuple[str, ...] = ()


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(f"usage: {message}")


def _ticket_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ticket_id", type=UUID)


def _session_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("session_id", type=UUID)


def _command_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--command-id", type=UUID)


def _version(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-version", required=True, type=_positive_int)


def _version_reason(parser: argparse.ArgumentParser) -> None:
    _version(parser)
    parser.add_argument("--reason", required=True)


def _review_dispatch(actions: argparse._SubParsersAction[_Parser]) -> None:
    dispatches = actions.add_parser("review-dispatch").add_subparsers(
        dest="review_dispatch_action", required=True, parser_class=_Parser
    )
    listed = dispatches.add_parser("list")
    listed.set_defaults(cli_name="ticket review-dispatch list")
    _ticket_id(listed)
    consume = dispatches.add_parser("consume")
    consume.set_defaults(cli_name="ticket review-dispatch consume")
    _ticket_id(consume)
    consume.add_argument("effect_id", type=UUID)
    _command_id(consume)
    _version_reason(consume)
    consume.add_argument("--reviewer-principal-id", required=True, type=UUID)
    for name in ("author-family", "reviewer-family", "crew-name"):
        consume.add_argument(f"--{name}", required=True)
