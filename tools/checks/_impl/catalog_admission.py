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
    parsed, value, should_refuse = _parse(path, text, is_catalog_artifact=is_catalog_artifact)
    if not parsed:
        if should_refuse:
            return (_finding(relative, "catalog artifact could not be classified"),)
        return ()
    if should_refuse and _contains_tenant_marker(value):
        return (_finding(relative, "explicit tenant catalog content marker"),)
    return ()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _parse(path: Path, text: str, *, is_catalog_artifact: bool) -> tuple[bool, object | None, bool]:
    suffix = path.suffix.lower()
    should_refuse = is_catalog_artifact or _FIELD in text
    if suffix == ".json":
        parsed, value = _parse_json(text)
        return parsed, value, should_refuse
    if suffix in {".yaml", ".yml"}:
        parsed, value = _parse_yaml(text)
        return parsed, value, should_refuse
    if not is_catalog_artifact:
        return True, None, False
    has_frontmatter, frontmatter = _yaml_frontmatter(text)
    if not has_frontmatter:
        return True, None, False
    if frontmatter is None:
        return False, None, True
    parsed, value = _parse_yaml(frontmatter)
    return parsed, value, True


def _parse_json(text: str) -> tuple[bool, object | None]:
    try:
        return True, json.loads(text, object_pairs_hook=_reject_duplicate_json_names)
    except ValueError:
        return False, None


def _parse_yaml(text: str) -> tuple[bool, object | None]:
    try:
        return True, _YAML.load(text)
    except (ValueError, YAMLError):
        return False, None


def _reject_duplicate_json_names(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object name: {key}")
        result[key] = value
    return result


def _yaml_frontmatter(text: str) -> tuple[bool, str | None]:
    lines = text.removeprefix("\ufeff").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return False, None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            return True, "".join(lines[1:index])
    return True, None


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
