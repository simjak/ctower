"""Knowledge-source Seam and its local static-file Adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: tuple[str, ...] = (
    "KnowledgeSource",
    "KnowledgeSourceDocument",
    "KnowledgeSourceUnavailableError",
    "StaticFileKnowledgeSource",
    "bundled_static_root",
)

_VALID_SCOPES = frozenset({"org", "project"})
_REF = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_MAX_FILE_BYTES = 1_050_000
_MAX_TITLE_LENGTH = 1024
_MAX_BODY_LENGTH = 1_048_576


class KnowledgeSourceUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeSourceDocument:
    """One strict source record resolved before it becomes an immutable fact."""

    scope: str
    ref: str
    title: str
    body: str

    def __post_init__(self) -> None:
        if self.scope not in _VALID_SCOPES:
            raise ValueError("knowledge source scope must be org or project")
        if _REF.fullmatch(self.ref) is None:
            raise ValueError("knowledge source ref is outside the authored contract")
        if not 1 <= len(self.title) <= _MAX_TITLE_LENGTH:
            raise ValueError("knowledge source title is outside the authored contract")
        if not 1 <= len(self.body) <= _MAX_BODY_LENGTH:
            raise ValueError("knowledge source body is outside the authored contract")

    def to_mapping(self) -> dict[str, object]:
        return {"body": self.body, "ref": self.ref, "scope": self.scope, "title": self.title}


class KnowledgeSource(Protocol):
    """Read static knowledge content by scope and stable source reference."""

    def list(self, *, scope: str) -> tuple[KnowledgeSourceDocument, ...]: ...

    def get(self, *, scope: str, ref: str) -> KnowledgeSourceDocument | None: ...


class StaticFileKnowledgeSource:
    """Read strict Markdown snapshots from ``root/<scope>/<ref>.md``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def list(self, *, scope: str) -> tuple[KnowledgeSourceDocument, ...]:
        scope_dir = self._scope_directory(scope)
        return tuple(
            self._read_file(scope=scope, ref=path.stem, path=path, scope_dir=scope_dir)
            for path in sorted(scope_dir.glob("*.md"), key=lambda item: item.name)
            if not path.is_symlink()
        )

    def get(self, *, scope: str, ref: str) -> KnowledgeSourceDocument | None:
        if _REF.fullmatch(ref) is None:
            return None
        scope_dir = self._scope_directory(scope)
        path = scope_dir / f"{ref}.md"
        if path.is_symlink() or not path.is_file():
            return None
        return self._read_file(scope=scope, ref=ref, path=path, scope_dir=scope_dir)

    def _scope_directory(self, scope: str) -> Path:
        if scope not in _VALID_SCOPES:
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} is not available")
        scope_dir = self._root / scope
        if not scope_dir.is_dir() or scope_dir.is_symlink():
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} is not an available directory")
        return scope_dir

    def _read_file(
        self, *, scope: str, ref: str, path: Path, scope_dir: Path
    ) -> KnowledgeSourceDocument:
        _validate_file(path, scope_dir)
        title, body = _read_markdown(path)
        try:
            return KnowledgeSourceDocument(scope=scope, ref=ref, title=title, body=body)
        except ValueError as exc:
            raise KnowledgeSourceUnavailableError(
                "knowledge file violates the authored contract"
            ) from exc


def _validate_file(path: Path, scope_dir: Path) -> None:
    """Require one bounded regular file directly below the configured scope."""

    try:
        resolved_scope = scope_dir.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        byte_count = path.stat().st_size
    except OSError as exc:
        raise KnowledgeSourceUnavailableError("knowledge file could not be read") from exc
    if resolved_path.parent != resolved_scope or path.is_symlink():
        raise KnowledgeSourceUnavailableError("knowledge file escapes its configured scope")
    if byte_count > _MAX_FILE_BYTES:
        raise KnowledgeSourceUnavailableError("knowledge file exceeds the authored byte bound")


def _read_markdown(path: Path) -> tuple[str, str]:
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise KnowledgeSourceUnavailableError("knowledge file could not be read") from exc
    lines = text.splitlines()
    heading_index = next((index for index, line in enumerate(lines) if line.startswith("# ")), None)
    if heading_index is None:
        raise KnowledgeSourceUnavailableError("knowledge file has no level-one heading")
    return lines[heading_index][2:].strip(), "\n".join(lines[heading_index + 1 :]).strip()


def bundled_static_root() -> Path:
    """Return the wheel-owned static source mounted by the development API."""

    return Path(__file__).with_name("static")
