"""Render strict Pydantic boundary models directly from OpenAPI schemas."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import cast

from tools.codegen._json_integer_codegen import (
    JSON_INTEGER_MAXIMUM,
    JSON_INTEGER_MINIMUM,
    require_json_integer_profile,
)
from tools.codegen._rfc3339_codegen import require_rfc3339_profile

__all__: tuple[str, ...] = ()

_INLINE_WIDTH = 88
_MAX_LINE_WIDTH = 100


def render_models(document: dict[str, object], contract_digest: str) -> str:
    require_json_integer_profile(document)
    require_rfc3339_profile(document)
    schemas = _schemas(document)
    names = tuple(sorted(schemas))
    sections = [_header(contract_digest, names), _scalar_validators(), _boundary_model()]
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

from datetime import datetime, timedelta, timezone
from enum import StrEnum
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter

__all__ = [
{exports}
]'''


def _scalar_validators() -> str:
    return r"""_RFC3339_PATTERN = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,6}))?"
    r"(?P<zone>Z|(?P<sign>[+-])(?P<offset_hour>[0-9]{2}):"
    r"(?P<offset_minute>[0-9]{2}))$"
)
_ABSOLUTE_URI_ADAPTER = TypeAdapter(AnyUrl)


def _validate_rfc3339(value: object) -> datetime:
    if isinstance(value, datetime):
        offset = value.utcoffset()
        if offset is None:
            raise ValueError("RFC 3339 timestamps require a timezone")
        offset_seconds = offset.total_seconds()
        if offset_seconds % 60 != 0 or abs(offset_seconds) > 86_340:
            raise ValueError("RFC 3339 timestamp has an invalid numeric offset")
        return value
    if not isinstance(value, str):
        raise ValueError("RFC 3339 timestamp must be a string or datetime")
    match = _RFC3339_PATTERN.fullmatch(value)
    if match is None or match.group("zone") == "-00:00":
        raise ValueError("timestamp is outside the authored RFC 3339 profile")
    parts = {name: int(match.group(name)) for name in (
        "year", "month", "day", "hour", "minute", "second"
    )}
    if not 1 <= parts["year"] <= 9999:
        raise ValueError("RFC 3339 timestamp year is outside 0001-9999")
    if parts["hour"] > 23 or parts["minute"] > 59 or parts["second"] > 59:
        raise ValueError("RFC 3339 timestamp has an invalid time")
    offset_hour = int(match.group("offset_hour") or 0)
    offset_minute = int(match.group("offset_minute") or 0)
    if offset_hour > 23 or offset_minute > 59:
        raise ValueError("RFC 3339 timestamp has an invalid numeric offset")
    offset = timedelta(hours=offset_hour, minutes=offset_minute)
    if match.group("sign") == "-":
        offset = -offset
    zone = timezone.utc if match.group("zone") == "Z" else timezone(offset)
    fraction = (match.group("fraction") or "").ljust(6, "0")
    try:
        return datetime(
            parts["year"],
            parts["month"],
            parts["day"],
            parts["hour"],
            parts["minute"],
            parts["second"],
            int(fraction or 0),
            zone,
        )
    except ValueError as error:
        raise ValueError("timestamp is outside the proleptic Gregorian calendar") from error


def _validate_absolute_uri(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("absolute URI must be a string")
    try:
        _ABSOLUTE_URI_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError("string is not an absolute URI") from error
    return value


_AbsoluteUri = Annotated[str, BeforeValidator(_validate_absolute_uri)]
_Rfc3339DateTime = Annotated[datetime, BeforeValidator(_validate_rfc3339)]"""


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
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        variants = " | ".join(
            _type_expression(_mapping(item, f"schema {name}.oneOf item")) for item in one_of
        )
        return f"type {name} = {variants}"
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
        return f"Literal[{_literal(schema['const'])}]"
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
    if schema_type == "null":
        return "None"
    if schema_type == "object":
        return "dict[str, object]"
    raise ValueError(f"unsupported OpenAPI schema shape: {dict(schema)}")


def _array_expression(schema: Mapping[str, object]) -> str:
    items = _mapping(schema.get("items"), "array items")
    base = f"tuple[{_type_expression(items)}, ...]"
    constraints: list[tuple[str, object]] = []
    for source, target in (("minItems", "min_length"), ("maxItems", "max_length")):
        if source in schema:
            constraints.append((target, schema[source]))
    return _annotated(base, constraints)


def _string_expression(schema: Mapping[str, object]) -> str:
    enum = schema.get("enum")
    if isinstance(enum, list):
        values = [_literal(str(value)) for value in enum]
        inline = "Literal[" + ", ".join(values) + "]"
        if len(inline) <= _INLINE_WIDTH:
            return inline
        return "Literal[\n        " + ",\n        ".join(values) + ",\n    ]"
    base = {
        "uuid": "UUID",
        "date-time": "_Rfc3339DateTime",
        "uri": "_AbsoluteUri",
    }.get(str(schema.get("format")), "str")
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
    minimum = schema.get("minimum", JSON_INTEGER_MINIMUM)
    maximum = schema.get("maximum", JSON_INTEGER_MAXIMUM)
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, (int, float))
        or isinstance(maximum, bool)
        or not isinstance(maximum, (int, float))
    ):
        raise TypeError("integer bounds must be numbers")
    lower = max(JSON_INTEGER_MINIMUM, minimum)
    upper = min(JSON_INTEGER_MAXIMUM, maximum)
    if lower > upper:
        raise ValueError("integer schema has no value inside the lossless JSON range")
    constraints: list[tuple[str, object]] = [("ge", lower), ("le", upper)]
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
