"""Closed argparse grammar for first-class Request commands."""

from __future__ import annotations

import argparse
from uuid import UUID

from ctower_client.models import Priority
from ctowerctl._parser_support import _command_id, _Parser, _version

__all__: tuple[str, ...] = ()


def request_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    capture = actions.add_parser("capture")
    capture.set_defaults(cli_name="request capture")
    _command_id(capture)
    capture.add_argument("--project-key", required=True)
    capture.add_argument("text")
    listed = actions.add_parser("list")
    listed.set_defaults(cli_name="request list")
    listed.add_argument("--project-key")
    prioritize = actions.add_parser("prioritize")
    prioritize.set_defaults(cli_name="request prioritize")
    prioritize.add_argument("request_id", type=UUID)
    _command_id(prioritize)
    _version(prioritize)
    prioritize.add_argument("--priority", required=True, choices=tuple(Priority))
    prioritize.add_argument("--reason", required=True)
    triage = actions.add_parser("triage")
    triage.set_defaults(cli_name="request triage")
    triage.add_argument("request_id", type=UUID)
    _command_id(triage)
    _version(triage)
    triage.add_argument(
        "--disposition", required=True, choices=("ACCEPTED", "DUPLICATE", "REJECTED")
    )
    triage.add_argument("--reason")
    triage.add_argument("--canonical-request-id", type=UUID)
    _fact_parsers(actions)


def _fact_parsers(actions: argparse._SubParsersAction[_Parser]) -> None:
    _owner_parser(actions)
    _ticket_parser(actions)
    _blocker_parser(actions)
    _closure_parser(actions)


def _owner_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    owner_actions = actions.add_parser("owner").add_subparsers(
        dest="owner_action", required=True, parser_class=_Parser
    )
    owner = owner_actions.add_parser("assign")
    owner.set_defaults(cli_name="request owner assign")
    owner.add_argument("request_id", type=UUID)
    _command_id(owner)
    _version(owner)
    owner.add_argument("--owner-id", required=True, type=UUID)
    owner.add_argument("--reason", required=True)


def _ticket_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    ticket_actions = actions.add_parser("ticket").add_subparsers(
        dest="ticket_action", required=True, parser_class=_Parser
    )
    relation = ticket_actions.add_parser("relate")
    relation.set_defaults(cli_name="request ticket relate")
    relation.add_argument("request_id", type=UUID)
    _command_id(relation)
    _version(relation)
    relation.add_argument("--expected-ticket-version", required=True, type=int)
    relation.add_argument("--ticket-id", required=True, type=UUID)
    relation.add_argument("--purpose", required=True, choices=("required", "optional"))
    relation.add_argument("--inactive", action="store_true")
    relation.add_argument("--reason", required=True)


def _blocker_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    blocker_actions = actions.add_parser("blocker").add_subparsers(
        dest="blocker_action", required=True, parser_class=_Parser
    )
    blocker = blocker_actions.add_parser("set")
    blocker.set_defaults(cli_name="request blocker set")
    blocker.add_argument("request_id", type=UUID)
    _command_id(blocker)
    _version(blocker)
    blocker.add_argument("--blocker-key", required=True)
    blocker.add_argument("--inactive", action="store_true")
    blocker.add_argument("--reason", required=True)


def _closure_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    closure_actions = actions.add_parser("closure").add_subparsers(
        dest="closure_action", required=True, parser_class=_Parser
    )
    closure = closure_actions.add_parser("evaluate")
    closure.set_defaults(cli_name="request closure evaluate")
    closure.add_argument("request_id", type=UUID)
    _command_id(closure)
    _version(closure)
    closure.add_argument("--reason", required=True)
