"""Thin composition root for explicit generated-client and encrypted-spool commands."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from typing import Literal, TextIO, cast
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from ctower_client import CtowerClient, CtowerProblemError
from ctower_client.models import (
    CompanyBundleExportResult,
    ControlHealth,
    HealthStatus,
    MorningDigest,
    MovementEventPage,
    Problem,
    ProjectDeliveryView,
)
from ctower_client.operations import OperationSpec, SpoolPolicy, operation_for_cli
from ctowerctl import (
    _attention_commands,
    _beat_dispatch_commands,
    _bootstrap_commands,
    _company_commands,
    _credential_commands,
    _digest_commands,
    _dream_dispatch_commands,
    _dream_lane_commands,
    _inbox_commands,
    _intake_commands,
    _knowledge_commands,
    _migration_commands,
    _ops_commands,
    _request_commands,
    _ruling_commands,
    _session_commands,
    _spool_commands,
    _synthetic_commands,
    _ticket_commands,
    _workflow_commands,
)
from ctowerctl._auth import read_authority
from ctowerctl._command_types import MutationPayload
from ctowerctl._generated_replay import GeneratedReplayExecutor, ReplayObservation
from ctowerctl._mutation_retry import drain_with_retry
from ctowerctl._output import (
    CommandOutcome,
    ExitCode,
    LocalFailure,
    reason_code,
    write_json,
    write_text,
)
from ctowerctl._parser import parse_arguments
from ctowerctl.discovery import DiscoveryError, resolve_base_url
from ctowerctl.spool import Spool, SpoolCommand, SpoolEntry, SpoolError, SpoolState

__all__ = ["main", "write_result"]

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

_NOTIFICATION_OPERATION_ID = "ingestInboxNotification"


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute one explicit command with durable-before-send mutation semantics."""

    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    try:
        arguments = parse_arguments(argv)
    except (TypeError, ValueError):
        error_stream.write("usage: invalid command input or missing stdin authority\n")
        return int(ExitCode.USAGE)
    if arguments.base_url is None:
        try:
            arguments.base_url = resolve_base_url()
        except DiscoveryError as error:
            error_stream.write(f"usage: {error}\n")
            return int(ExitCode.USAGE)
    return _run_command(arguments, input_stream, output_stream, error_stream)


def _run_command(
    arguments: argparse.Namespace,
    input_stream: TextIO,
    output_stream: TextIO,
    error_stream: TextIO,
) -> int:
    try:
        result, code = (
            _execute_local(arguments, input_stream)
            if hasattr(arguments, "local_command")
            else _execute(arguments, input_stream)
        )
    except SpoolError as error:
        command_id = _command_id(arguments)
        write_json(
            output_stream,
            LocalFailure(command_id=command_id, reason_code=reason_code(error.code)),
        )
        error_stream.write(f"local_failure code={reason_code(error.code)}\n")
        return int(ExitCode.LOCAL_FAILURE)
    except (ValidationError, OSError, TypeError, ValueError):
        error_stream.write("usage: invalid command input or missing stdin authority\n")
        return int(ExitCode.USAGE)
    except CtowerProblemError as error:
        _write_problem(error, error_stream)
        return int(ExitCode.PERMANENT)
    except httpx.RequestError:
        subject = _command_id(arguments)
        identity = f"command_id={subject}" if subject is not None else "query"
        error_stream.write(f"temporary {identity}: ctower is unreachable\n")
        return int(ExitCode.TEMPORARY)
    write_result(arguments, result, output_stream)
    return int(code)


