from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from referencing import Registry, Resource

from tools.compatibility.contract import (
    CompatibilityError,
    CompatibilityReport,
    MatrixInput,
    ProbeResult,
    TelemetryContext,
)

JsonObject = dict[str, object]
_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _ROOT / "contracts"
_INPUT_SCHEMA_PATH = _CONTRACTS / "compatibility" / "matrix-input.schema.json"
_RESULT_SCHEMA_PATH = _CONTRACTS / "compatibility" / "matrix-result.schema.json"
_TELEMETRY_SCHEMA_PATH = _CONTRACTS / "observability" / "telemetry-context.schema.json"


def read_json_object(path: Path, *, label: str) -> JsonObject:
    """Read JSON without constructing a trusted domain value."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompatibilityError(f"invalid {label} JSON: {error}") from error
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise CompatibilityError(f"{label} root must be an object")
    return cast("JsonObject", raw)


def parse_matrix(raw: JsonObject) -> MatrixInput:
    """Apply the published schema before crossing into the frozen input model."""
    _validate(_input_schema(), raw, label="matrix input")
    return _model_from_raw(MatrixInput, raw, label="matrix input")


def parse_probe(raw: JsonObject) -> ProbeResult:
    """Apply the published probe-result fragment before accepting probe evidence."""
    result_schema = _result_schema()
    fragment: JsonObject = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"{result_schema['$id']}#/$defs/probe_result",
    }
    _validate(fragment, raw, label="probe result", extra_resources=(result_schema,))
    return _model_from_raw(ProbeResult, raw, label="probe result")


def parse_report(raw: JsonObject) -> CompatibilityReport:
    """Apply the exact published result schema before accepting report evidence."""
    _validate(_result_schema(), raw, label="compatibility report")
    return _model_from_raw(CompatibilityReport, raw, label="compatibility report")


def validate_telemetry(context: TelemetryContext) -> None:
    """Prove the hand-authored narrow L0 model matches the canonical contract."""
    raw = cast("JsonObject", context.model_dump(mode="json", by_alias=True))
    _validate(_telemetry_schema(), raw, label="telemetry context")


def validate_report_schema(raw: JsonObject) -> None:
    """Revalidate a typed report at its final serialization boundary."""
    _validate(_result_schema(), raw, label="compatibility report")


def _model_from_raw[ModelValue: BaseModel](
    model: type[ModelValue], raw: JsonObject, *, label: str
) -> ModelValue:
    try:
        return model.model_validate_json(json.dumps(raw, separators=(",", ":")))
    except PydanticValidationError as error:
        raise CompatibilityError(
            f"{label} violates the typed contract: {_bounded(error)}"
        ) from error


def _validate(
    schema: JsonObject,
    instance: object,
    *,
    label: str,
    extra_resources: tuple[JsonObject, ...] = (),
) -> None:
    resources = (*extra_resources, _telemetry_schema())
    registry: Registry[Any] = Registry()
    for resource_schema in resources:
        identifier = resource_schema.get("$id")
        if not isinstance(identifier, str):
            raise CompatibilityError("contract schema is missing a string $id")
        registry = registry.with_resource(
            identifier,
            Resource.from_contents(cast("dict[str, Any]", resource_schema)),
        )
    try:
        validator = Draft202012Validator(
            cast("dict[str, Any]", schema),
            format_checker=FormatChecker(),
            registry=registry,
        )
        validator.validate(instance)
    except (JsonSchemaValidationError, SchemaError) as error:
        path = "/".join(str(part) for part in error.absolute_path) or "<root>"
        raise CompatibilityError(
            f"{label} violates its published schema at {path}: {_bounded(error.message)}"
        ) from error


def _input_schema() -> JsonObject:
    return read_json_object(_INPUT_SCHEMA_PATH, label="matrix input schema")


def _result_schema() -> JsonObject:
    return read_json_object(_RESULT_SCHEMA_PATH, label="matrix result schema")


def _telemetry_schema() -> JsonObject:
    return read_json_object(_TELEMETRY_SCHEMA_PATH, label="telemetry schema")


def _bounded(value: object) -> str:
    text = " ".join(str(value).split())
    return text[:1000]
