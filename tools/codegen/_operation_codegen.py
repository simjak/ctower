"""Render the generated, closed-world operation and replay metadata registry."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

__all__: tuple[str, ...] = ()

type _Method = Literal["GET", "POST"]
type _SpoolPolicy = Literal["allowed", "forbidden"]


@dataclass(frozen=True, slots=True)
class _Operation:
    operation_id: str
    client_method: str
    method: _Method
    path: str
    request_model: str | None
    response_model: str | None
    cli_names: tuple[str, ...]
    mutation: bool
    spool_policy: _SpoolPolicy
    principal: str | None
    refusal_only: bool


def render_operations(document: dict[str, object], contract_digest: str) -> str:
    operations = _operations(document)
    entries = "\n".join(_entry(operation) for operation in operations)
    cli_entries = "\n".join(
        f"        {json.dumps(cli_name)}: OPERATIONS[{json.dumps(operation.operation_id)}],"
        for operation in operations
        for cli_name in operation.cli_names
    )
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel

from ctower_client import models as _models

__all__ = [
    "CLI_OPERATIONS",
    "OPERATIONS",
    "OperationSpec",
    "SpoolPolicy",
    "operation_for_cli",
]


class SpoolPolicy(StrEnum):
    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    client_method: str
    method: Literal["GET", "POST"]
    path: str
    request_model: type[BaseModel] | None
    response_model: type[BaseModel] | None
    cli_names: tuple[str, ...]
    mutation: bool
    spool_policy: SpoolPolicy
    principal: str | None
    refusal_only: bool


OPERATIONS = MappingProxyType(
    {{
{entries}
    }}
)

CLI_OPERATIONS = MappingProxyType(
    {{
{cli_entries}
    }}
)


def operation_for_cli(cli_name: str) -> OperationSpec | None:
    """Resolve only an authored CLI spelling; never dispatch arbitrary operation IDs."""

    return CLI_OPERATIONS.get(cli_name)
'''


def _operations(document: dict[str, object]) -> tuple[_Operation, ...]:
    paths = _mapping(document.get("paths"), "paths")
    operations: list[_Operation] = []
    operation_ids: set[str] = set()
    cli_names: set[str] = set()
    for path, path_value in paths.items():
        for method, value in _mapping(path_value, f"path {path}").items():
            if method not in {"get", "post"}:
                continue
            operation = _operation(path, method, _mapping(value, f"{method} {path}"))
            if operation.operation_id in operation_ids:
                raise ValueError(f"duplicate operation ID {operation.operation_id}")
            duplicate_cli = cli_names.intersection(operation.cli_names)
            if duplicate_cli:
                raise ValueError(f"duplicate CLI operation names: {sorted(duplicate_cli)}")
            operation_ids.add(operation.operation_id)
            cli_names.update(operation.cli_names)
            operations.append(operation)
    return tuple(sorted(operations, key=lambda item: item.operation_id))


def _operation(path: str, method: str, value: Mapping[str, object]) -> _Operation:
    operation_id = value.get("operationId")
    if not isinstance(operation_id, str):
        raise TypeError(f"{method} {path} lacks operationId")
    mutation, spool = _mutation_and_spool(operation_id, value)
    principal, refusal_only = _principal_and_refusal(
        operation_id,
        value,
        mutation=mutation,
        spool=spool,
    )
    return _Operation(
        operation_id=operation_id,
        client_method=_snake_case(operation_id),
        method=cast(_Method, method.upper()),
        path=path,
        request_model=_request_model(value),
        response_model=_response_model(value, refusal_only=refusal_only),
        cli_names=_cli_names(operation_id, value.get("x-ctower-cli")),
        mutation=mutation,
        spool_policy=spool,
        principal=principal,
        refusal_only=refusal_only,
    )


def _mutation_and_spool(
    operation_id: str,
    value: Mapping[str, object],
) -> tuple[bool, _SpoolPolicy]:
    mutation = value.get("x-ctower-mutation")
    if not isinstance(mutation, bool):
        raise TypeError(f"{operation_id} lacks boolean x-ctower-mutation")
    spool = value.get("x-ctower-spool")
    if spool not in {"allowed", "forbidden"}:
        raise ValueError(f"{operation_id} lacks exact x-ctower-spool policy")
    if not mutation and spool != "forbidden":
        raise ValueError(f"query operation {operation_id} cannot be spooled")
    return mutation, spool


def _principal_and_refusal(
    operation_id: str,
    value: Mapping[str, object],
    *,
    mutation: bool,
    spool: _SpoolPolicy,
) -> tuple[str | None, bool]:
    refusal_only = value.get("x-ctower-refusal-only", False)
    if not isinstance(refusal_only, bool):
        raise TypeError(f"{operation_id} has non-boolean x-ctower-refusal-only")
    principal = value.get("x-ctower-principal")
    if principal is not None and (not isinstance(principal, str) or not principal):
        raise TypeError(f"{operation_id} has invalid x-ctower-principal")
    if refusal_only and (mutation or spool != "forbidden"):
        raise ValueError(
            f"refusal-only operation {operation_id} must be non-mutating and unspoolable"
        )
    return principal, refusal_only


def _cli_names(operation_id: str, value: object) -> tuple[str, ...]:
    candidates = value if isinstance(value, list) else [value]
    names = tuple(item for item in candidates if isinstance(item, str) and item.strip() == item)
    if len(names) != len(candidates) or not names or len(names) != len(set(names)):
        raise ValueError(f"{operation_id} has invalid x-ctower-cli names")
    return names


def _request_model(operation: Mapping[str, object]) -> str | None:
    body = operation.get("requestBody")
    if body is None:
        return None
    content = _mapping(_mapping(body, "requestBody").get("content"), "requestBody.content")
    media = _mapping(content.get("application/json"), "requestBody application/json")
    return _schema_reference(_mapping(media.get("schema"), "requestBody schema"))


def _response_model(operation: Mapping[str, object], *, refusal_only: bool) -> str | None:
    responses = _mapping(operation.get("responses"), "responses")
    for status, value in sorted(responses.items()):
        if not status.startswith("2"):
            continue
        if refusal_only:
            raise ValueError("refusal-only operation advertises a success response")
        response = _mapping(value, f"response {status}")
        content = _mapping(response.get("content"), f"response {status}.content")
        media = _mapping(content.get("application/json"), "response application/json")
        return _schema_reference(_mapping(media.get("schema"), "response schema"))
    if refusal_only:
        return None
    raise ValueError("operation has no JSON success response")


def _entry(operation: _Operation) -> str:
    request = (
        f"_models.{operation.request_model}" if operation.request_model is not None else "None"
    )
    response = (
        f"_models.{operation.response_model}" if operation.response_model is not None else "None"
    )
    cli_names = repr(operation.cli_names)
    return f"""        {json.dumps(operation.operation_id)}: OperationSpec(
            operation_id={json.dumps(operation.operation_id)},
            client_method={json.dumps(operation.client_method)},
            method={json.dumps(operation.method)},
            path={json.dumps(operation.path)},
            request_model={request},
            response_model={response},
            cli_names={cli_names},
            mutation={operation.mutation!r},
            spool_policy=SpoolPolicy.{operation.spool_policy.upper()},
            principal={operation.principal!r},
            refusal_only={operation.refusal_only!r},
        ),"""


def _schema_reference(schema: Mapping[str, object]) -> str:
    reference = schema.get("$ref")
    prefix = "#/components/schemas/"
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise ValueError("operation boundary schemas must be component references")
    return reference.removeprefix(prefix)


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast(Mapping[str, object], value)
