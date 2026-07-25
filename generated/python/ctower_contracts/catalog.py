"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:d110be83601a088f160efa3fa859e9e3ed40119c7ab47e3e60d43a170e7163ce
"""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from importlib.resources import files
import json
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

__all__ = ["CATALOG", "ContractCatalog", "schema_for", "validator_for"]

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
        registry = Registry()
        for document in resources.values():
            schema_id = document.get("$id")
            if not isinstance(schema_id, str):
                raise RuntimeError("generated contract resource lacks $id")
            registry = registry.with_resource(schema_id, Resource.from_contents(document))
        return Draft202012Validator(
            resources[path],
            registry=registry,
            format_checker=FormatChecker(),
        )

    def _resources(
        self,
    ) -> tuple[dict[str, str], dict[str, dict[str, JsonValue]]]:
        payload = _payload()
        aliases = cast(dict[str, str], payload["aliases"])
        resources = cast(dict[str, dict[str, JsonValue]], payload["resources"])
        return aliases, resources


CATALOG = ContractCatalog()


def schema_for(schema_ref: str) -> dict[str, JsonValue] | None:
    return CATALOG.schema_for(schema_ref)


def validator_for(schema_ref: str) -> Draft202012Validator:
    return CATALOG.validator_for(schema_ref)
