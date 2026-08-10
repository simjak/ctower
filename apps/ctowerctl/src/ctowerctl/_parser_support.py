"""Shared argparse building blocks for the authored ctower CLI command families."""

from __future__ import annotations

import argparse
from typing import Never
from uuid import UUID

from ctowerctl._argument_types import _positive_int

__all__: tuple[str, ...] = ()

AUTHORED_COMMAND_NAMES = frozenset(
    {
        "bootstrap first-tenant",
        "credential seat issue",
        "credential seat revoke",
        "digest morning",
        "intake promote",
        "intake submit",
        "request capture",
        "request blocker set",
        "request closure evaluate",
        "request list",
        "request owner assign",
        "request prioritize",
        "request ticket relate",
        "request triage",
        "ruling append",
        "ruling get",
        "ruling list",
        "inbox send",
        "inbox ack",
        "inbox list",
        "inbox notify",
        "inbox promote",
        "inbox read",
        "inbox read-state",
        "knowledge add",
        "knowledge list",
        "knowledge get",
        "dream-dispatch list",
        "dream-dispatch consume",
        "dream-lane bind",
        "ticket capture",
        "ticket create",
        "ticket query",
        "ticket show",
        "ticket timeline",
        "ticket audit",
        "ticket assignments",
        "ticket comment add",
        "ticket change-reference add",
        "ticket label apply",
        "ticket assign",
        "ticket custody transfer",
        "ticket prioritize",
        "ticket admit",
        "ticket defer",
        "ticket block",
        "ticket unblock",
        "ticket reopen",
        "ticket relation add",
        "ticket criteria freeze",
        "ticket evidence add",
        "ticket gate verdict",
        "ticket workflow start",
        "ticket transition",
        "ticket resolve",
        "ticket review-dispatch consume",
        "ticket review-dispatch list",
        "session start",
        "session transition",
        "session close",
        "session ticket",
        "session project",
        "board query",
        "control health",
        "ops outbox poison dispose",
        "company bundle validate",
        "company bundle plan",
        "company bundle apply",
        "company bundle export",
        "synthetic query",
        "synthetic run",
        "migration ctower-project inventory",
        "migration ctower-project export",
        "migration ctower-project plan",
        "migration ctower-project import",
        "migration ctower-project reconcile",
        "migration ctower-project run get",
        "migration ctower-project correction append",
        "migration ctower-project fence observe",
        "migration ctower-project prepare",
        "migration ctower-project commit-development-epoch",
        "migration ctower-project verify",
        "project delivery query",
        "project events",
        "attention finding append",
        "attention finding disposition",
    }
)


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
    consume.add_argument("--crew-name", required=True)
