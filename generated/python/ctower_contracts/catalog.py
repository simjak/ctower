"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:590fd2134945ee6e4a41259bb4f5d342c2b320ae96184283b5c231f1ac5dff9b
"""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from importlib.resources import files
import json
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

__all__ = ["CATALOG", "ContractCatalog", "schema_for", "validator_for", "verify_all"]

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@cache
def _payload() -> dict[str, object]:
    raw = files("ctower_contracts").joinpath("schemas.json").read_text(encoding="utf-8")
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("generated contract resource is malformed")
    return cast(dict[str, object], parsed)


class ContractCatalog:
    """Immutable local schema lookup and validator registry."""

    def schema_for(self, schema_ref: str) -> dict[str, JsonValue] | None:
        aliases, resources = self._resources()
        path = aliases.get(schema_ref)
        if path is None:
            return None
        return deepcopy(resources[path])

    def validator_for(self, schema_ref: str) -> Draft202012Validator:
        aliases, resources = self._resources()
        path = aliases.get(schema_ref)
        if path is None:
            raise KeyError(schema_ref)
        return Draft202012Validator(
            resources[path],
            registry=_registry(resources),
            format_checker=FormatChecker(),
        )

    def verify_all(self) -> int:
        _, resources = self._resources()
        registry = _registry(resources)
        for document in resources.values():
            Draft202012Validator.check_schema(document)
            schema_id = document.get("$id")
            if not isinstance(schema_id, str):
                raise RuntimeError("generated contract resource lacks $id")
            resolver = registry.resolver(base_uri=schema_id)
            for reference in _references(document):
                resolver.lookup(reference)
        return len(resources)

    def _resources(
        self,
    ) -> tuple[dict[str, str], dict[str, dict[str, JsonValue]]]:
        payload = _payload()
        aliases = cast(dict[str, str], payload["aliases"])
        resources = cast(dict[str, dict[str, JsonValue]], payload["resources"])
        return aliases, resources


CATALOG = ContractCatalog()


def _registry(resources: dict[str, dict[str, JsonValue]]) -> Registry:
    registry = Registry()
    for document in resources.values():
        schema_id = document.get("$id")
        if not isinstance(schema_id, str):
            raise RuntimeError("generated contract resource lacks $id")
        registry = registry.with_resource(schema_id, Resource.from_contents(document))
    return registry


def _references(value: JsonValue) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(reference for item in value for reference in _references(item))
    if not isinstance(value, dict):
        return ()
    candidate = value.get("$ref")
    own = (candidate,) if isinstance(candidate, str) else ()
    return own + tuple(
        reference for item in value.values() for reference in _references(item)
    )


def schema_for(schema_ref: str) -> dict[str, JsonValue] | None:
    return CATALOG.schema_for(schema_ref)


def validator_for(schema_ref: str) -> Draft202012Validator:
    return CATALOG.validator_for(schema_ref)


def verify_all() -> int:
    return CATALOG.verify_all()
