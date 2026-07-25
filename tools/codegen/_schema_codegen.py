"""Vendor authored JSON schemas into a local-only generated runtime package."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urldefrag, urlsplit

__all__: tuple[str, ...] = ()

_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."
_CONTRACTS = Path("contracts")
_PACKAGE = Path("generated/python/ctower_contracts")


@dataclass(frozen=True, slots=True)
class SchemaResources:
    outputs: tuple[tuple[Path, str], ...]
    inputs: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class _Source:
    path: Path
    absolute: Path
    schema_id: str
    document: dict[str, object]
    digest: str
    aliases: tuple[str, ...]


def render_schema_resources(root: Path, contract_digest: str) -> SchemaResources:
    sources = _load_sources(root)
    resources, aliases = _runtime_resources(root, sources)
    payload = {
        "_notice": _NOTICE,
        "aliases": aliases,
        "resources": resources,
        "schema": "ctower.runtime-contracts/v1",
        "sources": [
            {
                "id": source.schema_id,
                "path": source.path.as_posix(),
                "sha256": f"sha256:{source.digest}",
            }
            for source in sources
        ],
    }
    outputs = (
        (_PACKAGE / "__init__.py", _render_init(contract_digest)),
        (_PACKAGE / "catalog.py", _render_catalog(contract_digest)),
        (_PACKAGE / "schemas.json", json.dumps(payload, indent=2, sort_keys=True) + "\n"),
    )
    return SchemaResources(outputs=outputs, inputs=tuple(source.path for source in sources))


def _load_sources(root: Path) -> tuple[_Source, ...]:
    contract_root = (root / _CONTRACTS).resolve()
    sources: list[_Source] = []
    ids: dict[str, Path] = {}
    aliases: dict[str, Path] = {}
    for path in sorted(contract_root.rglob("*.schema.json")):
        absolute = path.resolve()
        if path.is_symlink() or not absolute.is_relative_to(contract_root):
            raise ValueError(f"schema source escapes contracts: {path}")
        relative = absolute.relative_to(root)
        document = _load_document(absolute, relative)
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise ValueError(f"runtime schema lacks $id: {relative}")
        _register(ids, schema_id, relative, "schema ID collision")
        named = _schema_aliases(document)
        for name in named:
            _register(aliases, name, relative, "runtime schema name collision")
        sources.append(
            _Source(
                path=relative,
                absolute=absolute,
                schema_id=schema_id,
                document=document,
                digest=hashlib.sha256(absolute.read_bytes()).hexdigest(),
                aliases=named,
            )
        )
    if not sources:
        raise ValueError("no authored runtime schemas found")
    return tuple(sources)


def _load_document(path: Path, relative: Path) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load runtime schema {relative}: {error}") from error
    if not isinstance(payload, dict):
        raise TypeError(f"runtime schema must be an object: {relative}")
    return cast(dict[str, object], payload)


def _schema_aliases(document: Mapping[str, object]) -> tuple[str, ...]:
    properties = document.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    schema_field = properties.get("schema")
    if not isinstance(schema_field, Mapping):
        return ()
    name = schema_field.get("const")
    return (name,) if isinstance(name, str) else ()


def _register(
    seen: dict[str, Path],
    name: str,
    path: Path,
    label: str,
) -> None:
    previous = seen.get(name)
    if previous is not None and previous != path:
        raise ValueError(f"{label} {name}: {previous} and {path}")
    seen[name] = path


def _runtime_resources(
    root: Path,
    sources: tuple[_Source, ...],
) -> tuple[dict[str, object], dict[str, str]]:
    contract_root = (root / _CONTRACTS).resolve()
    by_path = {source.absolute: source for source in sources}
    by_id = {source.schema_id: source for source in sources}
    resources = {
        source.path.as_posix(): _rewrite_references(
            source.document,
            source,
            contract_root,
            by_path,
            by_id,
        )
        for source in sources
    }
    aliases: dict[str, str] = {}
    for source in sources:
        for name in (source.schema_id, *source.aliases):
            aliases[name] = source.path.as_posix()
    return resources, dict(sorted(aliases.items()))


def _rewrite_references(
    value: object,
    source: _Source,
    contract_root: Path,
    by_path: Mapping[Path, _Source],
    by_id: Mapping[str, _Source],
) -> object:
    if isinstance(value, list):
        return [_rewrite_references(item, source, contract_root, by_path, by_id) for item in value]
    if not isinstance(value, dict):
        return value
    rewritten = {
        key: _rewrite_references(item, source, contract_root, by_path, by_id)
        for key, item in value.items()
        if key != "$ref"
    }
    reference = value.get("$ref")
    if isinstance(reference, str):
        rewritten["$ref"] = _canonical_reference(
            reference,
            source,
            contract_root,
            by_path,
            by_id,
        )
    return rewritten


def _canonical_reference(
    reference: str,
    source: _Source,
    contract_root: Path,
    by_path: Mapping[Path, _Source],
    by_id: Mapping[str, _Source],
) -> str:
    target, fragment = urldefrag(reference)
    if not target:
        return reference
    if target in by_id:
        resolved = by_id[target]
    else:
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            raise ValueError(f"network schema reference is forbidden: {reference}")
        candidate = (source.absolute.parent / unquote(parsed.path)).resolve()
        if not candidate.is_relative_to(contract_root):
            raise ValueError(f"schema reference escapes contracts: {reference}")
        local_source = by_path.get(candidate)
        if local_source is None:
            raise ValueError(f"local schema reference is unavailable: {reference}")
        resolved = local_source
    return resolved.schema_id + (f"#{fragment}" if fragment else "")


def _render_init(contract_digest: str) -> str:
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
"""

from ctower_contracts.catalog import (
    CATALOG,
    ContractCatalog,
    schema_for,
    validator_for,
)

__all__ = ["CATALOG", "ContractCatalog", "schema_for", "validator_for"]
'''


def _render_catalog(contract_digest: str) -> str:
    return f'''"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:{contract_digest}
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
'''
