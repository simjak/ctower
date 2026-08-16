"""AC-CAT-01 admission checks for public repository content."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from tools.checks.report import Finding, Severity

__all__ = ["catalog_admission_findings"]

TENANT_CONTENT_REFUSAL = "tenant-catalog-content-in-public-repository"
_FIELD = "catalog_content"
_TENANT_VALUE = "tenant"
_SUPPORTED_SUFFIXES = frozenset({".json", ".yaml", ".yml"})
_CATALOG_DIRECTORIES = frozenset({"examples", "packs"})
_YAML = YAML(typ="safe")
_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "site",
    }
)


def catalog_admission_findings(root: Path) -> tuple[Finding, ...]:
    """Refuse explicit tenant-content markers in the public repository tree."""

    findings: list[Finding] = []
    for path in _files(root):
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        findings.extend(_path_findings(path, root))
    return tuple(findings)


def _path_findings(path: Path, root: Path) -> tuple[Finding, ...]:
    relative = path.relative_to(root).as_posix()
    is_catalog_artifact = _is_catalog_artifact(path, root)
    text = _read_text(path)
    if text is None:
        return (
            (_finding(relative, "catalog artifact could not be classified"),)
            if is_catalog_artifact
            else ()
        )
    parsed, value = _parse(path, text)
    if not parsed:
        if is_catalog_artifact or _FIELD in text:
            return (_finding(relative, "catalog artifact could not be classified"),)
        return ()
    if _contains_tenant_marker(value):
        return (_finding(relative, "explicit tenant catalog content marker"),)
    return ()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _parse(path: Path, text: str) -> tuple[bool, object | None]:
    try:
        if path.suffix.lower() == ".json":
            return True, json.loads(text)
        return True, _YAML.load(text)
    except (ValueError, YAMLError):
        return False, None


def _contains_tenant_marker(value: object) -> bool:
    if isinstance(value, Mapping):
        if value.get(_FIELD) == _TENANT_VALUE:
            return True
        return any(_contains_tenant_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_tenant_marker(item) for item in value)
    return False


def _is_catalog_artifact(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return bool(relative.parts) and relative.parts[0] in _CATALOG_DIRECTORIES


def _finding(relative: str, detail: str) -> Finding:
    return Finding(
        TENANT_CONTENT_REFUSAL,
        relative,
        f"{TENANT_CONTENT_REFUSAL}: {detail}",
        Severity.ERROR,
        observed=1,
        limit=0,
    )


def _files(root: Path) -> Iterator[Path]:
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        names[:] = sorted(name for name in names if name not in _EXCLUDED_DIRECTORIES)
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.is_file():
                yield path
