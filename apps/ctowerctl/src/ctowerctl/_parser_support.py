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
    parser.add_argument("--command-id", required=True, type=UUID)


def _version(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-version", required=True, type=_positive_int)


def _version_reason(parser: argparse.ArgumentParser) -> None:
    _version(parser)
    parser.add_argument("--reason", required=True)
