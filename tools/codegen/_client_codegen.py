"""Render the synchronous HTTP client directly from OpenAPI operations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Parameter:
    name: str
    location: str
    python_name: str
    python_type: str


@dataclass(frozen=True, slots=True)
class _Operation:
    operation_id: str
    method: str
    path: str
    parameters: tuple[_Parameter, ...]
    request_model: str | None
    response_model: str
    authenticated: bool


def render_client(document: dict[str, object], contract_digest: str) -> str:
    operations = _operations(document)
    model_names = sorted(
        {
            "Problem",
            "TelemetryContext",
            *(operation.response_model for operation in operations),
            *(operation.request_model for operation in operations if operation.request_model),
        }
    )
    imports = "\n".join(f"    {name}," for name in model_names)
    methods = "\n\n".join(_render_method(operation) for operation in operations)
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
"""

from __future__ import annotations

import secrets
from types import TracebackType
from typing import Self
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel

from ctower_client.models import (
{imports}
)

__all__ = ["CtowerClient", "CtowerProblemError"]


class CtowerProblemError(Exception):
    """Typed RFC 9457 response from ctower."""

    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        super().__init__(f"{{problem.code}}: {{problem.detail}}")


class CtowerClient:
    """Thin synchronous client generated from the authored HTTP contract."""

    def __init__(
        self,
        base_url: str,
        *,
        credential: str | None = None,
        telemetry: TelemetryContext | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._credential = credential
        self._telemetry = telemetry
        self._http = httpx.Client(base_url=base_url, timeout=timeout_seconds)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

{methods}

    def _auth_headers(self) -> dict[str, str]:
        if self._credential is None:
            return {{"Accept": "application/json"}}
        return {{
            "Accept": "application/json",
            "Authorization": f"Bearer {{self._credential}}",
        }}

    def _command_headers(self, command_id: UUID) -> dict[str, str]:
        return {{
            **self._auth_headers(),
            "Content-Type": "application/json",
            "Idempotency-Key": str(command_id),
        }}

    def _context(self, command_id: UUID, *, ticket_id: UUID | None = None) -> TelemetryContext:
        if self._telemetry is not None:
            payload = self._telemetry.model_dump(mode="json", by_alias=True, exclude_none=True)
            payload["command_id"] = str(command_id)
            payload["ticket_id"] = str(ticket_id) if ticket_id is not None else None
            return TelemetryContext.model_validate(payload)
        return TelemetryContext(
            schema_id="ctower.telemetry-context/v1",
            trace_id=secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            trace_flags=1,
            correlation_id=str(command_id),
            causation_id=str(command_id),
            tenant_id="unresolved",
            actor_id="unresolved",
            command_id=str(command_id),
            ticket_id=str(ticket_id) if ticket_id is not None else None,
        )

    def _telemetry_headers(
        self, context: TelemetryContext, headers: dict[str, str]
    ) -> dict[str, str]:
        return {{
            **headers,
            "X-Ctower-Telemetry-Context": context.model_dump_json(by_alias=True),
        }}


def _response[ModelT: BaseModel](response: httpx.Response, model: type[ModelT]) -> ModelT:
    if response.is_success:
        return model.model_validate_json(response.content)
    content_type = response.headers.get("content-type", "").partition(";")[0]
    if content_type != "application/problem+json":
        raise httpx.HTTPStatusError(
            "ctower returned a non-problem failure", request=response.request, response=response
        )
    raise CtowerProblemError(Problem.model_validate_json(response.content))
'''


def _operations(document: dict[str, object]) -> tuple[_Operation, ...]:
    paths = _mapping(document.get("paths"), "paths")
    components = _mapping(document.get("components"), "components")
    parameter_definitions = _mapping(components.get("parameters"), "components.parameters")
    operations: list[_Operation] = []
    for path, path_value in paths.items():
        for method, value in _mapping(path_value, f"path {path}").items():
            if method not in {"get", "post"}:
                continue
            operation = _mapping(value, f"{method} {path}")
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str):
                raise TypeError(f"{method} {path} lacks operationId")
            parameters = _parameters(operation, parameter_definitions)
            operations.append(
                _Operation(
                    operation_id=operation_id,
                    method=method,
                    path=path,
                    parameters=parameters,
                    request_model=_request_model(operation),
                    response_model=_response_model(operation),
                    authenticated=bool(operation.get("security")),
                )
            )
    return tuple(sorted(operations, key=lambda item: item.operation_id))


def _parameters(
    operation: Mapping[str, object], definitions: Mapping[str, object]
) -> tuple[_Parameter, ...]:
    value = operation.get("parameters", [])
    if not isinstance(value, list):
        raise TypeError("operation parameters must be an array")
    parameters: list[_Parameter] = []
    for item in value:
        parameter = _mapping(item, "operation parameter")
        reference = parameter.get("$ref")
        if isinstance(reference, str):
            name = reference.removeprefix("#/components/parameters/")
            parameter = _mapping(definitions.get(name), f"parameter {name}")
        wire_name = str(parameter["name"])
        location = str(parameter["in"])
        schema = _mapping(parameter.get("schema"), f"parameter {wire_name}.schema")
        parameters.append(
            _Parameter(
                name=wire_name,
                location=location,
                python_name=_parameter_name(wire_name),
                python_type="UUID" if schema.get("format") == "uuid" else "str",
            )
        )
    return tuple(parameters)


def _request_model(operation: Mapping[str, object]) -> str | None:
    body = operation.get("requestBody")
    if body is None:
        return None
    content = _mapping(_mapping(body, "requestBody").get("content"), "requestBody.content")
    media = _mapping(content.get("application/json"), "requestBody application/json")
    return _schema_reference(_mapping(media.get("schema"), "requestBody schema"))


def _response_model(operation: Mapping[str, object]) -> str:
    responses = _mapping(operation.get("responses"), "responses")
    for status, value in sorted(responses.items()):
        if not status.startswith("2"):
            continue
        content = _mapping(_mapping(value, f"response {status}").get("content"), "response content")
        media = _mapping(content.get("application/json"), "response application/json")
        return _schema_reference(_mapping(media.get("schema"), "response schema"))
    raise ValueError("operation has no JSON success response")


def _render_method(operation: _Operation) -> str:
    path_parameters = [item for item in operation.parameters if item.location == "path"]
    header_parameters = [item for item in operation.parameters if item.location == "header"]
    positional = [f"{item.python_name}: {item.python_type}" for item in path_parameters]
    if operation.request_model is not None:
        positional.append(f"request: {operation.request_model}")
    keyword = [f"{item.python_name}: {item.python_type}" for item in header_parameters]
    signature = ["        self,", *(f"        {item}," for item in positional)]
    if keyword:
        signature.extend(["        *,", *(f"        {item}," for item in keyword)])
    path = operation.path
    for parameter in path_parameters:
        path = path.replace(
            "{" + parameter.name + "}",
            "{quote(str(" + parameter.python_name + "), safe='')}",
        )
    path_expression = f'f"{path}"' if path_parameters else json.dumps(path)
    arguments = [f"            {path_expression},"]
    if operation.request_model is not None:
        arguments.append("            content=request.model_dump_json(),")
    arguments.append(f"            headers={_headers_expression(operation, header_parameters)},")
    call = "\n".join(arguments)
    return f"""    def {_snake_case(operation.operation_id)}(
{chr(10).join(signature)}
    ) -> {operation.response_model}:
        response = self._http.{operation.method}(
{call}
        )
        return _response(response, {operation.response_model})"""


def _headers_expression(operation: _Operation, parameters: list[_Parameter]) -> str:
    command = next((item for item in parameters if item.name == "Idempotency-Key"), None)
    capability = next(
        (item for item in parameters if item.name == "X-Ctower-Bootstrap-Capability"), None
    )
    if operation.authenticated and command is not None:
        base = f"self._command_headers({command.python_name})"
    elif operation.authenticated:
        base = "self._auth_headers()"
    else:
        entries = ['"Content-Type": "application/json"']
        if command is not None:
            entries.append(f'"Idempotency-Key": str({command.python_name})')
        if capability is not None:
            entries.append(f'"X-Ctower-Bootstrap-Capability": {capability.python_name}')
        base = "{\n" + "\n".join(f"                    {entry}," for entry in entries)
        base += "\n                }"
    command_expression = command.python_name if command is not None else "uuid4()"
    ticket = next((item for item in operation.parameters if item.name == "ticket_id"), None)
    ticket_argument = f", ticket_id={ticket.python_name}" if ticket is not None else ""
    context = f"self._context({command_expression}{ticket_argument})"
    if base.startswith("{"):
        return (
            "self._telemetry_headers(\n"
            f"                {context},\n"
            f"                {base},\n"
            "            )"
        )
    return f"self._telemetry_headers(\n                {context}, {base}\n            )"


def _schema_reference(schema: Mapping[str, object]) -> str:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/components/schemas/"):
        raise ValueError("operation boundary schemas must be component references")
    return reference.removeprefix("#/components/schemas/")


def _parameter_name(name: str) -> str:
    aliases = {
        "Idempotency-Key": "command_id",
        "X-Ctower-Bootstrap-Capability": "capability",
    }
    return aliases.get(name, name.replace("-", "_").lower())


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast(Mapping[str, object], value)
