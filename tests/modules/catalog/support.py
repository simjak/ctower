from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ruamel.yaml import YAML

from ctower_kernel.catalog import CompanyBundle
from ctower_kernel.catalog.interface import JsonValue

ROOT = Path(__file__).parents[3]


class FileSchemas:
    def __init__(self) -> None:
        self._schemas = _load_schemas()

    def schema_for(self, schema_ref: str) -> dict[str, JsonValue] | None:
        return self._schemas.get(schema_ref)


def minimal_bundle() -> CompanyBundle:
    raw = cast(
        dict[str, JsonValue],
        YAML(typ="safe", pure=True).load(
            (ROOT / "company/company.bundle.yaml").read_text(encoding="utf-8")
        ),
    )
    return CompanyBundle.model_validate_json(json.dumps(raw))


def _load_schemas() -> dict[str, dict[str, JsonValue]]:
    schemas: dict[str, dict[str, JsonValue]] = {}
    for path in (ROOT / "contracts").rglob("*.schema.json"):
        raw = cast(dict[str, JsonValue], json.loads(path.read_text(encoding="utf-8")))
        properties = raw.get("properties")
        if not isinstance(properties, dict):
            continue
        schema_field = properties.get("schema")
        if not isinstance(schema_field, dict):
            continue
        schema_ref = schema_field.get("const")
        if isinstance(schema_ref, str):
            schemas[schema_ref] = raw
    return schemas
