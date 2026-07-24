"""Closed argparse surface for the authored ctower CLI command families."""

from __future__ import annotations

import argparse
import ipaddress
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Never
from urllib.parse import SplitResult, urlsplit
from uuid import UUID

from ctower_client.models import (
    BoardLane,
    PoisonDispositionAction,
    Priority,
    RelationKind,
    VerdictDecision,
)

__all__: tuple[str, ...] = ()

_ASSIGNMENT_KINDS = ("current_assignee", "stage_owner", "reviewer")
_BLOCKER_KINDS = ("dependency", "operator_action", "policy", "resource", "technical")
_SPOOL_STATES = ("pending", "accepted_archive", "quarantine")
_AUTHORED_COMMAND_NAMES = frozenset(
    {
        "bootstrap first-tenant",
        "ticket capture",
        "ticket create",
        "ticket query",
        "ticket show",
        "ticket timeline",
        "ticket audit",
        "ticket assignments",
        "ticket comment add",
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
        "board query",
        "control health",
        "ops outbox poison dispose",
        "company bundle validate",
        "company bundle plan",
        "company bundle apply",
        "company bundle export",
    }
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(f"usage: {message}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse only explicit authored commands; unknown operations are usage errors."""

    return _parser().parse_args(argv)


def authored_command_names() -> frozenset[str]:
    """Expose the closed command inventory for generated-contract parity tests."""

    return _AUTHORED_COMMAND_NAMES


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="ctowerctl")
    parser.add_argument("--base-url", required=True, type=_safe_base_url)
    areas = parser.add_subparsers(dest="area", required=True, parser_class=_Parser)
    _bootstrap_parser(areas.add_parser("bootstrap"))
    _ticket_parser(areas.add_parser("ticket"))
    _board_parser(areas.add_parser("board"))
    _control_parser(areas.add_parser("control"))
    _ops_parser(areas.add_parser("ops"))
    _company_parser(areas.add_parser("company"))
    _spool_parser(areas.add_parser("spool"))
    return parser


def _bootstrap_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    first = actions.add_parser("first-tenant")
    first.set_defaults(cli_name="bootstrap first-tenant")
    _command_id(first)
    first.add_argument("--tenant-name", required=True)
    first.add_argument("--tenant-slug", required=True)
    first.add_argument("--operator-name", required=True)
    first.add_argument("--operator-credential-ref", required=True)
    first.add_argument("--operator-vault-ref", required=True)
    first.add_argument("--commander-name", required=True)
    first.add_argument("--commander-vault-ref", required=True)


def _ticket_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    _ticket_capture_and_reads(actions)
    _ticket_authority(actions)
    _ticket_work(actions)
    _ticket_proof(actions)
    _ticket_workflow(actions)


def _ticket_capture_and_reads(actions: argparse._SubParsersAction[_Parser]) -> None:
    for name in ("capture", "create"):
        capture = actions.add_parser(name)
        capture.set_defaults(cli_name=f"ticket {name}")
        _command_id(capture)
        capture.add_argument("--initial-custodian-id", required=True, type=UUID)
        capture.add_argument("--priority", required=True, choices=tuple(Priority))
        capture.add_argument("--source-kind", required=True)
        capture.add_argument("--source-ref", required=True)
        capture.add_argument("--title", required=True)
    for name in ("query", "show"):
        query = actions.add_parser(name)
        query.set_defaults(cli_name=f"ticket {name}")
        _ticket_id(query)
    for name in ("timeline", "assignments"):
        read = actions.add_parser(name)
        read.set_defaults(cli_name=f"ticket {name}")
        _ticket_id(read)
    audit = actions.add_parser("audit")
    audit.set_defaults(cli_name="ticket audit")
    _ticket_id(audit)
    audit.add_argument("--cursor", type=_nonnegative_int)
    audit.add_argument("--limit", type=_positive_int)


def _ticket_authority(actions: argparse._SubParsersAction[_Parser]) -> None:
    comment_actions = actions.add_parser("comment").add_subparsers(
        dest="comment_action", required=True, parser_class=_Parser
    )
    comment = comment_actions.add_parser("add")
    comment.set_defaults(cli_name="ticket comment add")
    _ticket_id(comment)
    _command_id(comment)
    comment.add_argument("--body", required=True)

    assign = actions.add_parser("assign")
    assign.set_defaults(cli_name="ticket assign")
    _ticket_id(assign)
    _command_id(assign)
    _version_reason(assign)
    assign.add_argument("--kind", required=True, choices=_ASSIGNMENT_KINDS)
    assign.add_argument("--to-principal-id", required=True, type=UUID)
    assign.add_argument("--scope-ref")

    custody_actions = actions.add_parser("custody").add_subparsers(
        dest="custody_action", required=True, parser_class=_Parser
    )
    transfer = custody_actions.add_parser("transfer")
    transfer.set_defaults(cli_name="ticket custody transfer")
    _ticket_id(transfer)
    _command_id(transfer)
    _version_reason(transfer)
    transfer.add_argument("--from-custodian-id", required=True, type=UUID)
    transfer.add_argument("--to-custodian-id", required=True, type=UUID)
    transfer.add_argument("--protected-transfer", action="store_true", required=True)


def _ticket_work(actions: argparse._SubParsersAction[_Parser]) -> None:
    prioritize = actions.add_parser("prioritize")
    prioritize.set_defaults(cli_name="ticket prioritize")
    _ticket_id(prioritize)
    _command_id(prioritize)
    _version_reason(prioritize)
    prioritize.add_argument("--priority", required=True, choices=tuple(Priority))
    prioritize.add_argument("--urgent-evidence-ref")

    for name in ("admit", "reopen"):
        intent = actions.add_parser(name)
        intent.set_defaults(cli_name=f"ticket {name}")
        _ticket_id(intent)
        _command_id(intent)
        _version_reason(intent)
    defer = actions.add_parser("defer")
    defer.set_defaults(cli_name="ticket defer")
    _ticket_id(defer)
    _command_id(defer)
    _version_reason(defer)
    defer.add_argument("--review-after", required=True, type=_aware_datetime)
    _block_parser(actions)
    _unblock_parser(actions)
    _relation_parser(actions)


def _block_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    block = actions.add_parser("block")
    block.set_defaults(cli_name="ticket block")
    _ticket_id(block)
    _command_id(block)
    _version_reason(block)
    block.add_argument("--blocker-id", required=True, type=UUID)
    block.add_argument("--blocker-kind", required=True, choices=_BLOCKER_KINDS)
    block.add_argument("--reason-class", required=True)
    block.add_argument("--owner-principal-id", required=True, type=UUID)
    block.add_argument("--source-ref", required=True)
    block.add_argument("--affected-stage")
    block.add_argument("--resolution-condition", required=True)
    block.add_argument("--next-check-at", type=_aware_datetime)
    block.add_argument("--dependency-ref")
    block.add_argument(
        "--board-impact",
        action=argparse.BooleanOptionalAction,
        required=True,
    )


def _unblock_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    unblock = actions.add_parser("unblock")
    unblock.set_defaults(cli_name="ticket unblock")
    _ticket_id(unblock)
    _command_id(unblock)
    _version_reason(unblock)
    unblock.add_argument("--blocker-id", required=True, type=UUID)
    unblock.add_argument("--resolution-evidence-ref", required=True)


def _relation_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    relation_actions = actions.add_parser("relation").add_subparsers(
        dest="relation_action", required=True, parser_class=_Parser
    )
    relation = relation_actions.add_parser("add")
    relation.set_defaults(cli_name="ticket relation add")
    _ticket_id(relation)
    _command_id(relation)
    _version_reason(relation)
    relation.add_argument("--kind", required=True, choices=tuple(RelationKind))
    relation.add_argument("--target-ticket-id", required=True, type=UUID)


def _ticket_proof(actions: argparse._SubParsersAction[_Parser]) -> None:
    criteria_actions = actions.add_parser("criteria").add_subparsers(
        dest="criteria_action", required=True, parser_class=_Parser
    )
    criteria = criteria_actions.add_parser("freeze")
    criteria.set_defaults(cli_name="ticket criteria freeze")
    _ticket_id(criteria)
    _command_id(criteria)
    criteria.add_argument("--expected-version", required=True, type=_nonnegative_int)
    criteria.add_argument("--candidate-digest", required=True)
    criteria.add_argument("--criteria-file", required=True, type=Path)

    evidence_actions = actions.add_parser("evidence").add_subparsers(
        dest="evidence_action", required=True, parser_class=_Parser
    )
    evidence = evidence_actions.add_parser("add")
    evidence.set_defaults(cli_name="ticket evidence add")
    _ticket_id(evidence)
    _command_id(evidence)
    _version(evidence)
    evidence.add_argument("--evidence-id", required=True, type=UUID)
    evidence.add_argument("--criterion-key", required=True)
    evidence.add_argument("--candidate-digest", required=True)
    evidence.add_argument("--artifact-digest", required=True)
    evidence.add_argument("--content-file", required=True, type=Path)
    _verdict_parser(actions)


def _verdict_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    gate_actions = actions.add_parser("gate").add_subparsers(
        dest="gate_action", required=True, parser_class=_Parser
    )
    verdict = gate_actions.add_parser("verdict")
    verdict.set_defaults(cli_name="ticket gate verdict")
    _ticket_id(verdict)
    _command_id(verdict)
    _version(verdict)
    verdict.add_argument("--verdict-id", required=True, type=UUID)
    verdict.add_argument("--criterion-key", required=True)
    verdict.add_argument("--candidate-digest", required=True)
    verdict.add_argument("--decision", required=True, choices=tuple(VerdictDecision))


def _ticket_workflow(actions: argparse._SubParsersAction[_Parser]) -> None:
    workflow_actions = actions.add_parser("workflow").add_subparsers(
        dest="workflow_action", required=True, parser_class=_Parser
    )
    start = workflow_actions.add_parser("start")
    start.set_defaults(cli_name="ticket workflow start")
    _ticket_id(start)
    _command_id(start)
    for name in ("workflow", "execution-policy", "gate-policy", "evidence-policy"):
        start.add_argument(f"--{name}-ref", required=True)
        start.add_argument(f"--{name}-digest", required=True)
    transition = actions.add_parser("transition")
    transition.set_defaults(cli_name="ticket transition")
    _ticket_id(transition)
    _command_id(transition)
    transition.add_argument("--expected-version", required=True, type=_nonnegative_int)
    transition.add_argument("--workflow-ref", required=True)
    transition.add_argument("--source-stage", required=True)
    transition.add_argument("--destination-stage", required=True)
    resolve = actions.add_parser("resolve")
    resolve.set_defaults(cli_name="ticket resolve")
    _ticket_id(resolve)
    _command_id(resolve)
    _version(resolve)
    resolve.add_argument("--workflow-ref", required=True)


def _board_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    query = actions.add_parser("query")
    query.set_defaults(cli_name="board query")
    query.add_argument("--lane", choices=tuple(BoardLane))
    query.add_argument("--priority", choices=tuple(Priority))
    query.add_argument("--stage-key")
    query.add_argument("--custodian-id", type=UUID)
    query.add_argument("--assignee-id", type=UUID)


def _control_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    health = actions.add_parser("health")
    health.set_defaults(cli_name="control health")


def _ops_parser(parser: argparse.ArgumentParser) -> None:
    outbox = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    poison = outbox.add_parser("outbox").add_subparsers(
        dest="outbox_subject", required=True, parser_class=_Parser
    )
    dispose = (
        poison.add_parser("poison")
        .add_subparsers(dest="poison_action", required=True, parser_class=_Parser)
        .add_parser("dispose")
    )
    dispose.set_defaults(cli_name="ops outbox poison dispose")
    dispose.add_argument("outbox_id", type=UUID)
    _command_id(dispose)
    dispose.add_argument("--consumer-key", required=True)
    dispose.add_argument("--topic", required=True)
    dispose.add_argument("--action", required=True, choices=tuple(PoisonDispositionAction))
    dispose.add_argument("--reason", required=True)


def _company_parser(parser: argparse.ArgumentParser) -> None:
    bundle = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    actions = bundle.add_parser("bundle").add_subparsers(
        dest="bundle_action", required=True, parser_class=_Parser
    )
    for name in ("validate", "plan"):
        operation = actions.add_parser(name)
        operation.set_defaults(cli_name=f"company bundle {name}")
        operation.add_argument("bundle_file", type=Path)
    apply = actions.add_parser("apply")
    apply.set_defaults(cli_name="company bundle apply")
    apply.add_argument("bundle_file", type=Path)
    _command_id(apply)
    apply.add_argument("--expected-active-version", required=True, type=_nonnegative_int)
    apply.add_argument("--plan-digest", required=True)
    export = actions.add_parser("export")
    export.set_defaults(cli_name="company bundle export")


def _spool_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    actions.add_parser("status").set_defaults(local_command="spool status")
    listing = actions.add_parser("list")
    listing.set_defaults(local_command="spool list")
    listing.add_argument("--state", choices=_SPOOL_STATES)
    listing.add_argument("--limit", type=_positive_int, default=1000)
    actions.add_parser("doctor").set_defaults(local_command="spool doctor")
    actions.add_parser("drain").set_defaults(local_command="spool drain")
    quarantine = actions.add_parser("quarantine").add_subparsers(
        dest="quarantine_action", required=True, parser_class=_Parser
    )
    quarantine_list = quarantine.add_parser("list")
    quarantine_list.set_defaults(local_command="spool quarantine list")
    quarantine_list.add_argument("--limit", type=_positive_int, default=1000)
    for name in ("retry", "discard"):
        disposition = actions.add_parser(name)
        disposition.set_defaults(local_command=f"spool {name}")
        disposition.add_argument("sequence", type=_positive_int)
        disposition.add_argument("--reason", required=True)


def _ticket_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ticket_id", type=UUID)


def _command_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--command-id", required=True, type=UUID)


def _version(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-version", required=True, type=_positive_int)


def _version_reason(parser: argparse.ArgumentParser) -> None:
    _version(parser)
    parser.add_argument("--reason", required=True)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def _safe_base_url(value: str) -> str:
    parsed = _split_base_url(value)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"}:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if host is None:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if _has_forbidden_url_parts(parsed):
        raise argparse.ArgumentTypeError("base URL must not contain credentials or suffix data")
    if parsed.scheme == "http" and not _loopback(host):
        raise argparse.ArgumentTypeError("cleartext HTTP is permitted only for loopback")
    return value


def _split_base_url(value: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise argparse.ArgumentTypeError("base URL syntax is invalid") from error
    return parsed


def _has_forbidden_url_parts(parsed: SplitResult) -> bool:
    return any((parsed.username, parsed.password, parsed.query, parsed.fragment))


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
