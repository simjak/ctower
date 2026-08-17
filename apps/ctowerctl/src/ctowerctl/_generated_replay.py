"""Confined generated-operation replay executor for encrypted spool commands."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from ctower_client import CtowerClient, CtowerProblemError
from ctower_client.models import Problem
from ctower_client.operations import OPERATIONS, SpoolPolicy
from ctowerctl.spool import ReplayResponse, SpoolCommand, server_refusal

__all__: tuple[str, ...] = ()

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

_PATH_PARAMETER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class ReplayObservation:
    """In-memory current-invocation detail; authority is never persisted here."""

    response: ReplayResponse
    problem: Problem | None = None


@dataclass(slots=True)
class GeneratedReplayExecutor:
    """Replay only generated allowlisted mutation specs through CtowerClient."""

    client: CtowerClient
    observations: dict[UUID, ReplayObservation] = field(default_factory=dict)

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        response, problem = self._execute(command)
        self.observations[command.command_id] = ReplayObservation(response, problem)
        return response

    def _execute(self, command: SpoolCommand) -> tuple[ReplayResponse, Problem | None]:
        operation = OPERATIONS.get(command.operation_id)
        if (
            operation is None
            or not operation.mutation
            or operation.spool_policy is not SpoolPolicy.ALLOWED
            or operation.request_model is None
        ):
            return _local_refusal("operation_not_replayable"), None
        try:
            request = operation.request_model.model_validate_json(
                json.dumps(command.request_body, allow_nan=False, separators=(",", ":"))
            )
            path_arguments = _path_arguments(operation.path, command.path_parameters)
            method = cast(
                Callable[..., BaseModel],
                getattr(self.client, operation.client_method),
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            return _local_refusal("operation_schema_invalid"), None
        return _invoke(method, path_arguments, request, command)


def _invoke(
    method: Callable[..., BaseModel],
    path_arguments: tuple[UUID | str, ...],
    request: BaseModel,
    command: SpoolCommand,
) -> tuple[ReplayResponse, Problem | None]:
    try:
        result = method(*path_arguments, request, command_id=command.command_id)
    except CtowerProblemError as error:
        problem = cast(Problem, error.problem)
        return _problem_response(problem), problem
    except httpx.HTTPStatusError as error:
        return ReplayResponse(status_code=error.response.status_code), None
    except httpx.RequestError:
        return ReplayResponse(status_code=503), None
    except ValidationError:
        return ReplayResponse(status_code=200), None
    return _success_response(result), None


def _path_arguments(path: str, values: JsonObject) -> tuple[UUID | str, ...]:
    names = tuple(_PATH_PARAMETER.findall(path))
    if set(values) != set(names):
        raise ValueError("stored path parameters do not match generated operation")
    parsed: list[UUID | str] = []
    for name in names:
        value = values[name]
        if not isinstance(value, str):
            raise TypeError("stored path parameter is not a UUID string")
        try:
            parsed.append(UUID(value))
        except ValueError:
            if not re.fullmatch(r"[A-Z]{2,5}-[1-9][0-9]*", value):
                raise ValueError("stored path parameter is not a UUID or display key") from None
            parsed.append(value)
    return tuple(parsed)


def _success_response(result: BaseModel) -> ReplayResponse:
    payload = cast(JsonObject, json.loads(result.model_dump_json(by_alias=True, exclude_none=True)))
    raw_command_id = payload.get("command_id")
    raw_state = payload.get("durability_state")
    event_ids = payload.get("event_ids")
    if not isinstance(event_ids, list):
        single_event = payload.get("event_id")
        event_ids = [single_event] if isinstance(single_event, str) else []
    durability_state: Literal["accepted", "durability_pending"] | None = None
    if raw_state == "accepted":
        durability_state = "accepted"
    elif raw_state == "durability_pending":
        durability_state = "durability_pending"
    return ReplayResponse(
        status_code=200 if raw_state == "accepted" else 202,
        command_id=UUID(raw_command_id) if isinstance(raw_command_id, str) else None,
        durability_state=durability_state,
        response=payload,
        event_ids=tuple(str(item) for item in event_ids),
    )


def _problem_response(problem: Problem) -> ReplayResponse:
    code = _reason_code(problem.code)
    return ReplayResponse(
        status_code=problem.status,
        command_id=problem.command_id,
        problem_code=code,
        response={"code": problem.code, "status": problem.status},
        refusal=server_refusal(problem.status, problem.code),
    )


def _local_refusal(code: str) -> ReplayResponse:
    return ReplayResponse(status_code=422, problem_code=_reason_code(code))


def _reason_code(value: str) -> str:
    return value.replace("-", "_")[:64]
