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
_BYTE_ORDER_MARK = "\ufeff"
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


def _reject_duplicate_json_names(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object name: {key}")
        result[key] = value
    return result


_JSON = json.JSONDecoder(object_pairs_hook=_reject_duplicate_json_names)


def catalog_admission_findings(root: Path) -> tuple[Finding, ...]:
    """Refuse explicit tenant-content markers in the public repository tree."""

    findings: list[Finding] = []
    for path in _files(root):
        findings.extend(_path_findings(path, root))
    return tuple(findings)


def _path_findings(path: Path, root: Path) -> tuple[Finding, ...]:
    relative = path.relative_to(root).as_posix()
    text = _read_text(path)
    if text is None:
        if _is_catalog_artifact(path, root):
            return (_finding(relative, "catalog artifact could not be decoded"),)
        return ()
    composed, documents = _documents(path, text)
    if not composed:
        return (_finding(relative, "structured stream could not be classified"),)
    if any(_contains_tenant_marker(document) for document in documents):
        return (_finding(relative, "explicit tenant catalog content marker"),)
    return ()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _documents(path: Path, text: str) -> tuple[bool, tuple[object, ...]]:
    """Compose every structured document a file carries, wherever that class occurs.

    Composition takes whole streams, not one document each: a byte-order mark,
    several YAML documents, and several concatenated JSON values all compose,
    and every composed document is judged by the one classifier. A stream that
    composes to no document carries no class. A stream that does not compose at
    all offers no document to judge, so its caller refuses it rather than asking
    how the bytes are spelled. Files carrying no structured document compose
    empty.
    """

    suffix = path.suffix.lower()
    if suffix == ".json":
        return _compose_json(text)
    if suffix in {".yaml", ".yml"}:
        return _compose_yaml(text)
    has_frontmatter, frontmatter = _yaml_frontmatter(text)
    if not has_frontmatter:
        return True, ()
    if frontmatter is None:
        return False, ()
    return _compose_yaml(frontmatter)


def _compose_json(text: str) -> tuple[bool, tuple[object, ...]]:
    stream = text.removeprefix(_BYTE_ORDER_MARK)
    documents: list[object] = []
    index = _next_document(stream, 0)
    while index < len(stream):
        try:
            document, index = _JSON.raw_decode(stream, index)
        except ValueError:
            return False, ()
        documents.append(document)
        index = _next_document(stream, index)
    return True, tuple(documents)


def _next_document(stream: str, index: int) -> int:
    while index < len(stream) and stream[index].isspace():
        index += 1
    return index


def _compose_yaml(text: str) -> tuple[bool, tuple[object, ...]]:
    try:
        return True, tuple(_YAML.load_all(text))
    except (ValueError, YAMLError):
        return False, ()


def _yaml_frontmatter(text: str) -> tuple[bool, str | None]:
    lines = text.removeprefix(_BYTE_ORDER_MARK).splitlines(keepends=True)
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
