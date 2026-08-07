"""Knowledge-source adapter SEAM: a pluggable external-source interface plus one \
local static-file implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: tuple[str, ...] = (
    "KnowledgeDocument",
    "KnowledgeSource",
    "KnowledgeSourceUnavailableError",
    "StaticFileKnowledgeSource",
)

_VALID_SCOPES = frozenset({"org", "project"})


class KnowledgeSourceUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """A single knowledge record with an org/project scope and a stable ref."""

    scope: str
    ref: str
    title: str
    body: str

    def __post_init__(self) -> None:
        if self.scope not in _VALID_SCOPES:
            raise ValueError(f"scope must be one of {sorted(_VALID_SCOPES)}, got {self.scope!r}")

    def to_mapping(self) -> dict[str, object]:
        """Serialize this document to a plain, JSON-friendly mapping."""
        return {
            "scope": self.scope,
            "ref": self.ref,
            "title": self.title,
            "body": self.body,
        }


class KnowledgeSource(Protocol):
    """Pluggable knowledge source: list documents by scope and fetch one by ref.

    Implementations must raise KnowledgeSourceUnavailableError when the requested
    scope cannot be served, and must refuse path-traversal refs by returning
    None. See the conformance suite for the full contract.
    """

    def list(self, *, scope: str) -> tuple[KnowledgeDocument, ...]: ...

    def get(self, *, scope: str, ref: str) -> KnowledgeDocument | None: ...


class StaticFileKnowledgeSource:
    """KnowledgeSource backed by markdown files under ``root/<scope>/*.md``.

    Each file's ``# `` heading becomes the document title; the remaining file
    content becomes the body. The file stem is the document ref.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def list(self, *, scope: str) -> tuple[KnowledgeDocument, ...]:
        if scope not in _VALID_SCOPES:
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} is not available")
        scope_dir = self._root / scope
        if not scope_dir.is_dir():
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} is not an available directory")
        return tuple(
            self._read_file(scope=scope, ref=path.stem, path=path)
            for path in sorted(scope_dir.glob("*.md"), key=lambda item: item.name)
        )

    def get(self, *, scope: str, ref: str) -> KnowledgeDocument | None:
        if "/" in ref or "\\" in ref or ".." in ref:
            return None
        if scope not in _VALID_SCOPES:
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} is not available")
        scope_dir = self._root / scope
        if not scope_dir.is_dir():
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} is not an available directory")
        path = scope_dir / f"{ref}.md"
        if not path.is_file():
            return None
        return self._read_file(scope=scope, ref=ref, path=path)

    def _read_file(self, *, scope: str, ref: str, path: Path) -> KnowledgeDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            message = f"could not read knowledge file {path}: {exc}"
            raise KnowledgeSourceUnavailableError(message) from exc
        lines = text.splitlines()
        heading_index = next(
            (index for index, line in enumerate(lines) if line.startswith("# ")),
            None,
        )
        if heading_index is None:
            raise KnowledgeSourceUnavailableError(f"knowledge file {path} has no '# ' heading")
        title = lines[heading_index][2:].strip()
        body = "\n".join(lines[heading_index + 1 :]).strip()
        return KnowledgeDocument(scope=scope, ref=ref, title=title, body=body)
