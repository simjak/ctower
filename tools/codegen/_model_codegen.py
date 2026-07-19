"""Render strict Pydantic boundary models directly from OpenAPI schemas."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import cast

__all__: tuple[str, ...] = ()

_INLINE_WIDTH = 88
_MAX_LINE_WIDTH = 100


def render_models(document: dict[str, object], contract_digest: str) -> str:
    schemas = _schemas(document)
    names = tuple(sorted(schemas))
    sections = [_header(contract_digest, names), _boundary_model()]
    for name in _schema_order(schemas):
        schema = _mapping(schemas[name], f"schema {name}")
        sections.append(_render_schema(name, schema))
    return "\n\n\n".join(sections).rstrip() + "\n"


def render_init(document: dict[str, object], contract_digest: str) -> str:
    names = tuple(sorted(_schemas(document)))
    imports = "\n".join(f"    {name}," for name in sorted(names, key=str.lower))
    exports = "\n".join(
        f'    "{name}",' for name in sorted((*names, "CtowerClient", "CtowerProblemError"))
    )
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
"""

from ctower_client.client import CtowerClient, CtowerProblemError
from ctower_client.models import (
{imports}
)

__all__ = [
{exports}
]
'''


def _header(contract_digest: str, names: tuple[str, ...]) -> str:
    exports = "\n".join(f'    "{name}",' for name in names)
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
{exports}
]'''


def _boundary_model() -> str:
    return """class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)"""


def _schemas(document: dict[str, object]) -> dict[str, object]:
    components = _mapping(document.get("components"), "components")
    return dict(_mapping(components.get("schemas"), "components.schemas"))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _schema_order(schemas: dict[str, object]) -> tuple[str, ...]:
    dependencies = {name: _references(schema) & schemas.keys() for name, schema in schemas.items()}
    ordered: list[str] = []
    remaining = set(schemas)
    while remaining:
        ready = sorted(name for name in remaining if dependencies[name] <= set(ordered))
        if not ready:
            ready = [min(remaining)]
        ordered.extend(ready)
        remaining.difference_update(ready)
    return tuple(ordered)


def _references(value: object) -> set[str]:
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        found = {_reference_name(reference)} if isinstance(reference, str) else set()
        return found | {item for nested in value.values() for item in _references(nested)}
    if isinstance(value, list):
        return {item for nested in value for item in _references(nested)}
    return set()


def _render_schema(name: str, schema: Mapping[str, object]) -> str:
    if schema.get("type") == "string" and isinstance(schema.get("enum"), list):
        values = cast(list[object], schema["enum"])
        members = "\n".join(
            f"    {_enum_member(str(value))} = {_literal(str(value))}" for value in values
        )
        return f"class {name}(StrEnum):\n{members}"
    if schema.get("type") != "object":
        raise ValueError(f"schema {name} must be an object or string enum")
    properties = _mapping(schema.get("properties"), f"schema {name}.properties")
    required_value = schema.get("required", [])
    if not isinstance(required_value, list):
        raise TypeError(f"schema {name}.required must be an array")
    required = {str(item) for item in required_value}
    fields = [
        _render_field(
            field_name,
            _mapping(value, f"{name}.{field_name}"),
            required=field_name in required,
        )
        for field_name, value in properties.items()
    ]
    return f"class {name}(_BoundaryModel):\n" + "\n".join(fields)


def _render_field(name: str, schema: Mapping[str, object], *, required: bool) -> str:
    expression = _type_expression(schema)
    if not required and "None" not in expression.split(" | "):
        expression += " | None"
    aliases = {"type": "type_uri", "schema": "schema_id"}
    python_name = aliases.get(name, name)
    suffix = ""
    if name in aliases:
        suffix = f' = Field(alias="{name}", serialization_alias="{name}")'
    elif not required:
        suffix = " = None"
    rendered = f"    {python_name}: {expression}{suffix}"
    if len(rendered) <= _MAX_LINE_WIDTH or name not in aliases:
        return rendered
    return (
        f"    {python_name}: {expression} = Field(\n"
        f'        alias="{name}", serialization_alias="{name}"\n'
        "    )"
    )


def _type_expression(schema: Mapping[str, object]) -> str:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return _reference_name(reference)
    if "const" in schema:
        return f"Literal[{_literal(str(schema['const']))}]"
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        return " | ".join(_type_expression(_mapping(item, "oneOf item")) for item in one_of)
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        expressions = [
            "None" if item == "null" else _type_expression({**schema, "type": item})
            for item in schema_type
        ]
        return " | ".join(expressions)
    return _primitive_expression(schema, schema_type)


def _primitive_expression(schema: Mapping[str, object], schema_type: object) -> str:
    if schema_type == "array":
        return _array_expression(schema)
    if schema_type == "string":
        return _string_expression(schema)
    if schema_type == "integer":
        return _integer_expression(schema)
    if schema_type == "boolean":
        return "bool"
    if schema_type == "object":
        return "dict[str, object]"
    raise ValueError(f"unsupported OpenAPI schema shape: {dict(schema)}")


def _array_expression(schema: Mapping[str, object]) -> str:
    items = _mapping(schema.get("items"), "array items")
    base = f"tuple[{_type_expression(items)}, ...]"
    minimum = schema.get("minItems")
    return _annotated(base, [("min_length", minimum)] if isinstance(minimum, int) else [])


def _string_expression(schema: Mapping[str, object]) -> str:
    enum = schema.get("enum")
    if isinstance(enum, list):
        values = [_literal(str(value)) for value in enum]
        inline = "Literal[" + ", ".join(values) + "]"
        if len(inline) <= _INLINE_WIDTH:
            return inline
        return "Literal[\n        " + ",\n        ".join(values) + ",\n    ]"
    base = {"uuid": "UUID", "date-time": "datetime"}.get(str(schema.get("format")), "str")
    constraints: list[tuple[str, object]] = []
    for source, target in (
        ("minLength", "min_length"),
        ("maxLength", "max_length"),
        ("pattern", "pattern"),
    ):
        if source in schema:
            constraints.append((target, schema[source]))
    return _annotated(base, constraints)


def _integer_expression(schema: Mapping[str, object]) -> str:
    constraints = []
    if "minimum" in schema:
        constraints.append(("ge", schema["minimum"]))
    if "maximum" in schema:
        constraints.append(("le", schema["maximum"]))
    return _annotated("int", constraints)


def _annotated(base: str, constraints: list[tuple[str, object]]) -> str:
    if not constraints:
        return base
    arguments = ", ".join(f"{name}={_literal(value)}" for name, value in constraints)
    return f"Annotated[{base}, Field({arguments})]"


def _reference_name(reference: str) -> str:
    prefix = "#/components/schemas/"
    if not reference.startswith(prefix):
        raise ValueError(f"unsupported schema reference {reference}")
    return reference.removeprefix(prefix)


def _enum_member(value: str) -> str:
    member = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    return f"VALUE_{member}" if member[:1].isdigit() else member


def _literal(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)