def _execute(
    arguments: object,
    authority_stream: TextIO,
) -> tuple[BaseModel, ExitCode]:
    namespace = cast("argparse.Namespace", arguments)
    base_url = cast(str, namespace.base_url)
    cli_name = cast(str, namespace.cli_name)
    if cli_name == "bootstrap first-tenant":
        result = _bootstrap_commands.execute(base_url, namespace, authority_stream)
        code = ExitCode.SUCCESS if result.durability_state == "accepted" else ExitCode.TEMPORARY
        return result, code
    operation = operation_for_cli(cli_name)
    if operation is None:
        raise ValueError("usage: command is absent from generated registry")
    credential = read_authority(authority_stream)
    if _uses_credential_executor(namespace, operation):
        return _execute_online_credential(base_url, credential, namespace, operation)
    if namespace.area == "migration" and (operation.mutation or operation.refusal_only):
        return _execute_online_migration(base_url, credential, namespace, operation)
    if operation.mutation:
        if cli_name == "synthetic run":
            return _execute_synthetic(base_url, credential, namespace, operation)
        return _execute_mutation(base_url, credential, namespace, operation)
    with CtowerClient(base_url, credential=credential) as client:
        query_result = _execute_query(namespace, client)
        return query_result, _query_exit_code(query_result)


def _uses_credential_executor(arguments: argparse.Namespace, operation: OperationSpec) -> bool:
    return operation.mutation and arguments.area in {"beat-dispatch", "credential", "dream-lane"}


def _query_exit_code(result: BaseModel) -> ExitCode:
    """A degraded or unknown `control health` read succeeded; its exit must not say `HEALTHY`."""

    if isinstance(result, ControlHealth) and result.status is not HealthStatus.HEALTHY:
        return ExitCode.PERMANENT
    return ExitCode.SUCCESS


def _execute_local(
    arguments: argparse.Namespace,
    authority_stream: TextIO,
) -> tuple[BaseModel, ExitCode]:
    if arguments.local_command == "ticket workflow list":
        return _workflow_commands.execute_local()
    return _spool_commands.execute(cast(str, arguments.base_url), arguments, authority_stream)


def _execute_mutation(
    base_url: str,
    credential: str,
    arguments: object,
    operation: OperationSpec,
) -> tuple[CommandOutcome, ExitCode]:
    namespace = cast("argparse.Namespace", arguments)
    if operation.spool_policy is not SpoolPolicy.ALLOWED:
        raise ValueError("usage: mutation is not allowlisted for encrypted replay")
    payload = _build_mutation(namespace)
    command_id = cast(UUID, namespace.command_id)
    command = SpoolCommand(
        operation_id=operation.operation_id,
        path_parameters=cast(JsonObject, payload.path_parameters),
        request_body=_model_payload(payload.request),
        command_id=command_id,
    )
    spool = Spool.for_origin(base_url).bind_credential(credential)
    spool.enqueue(command)
    with CtowerClient(base_url, credential=credential) as client:
        executor = GeneratedReplayExecutor(client)
        if operation.operation_id == _NOTIFICATION_OPERATION_ID:
            retry = drain_with_retry(spool, executor, command_id)
            report = retry.report
            current = retry.entry
            retry_exhausted = retry.exhausted
        else:
            report = spool.drain(executor)
            current = _current_entry(spool, command_id)
            retry_exhausted = False
    observation = executor.observations.get(command_id)
    result = _observation_result(observation)
    outcome = CommandOutcome(
        command_id=command_id,
        state=_outcome_state(current.state),
        reason_code=_outcome_reason(
            current,
            "retry_exhausted" if retry_exhausted else report.reason_code,
        ),
        sequence=current.sequence,
        result=result,
        server_refusal=current.server_refusal,
    )
    return outcome, _outcome_code(current.state, report.barrier_sequence)


_MUTATION_FAMILIES: dict[str, Callable[[argparse.Namespace], MutationPayload]] = {
    "ticket": _ticket_commands.build_mutation,
    "intake": _intake_commands.build_mutation,
    "inbox": _inbox_commands.build_mutation,
    "knowledge": _knowledge_commands.build_mutation,
    "company": _company_commands.build_mutation,
    "ops": _ops_commands.build_mutation,
    "session": _session_commands.build_mutation,
    "synthetic": _synthetic_commands.build_mutation,
    "attention": _attention_commands.build_mutation,
    "request": _request_commands.build_mutation,
    "ruling": _ruling_commands.build_mutation,
    "dream-dispatch": _dream_dispatch_commands.build_mutation,
}


