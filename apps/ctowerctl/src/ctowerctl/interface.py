"""Argument parsing and generated-client composition for ctowerctl."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from ctower_client import CtowerClient, CtowerProblemError
from ctower_client.models import (
    BootstrapReceipt,
    BootstrapRequest,
    CustodyTransferRequest,
    Priority,
    SourceReference,
    TicketCommandResult,
    TicketCreateRequest,
    TicketResource,
)

__all__ = ["main"]

CliResult = BootstrapReceipt | TicketCommandResult | TicketResource


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute one online command and report committed-but-pending truth."""

    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    arguments = _parser().parse_args(argv)
    command_id = _command_id(arguments)
    try:
        result = _invoke(arguments, input_stream)
    except (httpx.RequestError, CtowerProblemError, ValueError) as error:
        return _report_failure(error, command_id=command_id, stderr=error_stream)
    output_stream.write(_encoded(result) + "\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctowerctl")
    parser.add_argument("--base-url", required=True, type=_safe_base_url)
    areas = parser.add_subparsers(dest="area", required=True)
    _bootstrap_parser(areas.add_parser("bootstrap"))
    _ticket_parser(areas.add_parser("ticket"))
    return parser


def _report_failure(
    error: httpx.RequestError | CtowerProblemError | ValueError,
    *,
    command_id: UUID | None,
    stderr: TextIO,
) -> int:
    if isinstance(error, httpx.RequestError):
        subject = f"command_id={command_id}" if command_id is not None else "query"
        stderr.write(f"unsent {subject}: ctower is unreachable\n")
        return 2
    if isinstance(error, CtowerProblemError):
        stderr.write(f"refused code={error.problem.code}: {error.problem.detail}\n")
        return 3
    stderr.write("refused input: invalid command input or missing stdin authority\n")
    return 4


def _bootstrap_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    first = actions.add_parser("first-tenant")
    first.add_argument("--command-id", required=True, type=UUID)
    first.add_argument("--tenant-name", required=True)
    first.add_argument("--tenant-slug", required=True)
    first.add_argument("--operator-name", required=True)
    first.add_argument("--operator-credential-ref", required=True)
    first.add_argument("--operator-vault-ref", required=True)
    first.add_argument("--commander-name", required=True)
    first.add_argument("--commander-vault-ref", required=True)


def _ticket_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--command-id", required=True, type=UUID)
    create.add_argument("--initial-custodian-id", required=True, type=UUID)
    create.add_argument("--priority", required=True, choices=tuple(Priority))
    create.add_argument("--source-kind", required=True)
    create.add_argument("--source-ref", required=True)
    create.add_argument("--title", required=True)
    show = actions.add_parser("show")
    show.add_argument("ticket_id", type=UUID)
    assign = actions.add_parser("assign")
    assign.add_argument("ticket_id", type=UUID)
    assign.add_argument("--command-id", required=True, type=UUID)
    assign.add_argument("--expected-version", required=True, type=int)
    assign.add_argument("--from-custodian-id", required=True, type=UUID)
    assign.add_argument("--to-custodian-id", required=True, type=UUID)
    assign.add_argument("--reason", required=True)
    assign.add_argument("--protected-transfer", required=True, action="store_true")


def _invoke(arguments: argparse.Namespace, stdin: TextIO) -> CliResult:
    base_url = cast(str, arguments.base_url)
    area = cast(str, arguments.area)
    action = cast(str, arguments.action)
    if area == "bootstrap" and action == "first-tenant":
        return _bootstrap(base_url, arguments, stdin)
    credential = _read_authority(stdin)
    with CtowerClient(base_url, credential=credential) as client:
        if action == "create":
            return _create_ticket(client, arguments)
        if action == "show":
            return client.get_ticket(cast(UUID, arguments.ticket_id))
        if action == "assign":
            return _assign_ticket(client, arguments)
    raise ValueError("unsupported ctowerctl command")


def _bootstrap(base_url: str, arguments: argparse.Namespace, stdin: TextIO) -> BootstrapReceipt:
    request = BootstrapRequest(
        commander_name=cast(str, arguments.commander_name),
        commander_vault_ref=cast(str, arguments.commander_vault_ref),
        operator_credential_ref=cast(str, arguments.operator_credential_ref),
        operator_name=cast(str, arguments.operator_name),
        operator_vault_ref=cast(str, arguments.operator_vault_ref),
        tenant_name=cast(str, arguments.tenant_name),
        tenant_slug=cast(str, arguments.tenant_slug),
    )
    with CtowerClient(base_url) as client:
        return client.bootstrap_first_tenant(
            request,
            command_id=cast(UUID, arguments.command_id),
            capability=_read_authority(stdin),
        )


def _create_ticket(client: CtowerClient, arguments: argparse.Namespace) -> TicketCommandResult:
    request = TicketCreateRequest(
        initial_custodian_id=cast(UUID, arguments.initial_custodian_id),
        priority=Priority(cast(str, arguments.priority)),
        source=SourceReference(
            kind=cast(str, arguments.source_kind), ref=cast(str, arguments.source_ref)
        ),
        title=cast(str, arguments.title),
    )
    return client.create_ticket(request, command_id=cast(UUID, arguments.command_id))


def _assign_ticket(client: CtowerClient, arguments: argparse.Namespace) -> TicketCommandResult:
    request = CustodyTransferRequest(
        expected_version=cast(int, arguments.expected_version),
        from_custodian_id=cast(UUID, arguments.from_custodian_id),
        protected_transfer=cast(bool, arguments.protected_transfer),
        reason=cast(str, arguments.reason),
        to_custodian_id=cast(UUID, arguments.to_custodian_id),
    )
    return client.transfer_ticket_custody(
        cast(UUID, arguments.ticket_id),
        request,
        command_id=cast(UUID, arguments.command_id),
    )


def _command_id(arguments: argparse.Namespace) -> UUID | None:
    value = getattr(arguments, "command_id", None)
    return value if isinstance(value, UUID) else None


def _read_authority(stream: TextIO) -> str:
    authority = stream.readline().rstrip("\r\n")
    if not authority:
        raise ValueError("an authority value is required on stdin")
    return authority


def _safe_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise argparse.ArgumentTypeError("base URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise argparse.ArgumentTypeError("base URL must not contain authority credentials")
    return value


def _encoded(result: CliResult) -> str:
    return json.dumps(result.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
