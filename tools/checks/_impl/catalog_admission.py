"""AC-CAT-01 admission checks for public repository content."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.tokens import DocumentEndToken, DocumentStartToken

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
        return _unclassified(relative, must_classify=is_catalog_artifact)
    parsed, value = _document(path, text)
    if not parsed:
        return _unclassified(relative, must_classify=is_catalog_artifact or _FIELD in text)
    if _contains_tenant_marker(value):
        return (_finding(relative, "explicit tenant catalog content marker"),)
    return ()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _document(path: Path, text: str) -> tuple[bool, object | None]:
    """Parse the structured document a file carries, wherever that class occurs.

    The parser decodes escaped names and values, so admission judges the decoded
    content class. Files carrying no structured document parse as empty.
    """

    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_json(text)
    if suffix in {".yaml", ".yml"}:
        return _parse_yaml(text)
    has_frontmatter, frontmatter = _yaml_frontmatter(text)
    if not has_frontmatter:
        return True, None
    if frontmatter is None:
        return False, None
    return _parse_yaml(frontmatter)


def _unclassified(relative: str, *, must_classify: bool) -> tuple[Finding, ...]:
    """Fail closed where a document owes a class but cannot supply one.

    Classification is owed by the catalog artifact registry, and by any
    unparsable document whose bytes already show the semantic field. Neither
    condition can route a parsed document around admission; both only widen
    refusal where no parse exists to judge.
    """

    if not must_classify:
        return ()
    return (_finding(relative, "catalog artifact could not be classified"),)


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
    body = "".join(lines[1:])
    try:
        for token in _YAML.scan(body):
            if isinstance(token, (DocumentStartToken, DocumentEndToken)):
                return True, body[: token.start_mark.index]
    except YAMLError:
        return True, None
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