def _build_mutation(arguments: object) -> MutationPayload:
    namespace = cast("argparse.Namespace", arguments)
    area = cast(str, namespace.area)
    builder = _MUTATION_FAMILIES.get(area)
    if builder is None:
        raise ValueError("usage: unsupported mutation family")
    return builder(namespace)


def _execute_online_migration(
    base_url: str,
    credential: str,
    arguments: argparse.Namespace,
    operation: OperationSpec,
) -> tuple[BaseModel, ExitCode]:
    """Execute one cutover write or unconditional refusal online."""

    if operation.spool_policy is not SpoolPolicy.FORBIDDEN:
        raise ValueError("usage: online migration operation has unsafe spool metadata")
    with CtowerClient(base_url, credential=credential) as client:
        result = _migration_commands.execute_online(arguments, client)
    return result, ExitCode.SUCCESS


def _execute_online_credential(
    base_url: str,
    credential: str,
    arguments: argparse.Namespace,
    operation: OperationSpec,
) -> tuple[BaseModel, ExitCode]:
    """Execute one operator-only command without replay spooling."""

    if operation.spool_policy is not SpoolPolicy.FORBIDDEN:
        raise ValueError("usage: operator commands require forbidden spool metadata")
    with CtowerClient(base_url, credential=credential) as client:
        result = (
            _beat_dispatch_commands.execute_online(arguments, client)
            if arguments.area == "beat-dispatch"
            else _dream_lane_commands.execute_online(arguments, client)
            if arguments.area == "dream-lane"
            else _credential_commands.execute_online(arguments, client)
        )
    code = ExitCode.SUCCESS if result.durability_state == "accepted" else ExitCode.TEMPORARY
    return result, code


def _execute_query(arguments: object, client: CtowerClient) -> BaseModel:
    namespace = cast("argparse.Namespace", arguments)
    area = cast(str, namespace.area)
    if area in {
        "ticket",
        "inbox",
        "knowledge",
        "dream-dispatch",
        "beat-dispatch",
        "request",
        "ruling",
    }:
        return _execute_agent_query(namespace, client)
    handlers: dict[str, Callable[[argparse.Namespace, CtowerClient], BaseModel]] = {
        "digest": _digest_commands.execute_query,
        "company": _company_commands.execute_query,
        "board": _ops_commands.execute_query,
        "control": _ops_commands.execute_query,
        "session": _session_commands.execute_query,
        "synthetic": _synthetic_commands.execute_query,
    }
    return handlers.get(area, _execute_project_query)(namespace, client)


def _execute_agent_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    if arguments.area == "ticket":
        return _ticket_commands.execute_query(arguments, client)
    if arguments.area == "knowledge":
        return _knowledge_commands.execute_query(arguments, client)
    if arguments.area in {"dream-dispatch", "beat-dispatch"}:
        handler = (
            _dream_dispatch_commands.execute_query
            if arguments.area == "dream-dispatch"
            else _beat_dispatch_commands.execute_query
        )
        return handler(arguments, client)
    if arguments.area == "request":
        return _request_commands.execute_query(arguments, client)
    if arguments.area == "ruling":
        return _ruling_commands.execute_query(arguments, client)
    return _inbox_commands.execute_query(arguments, client)


def _execute_project_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    if arguments.area in {"migration", "project"}:
        return _migration_commands.execute_query(arguments, client)
    raise ValueError("usage: unsupported query family")


