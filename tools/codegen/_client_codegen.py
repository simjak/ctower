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
    required: bool


@dataclass(frozen=True, slots=True)
class _Operation:
    operation_id: str
    method: str
    path: str
    parameters: tuple[_Parameter, ...]
    request_model: str | None
    response_model: str | None
    success_models: tuple[tuple[int, str], ...]
    problem_models: tuple[tuple[int, str], ...]
    authenticated: bool
    refusal_only: bool


def render_client(document: dict[str, object], contract_digest: str) -> str:
    operations = _operations(document)
    model_names = sorted(
        {
            "TelemetryContext",
            *(model for operation in operations for _, model in operation.success_models),
            *(model for operation in operations for _, model in operation.problem_models),
            *(operation.request_model for operation in operations if operation.request_model),
        }
    )
    imports = "\n".join(f"    {name}," for name in model_names)
    methods = "\n\n".join(_render_method(operation) for operation in operations)
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
"""

from __future__ import annotations

from collections.abc import Mapping
import secrets
from types import TracebackType
from typing import Annotated, NoReturn, Protocol, Self, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, validate_call

from ctower_client.models import (
{imports}
)

__all__ = ["CtowerClient", "CtowerProblemError"]


class _ProblemModel(Protocol):
    code: str
    detail: str


class _StatusProblemModel(_ProblemModel, Protocol):
    status: int


class CtowerProblemError(Exception):
    """Typed RFC 9457 response from ctower."""

    def __init__(self, problem: _ProblemModel) -> None:
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


def _response[ModelT: BaseModel](
    response: httpx.Response,
    success_models: Mapping[int, type[ModelT]],
    problem_models: Mapping[int, type[BaseModel]],
) -> ModelT:
    model = success_models.get(response.status_code)
    if model is not None:
        return model.model_validate_json(response.content)
    if response.is_success:
        raise httpx.HTTPStatusError(
            "ctower returned an undeclared success status",
            request=response.request,
            response=response,
        )
    _raise_problem(response, problem_models)


def _raise_problem(
    response: httpx.Response,
    problem_models: Mapping[int, type[BaseModel]],
) -> NoReturn:
    content_type = response.headers.get("content-type", "").partition(";")[0]
    if content_type != "application/problem+json":
        raise httpx.HTTPStatusError(
            "ctower returned a non-problem failure", request=response.request, response=response
        )
    problem_model = problem_models.get(response.status_code)
    if problem_model is None:
        raise httpx.HTTPStatusError(
            "ctower returned an undeclared failure status",
            request=response.request,
            response=response,
        )
    problem = cast(_StatusProblemModel, problem_model.model_validate_json(response.content))
    if problem.status != response.status_code:
        raise ValueError("Problem status does not match HTTP response status")
    raise CtowerProblemError(problem)


def _refusal(
    response: httpx.Response,
    problem_models: Mapping[int, type[BaseModel]],
) -> NoReturn:
    if response.is_success:
        raise httpx.HTTPStatusError(
            "refusal-only operation returned success",
            request=response.request,
            response=response,
        )
    _raise_problem(response, problem_models)
'''


def _operations(document: dict[str, object]) -> tuple[_Operation, ...]:
    paths = _mapping(document.get("paths"), "paths")
    components = _mapping(document.get("components"), "components")
    parameter_definitions = _mapping(components.get("parameters"), "components.parameters")
    response_definitions = _mapping(components.get("responses"), "components.responses")
    operations: list[_Operation] = []
    for path, path_value in paths.items():
        for method, value in _mapping(path_value, f"path {path}").items():
            if method not in {"get", "post"}:
                continue
            operation = _mapping(value, f"{method} {path}")
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str):
                raise TypeError(f"{method} {path} lacks operationId")
            refusal_only = operation.get("x-ctower-refusal-only", False)
            if not isinstance(refusal_only, bool):
                raise TypeError(f"{operation_id} has non-boolean x-ctower-refusal-only")
            parameters = _parameters(operation, parameter_definitions)
            success_models = _success_models(operation, refusal_only=refusal_only)
            operations.append(
                _Operation(
                    operation_id=operation_id,
                    method=method,
                    path=path,
                    parameters=parameters,
                    request_model=_request_model(operation),
                    response_model=_response_model(
                        success_models,
                        refusal_only=refusal_only,
                    ),
                    success_models=success_models,
                    problem_models=_problem_models(operation, response_definitions),
                    authenticated=bool(operation.get("security")),
                    refusal_only=refusal_only,
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
        if location not in {"path", "header", "query"}:
            raise ValueError(f"unsupported parameter location {location}")
        required = parameter.get("required", False)
        if not isinstance(required, bool):
            raise TypeError(f"parameter {wire_name}.required must be a boolean")
        if location == "path" and not required:
            raise ValueError(f"path parameter {wire_name} must be required")
        schema = _mapping(parameter.get("schema"), f"parameter {wire_name}.schema")
        parameters.append(
            _Parameter(
                name=wire_name,
                location=location,
                python_name=_parameter_name(wire_name),
                python_type=_parameter_type(schema),
                required=required,
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


def _success_models(
    operation: Mapping[str, object],
    *,
    refusal_only: bool,
) -> tuple[tuple[int, str], ...]:
    responses = _mapping(operation.get("responses"), "responses")
    models: list[tuple[int, str]] = []
    for status, value in sorted(responses.items()):
        if not status.startswith("2"):
            continue
        if refusal_only:
            raise ValueError("refusal-only operation advertises a success response")
        try:
            status_code = int(status)
        except ValueError as error:
            raise ValueError(f"success response status must be exact: {status}") from error
        content = _mapping(_mapping(value, f"response {status}").get("content"), "response content")
        media = _mapping(content.get("application/json"), "response application/json")
        model = _schema_reference(_mapping(media.get("schema"), "response schema"))
        models.append((status_code, model))
    return tuple(models)


def _response_model(
    success_models: tuple[tuple[int, str], ...],
    *,
    refusal_only: bool,
) -> str | None:
    models = {model for _, model in success_models}
    if refusal_only:
        return None
    if not models:
        raise ValueError("operation has no JSON success response")
    if len(models) > 1:
        raise ValueError("one operation cannot expose multiple Python success model types")
    return next(iter(models))


def _problem_models(
    operation: Mapping[str, object], definitions: Mapping[str, object]
) -> tuple[tuple[int, str], ...]:
    responses = _mapping(operation.get("responses"), "responses")
    models: list[tuple[int, str]] = []
    for status, value in sorted(responses.items()):
        if status.startswith("2"):
            continue
        try:
            status_code = int(status)
        except ValueError as error:
            raise ValueError(f"failure response status must be exact: {status}") from error
        response = _mapping(value, f"response {status}")
        reference = response.get("$ref")
        if isinstance(reference, str):
            prefix = "#/components/responses/"
            if not reference.startswith(prefix):
                raise ValueError(f"unsupported response reference {reference}")
            name = reference.removeprefix(prefix)
            response = _mapping(definitions.get(name), f"response {name}")
        content = _mapping(response.get("content"), f"response {status}.content")
        media = _mapping(
            content.get("application/problem+json"),
            f"response {status} application/problem+json",
        )
        models.append((status_code, _schema_reference(_mapping(media.get("schema"), "schema"))))
    return tuple(models)


def _render_method(operation: _Operation) -> str:
    path_parameters = [item for item in operation.parameters if item.location == "path"]
    header_parameters = [item for item in operation.parameters if item.location == "header"]
    query_parameters = [item for item in operation.parameters if item.location == "query"]
    positional = [f"{item.python_name}: {item.python_type}" for item in path_parameters]
    if operation.request_model is not None:
        positional.append(f"request: {operation.request_model}")
    keyword_parameters = sorted(
        [*header_parameters, *query_parameters], key=lambda item: not item.required
    )
    keyword = [
        f"{item.python_name}: {item.python_type}" + ("" if item.required else " | None = None")
        for item in keyword_parameters
    ]
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
    if query_parameters:
        arguments.append(f"            params={_query_expression(query_parameters)},")
    arguments.append(f"            headers={_headers_expression(operation, header_parameters)},")
    call = "\n".join(arguments)
    response_type, response_call = _response_render(operation)
    return f"""    @validate_call(config=ConfigDict(strict=True, arbitrary_types_allowed=True))
    def {_snake_case(operation.operation_id)}(
{chr(10).join(signature)}
    ) -> {response_type}:
        response = self._http.{operation.method}(
{call}
        )
        {response_call}"""


def _response_render(operation: _Operation) -> tuple[str, str]:
    problems = ", ".join(f"{status}: {model}" for status, model in operation.problem_models)
    successes = ", ".join(f"{status}: {model}" for status, model in operation.success_models)
    if operation.response_model:
        call = f"return _response(response, {{{successes}}}, {{{problems}}})"
        return operation.response_model, call
    return "NoReturn", f"_refusal(response, {{{problems}}})"


def _query_expression(parameters: list[_Parameter]) -> str:
    entries = []
    for parameter in parameters:
        value = (
            f"str({parameter.python_name})"
            if parameter.python_type == "UUID"
            else parameter.python_name
        )
        entry = f'"{parameter.name}": {value}'
        if parameter.required:
            entries.append(entry)
        else:
            entries.append(f"**({{{entry}}} if {parameter.python_name} is not None else {{}})")
    return "{" + ", ".join(entries) + "}"


def _headers_expression(operation: _Operation, parameters: list[_Parameter]) -> str:
    command = next((item for item in parameters if item.name == "Idempotency-Key"), None)
    entries = (
        ["**self._auth_headers()"] if operation.authenticated else ['"Accept": "application/json"']
    )
    if operation.request_model is not None:
        entries.append('"Content-Type": "application/json"')
    for parameter in parameters:
        value = (
            f"str({parameter.python_name})"
            if parameter.python_type == "UUID"
            else parameter.python_name
        )
        entry = f'"{parameter.name}": {value}'
        if parameter.required:
            entries.append(entry)
        else:
            entries.append(f"**({{{entry}}} if {parameter.python_name} is not None else {{}})")
    base = "{\n" + "\n".join(f"                    {entry}," for entry in entries)
    base += "\n                }"
    if command is None:
        command_expression = "uuid4()"
    elif command.required:
        command_expression = command.python_name
    else:
        command_expression = f"({command.python_name} or uuid4())"
    ticket = next((item for item in operation.parameters if item.name == "ticket_id"), None)
    ticket_argument = f", ticket_id={ticket.python_name}" if ticket is not None else ""
    context = f"self._context({command_expression}{ticket_argument})"
    return (
        "self._telemetry_headers(\n"
        f"                {context},\n"
        f"                {base},\n"
        "            )"
    )


def _schema_reference(schema: Mapping[str, object]) -> str:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/components/schemas/"):
        raise ValueError("operation boundary schemas must be component references")
    return reference.removeprefix("#/components/schemas/")


def _parameter_type(schema: Mapping[str, object]) -> str:
    schema_type = schema.get("type")
    if schema_type == "string":
        base = "UUID" if schema.get("format") == "uuid" else "str"
        constraints = _bounds(schema, (("minLength", "min_length"), ("maxLength", "max_length")))
        return _annotated(base, constraints)
    if schema_type == "array":
        items = _mapping(schema.get("items"), "parameter array items")
        base = f"tuple[{_parameter_type(items)}, ...]"
        constraints = _bounds(schema, (("minItems", "min_length"), ("maxItems", "max_length")))
        return _annotated(base, constraints)
    if schema_type == "integer":
        return _annotated("int", _bounds(schema, (("minimum", "ge"), ("maximum", "le"))))
    if schema_type == "boolean":
        return "bool"
    raise ValueError(f"unsupported parameter schema: {dict(schema)}")


def _bounds(
    schema: Mapping[str, object], names: tuple[tuple[str, str], ...]
) -> list[tuple[str, object]]:
    return [(target, schema[source]) for source, target in names if source in schema]


def _annotated(base: str, constraints: list[tuple[str, object]]) -> str:
    if not constraints:
        return base
    arguments = ", ".join(f"{name}={json.dumps(value)}" for name, value in constraints)
    return f"Annotated[{base}, Field({arguments})]"


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
