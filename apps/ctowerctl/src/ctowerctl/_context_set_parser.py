"""Argparse surface for the ticket context-set and attention-finding commands."""

from __future__ import annotations

import argparse
from uuid import UUID

from ctowerctl._argument_types import _aware_datetime
from ctowerctl._parser_support import _command_id, _Parser, _ticket_id

__all__: tuple[str, ...] = ()


def ticket_context_sets(actions: argparse._SubParsersAction[_Parser]) -> None:
    change_reference_actions = actions.add_parser("change-reference").add_subparsers(
        dest="change_reference_action", required=True, parser_class=_Parser
    )
    change_reference = change_reference_actions.add_parser("add")
    change_reference.set_defaults(cli_name="ticket change-reference add")
    _ticket_id(change_reference)
    _command_id(change_reference)
    change_reference.add_argument("--repository", required=True)
    change_reference.add_argument("--change-identity", required=True)
    change_reference.add_argument("--reference", required=True)

    label_actions = actions.add_parser("label").add_subparsers(
        dest="label_action", required=True, parser_class=_Parser
    )
    label = label_actions.add_parser("apply")
    label.set_defaults(cli_name="ticket label apply")
    _ticket_id(label)
    _command_id(label)
    label.add_argument("--label-key", required=True)


def attention_parser(parser: argparse.ArgumentParser) -> None:
    subjects = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    finding_actions = subjects.add_parser("finding").add_subparsers(
        dest="finding_action", required=True, parser_class=_Parser
    )
    append = finding_actions.add_parser("append")
    append.set_defaults(cli_name="attention finding append")
    _command_id(append)
    append.add_argument("--subject-ticket-id", required=True, type=UUID)
    append.add_argument("--kind-key", required=True)
    append.add_argument("--reason-code", required=True)
    append.add_argument("--effective-owner", required=True, choices=("operator", "commander"))
    append.add_argument("--recommendation", required=True)
    append.add_argument("--alternative", dest="alternatives", required=True, action="append")
    append.add_argument("--consequence", required=True)
    append.add_argument("--deadline", type=_aware_datetime)
    append.add_argument("--dedupe-key", required=True)
    append.add_argument("--source-fact", dest="source_facts", required=True, action="append")

    disposition = finding_actions.add_parser("disposition")
    disposition.set_defaults(cli_name="attention finding disposition")
    disposition.add_argument("finding_id", type=UUID)
    _command_id(disposition)
    disposition.add_argument(
        "--outcome",
        required=True,
        choices=("resolved", "snoozed", "expired", "superseded", "cancelled"),
    )
    disposition.add_argument("--reason", required=True)