def _execute_synthetic(
    base_url: str,
    credential: str,
    arguments: argparse.Namespace,
    operation: OperationSpec,
) -> tuple[BaseModel, ExitCode]:
    outcome, code = _execute_mutation(base_url, credential, arguments, operation)
    if code is not ExitCode.SUCCESS or outcome.result is None:
        return outcome, code
    raw_run_id = outcome.result.get("run_id")
    if not isinstance(raw_run_id, str):
        raise TypeError("synthetic receipt omitted run identity")
    deadline = time.monotonic() + 60
    with CtowerClient(base_url, credential=credential) as client:
        while time.monotonic() < deadline:
            run = client.get_synthetic_workflow_run(UUID(raw_run_id))
            if run.state.value == "succeeded":
                if run.lifecycle_facts != cast(tuple[str, ...], arguments.assertions):
                    return run, ExitCode.PERMANENT
                return run, ExitCode.SUCCESS
            if run.state.value == "failed":
                return run, ExitCode.PERMANENT
            time.sleep(0.2)
    return run, ExitCode.TEMPORARY


def write_result(arguments: object, result: BaseModel, stream: TextIO) -> None:
    """Write one command result through the public CLI presentation boundary."""

    namespace = cast("argparse.Namespace", arguments)
    if getattr(namespace, "cli_name", None) == "company bundle export" and isinstance(
        result, CompanyBundleExportResult
    ):
        write_text(stream, _company_commands.export_yaml(result))
        return
    if (
        getattr(namespace, "cli_name", None) == "digest morning"
        and getattr(namespace, "output", None) == "text"
        and isinstance(result, MorningDigest)
    ):
        write_text(stream, _digest_commands.morning_text(result))
        return
    if (
        getattr(namespace, "cli_name", None) == "project delivery query"
        and getattr(namespace, "output", None) == "text"
        and isinstance(result, ProjectDeliveryView)
    ):
        write_text(stream, _migration_commands.delivery_text(result))
        return
    if getattr(namespace, "cli_name", None) == "project movement":
        _write_movement_result(result, stream)
        return
    write_json(stream, result)


def _model_payload(model: BaseModel) -> JsonObject:
    return cast(JsonObject, json.loads(model.model_dump_json(by_alias=True)))


def _write_movement_result(result: BaseModel, stream: TextIO) -> None:
    if not isinstance(result, MovementEventPage):
        write_json(stream, result)
        return
    stream.write(
        json.dumps(
            result.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _current_entry(spool: Spool, command_id: UUID) -> SpoolEntry:
    entry = next(
        (item for item in spool.list_entries(limit=10_000) if item.command_id == command_id),
        None,
    )
    if entry is None:
        raise SpoolError("local_failure", "spooled command disappeared")
    return entry


def _outcome_state(
    state: SpoolState,
) -> Literal["accepted", "queued", "quarantined"]:
    if state is SpoolState.ACCEPTED_ARCHIVE:
        return "accepted"
    if state is SpoolState.PENDING:
        return "queued"
    return "quarantined"


def _outcome_reason(entry: SpoolEntry, drain_reason: str) -> str:
    if entry.reason_code is not None:
        return reason_code(entry.reason_code)
    if entry.state is SpoolState.ACCEPTED_ARCHIVE:
        return "accepted"
    return reason_code(drain_reason)


def _observation_result(observation: ReplayObservation | None) -> JsonObject | None:
    if observation is None:
        return None
    if observation.problem is not None:
        return cast(
            JsonObject,
            json.loads(observation.problem.model_dump_json(by_alias=True, exclude_none=True)),
        )
    return observation.response.response


def _outcome_code(state: SpoolState, barrier: int | None) -> ExitCode:
    if state is SpoolState.ACCEPTED_ARCHIVE:
        return ExitCode.SUCCESS
    if state is SpoolState.QUARANTINE or barrier is not None:
        return ExitCode.PERMANENT
    return ExitCode.TEMPORARY


def _write_problem(error: CtowerProblemError, stream: TextIO) -> None:
    problem = cast(Problem, error.problem)
    stream.write(
        json.dumps(
            problem.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _command_id(arguments: object | None) -> UUID | None:
    value = getattr(arguments, "command_id", None)
    return value if isinstance(value, UUID) else None
