"""Strict JSON, RFC 8785 canonicalization, digest, and contract validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .refusal import MigrationRefusal, RefusalCode

__all__ = (
    "JsonValue",
    "artifact_digest",
    "canonical_bytes",
    "canonical_digest",
    "sha256_digest",
    "strict_json",
    "validate_contract",
)

JsonValue = None | bool | int | str | list["JsonValue"] | dict[str, "JsonValue"]
MAX_JSON_BYTES = 16 * 1024 * 1024


def _pairs(pairs: Iterable[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationRefusal(RefusalCode.DUPLICATE_JSON_KEY, "duplicate object member")
        result[key] = value
    return result


def strict_json(data: bytes, *, context: str) -> JsonValue:
    if len(data) > MAX_JSON_BYTES:
        raise MigrationRefusal(RefusalCode.SOURCE_TOO_LARGE, context)
    try:
        text = data.decode("utf-8")
        return cast(
            JsonValue,
            json.loads(
                text,
                object_pairs_hook=_pairs,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
        )
    except MigrationRefusal:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise MigrationRefusal(RefusalCode.MALFORMED_JSON, context) from error


def _reject_number(value: str) -> JsonValue:
    del value
    raise ValueError("non-integral or non-finite JSON number")


def canonical_bytes(value: JsonValue | Mapping[str, Any]) -> bytes:
    try:
        return rfc8785.dumps(cast(Any, value))
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError) as error:
        raise MigrationRefusal(RefusalCode.CONTRACT_INVALID, "outside RFC 8785 domain") from error


def sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def canonical_digest(value: JsonValue | Mapping[str, Any]) -> str:
    return sha256_digest(canonical_bytes(value))


def artifact_digest(value: Mapping[str, Any], *excluded: str) -> str:
    payload = {key: item for key, item in value.items() if key not in excluded}
    return canonical_digest(payload)


def validate_contract(schema_name: str, value: Mapping[str, Any]) -> None:
    schema_root = Path(__file__).resolve().parents[4] / "contracts" / "domain"
    resources: list[tuple[str, Resource[Any]]] = []
    for path in schema_root.rglob("*.schema.json"):
        contents = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        schema_id = contents.get("$id")
        if isinstance(schema_id, str):
            resources.append((schema_id, Resource.from_contents(contents)))
    target_path = schema_root / "migration" / schema_name
    target = cast(dict[str, Any], json.loads(target_path.read_text(encoding="utf-8")))
    validator = Draft202012Validator(
        target,
        registry=Registry().with_resources(resources),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
    if errors:
        location = ".".join(str(item) for item in errors[0].absolute_path) or "<root>"
        raise MigrationRefusal(RefusalCode.CONTRACT_INVALID, f"{schema_name}:{location}")
