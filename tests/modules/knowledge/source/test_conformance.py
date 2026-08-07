"""Conformance suite for the knowledge-source adapter seam.

Any KnowledgeSource implementation must satisfy run_conformance_suite.
Two concrete implementations are exercised here: the local
StaticFileKnowledgeSource and a trivial in-memory fake, proving the seam
is implementation-agnostic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctower_kernel.knowledge.source import (
    KnowledgeSource,
    KnowledgeSourceDocument,
    KnowledgeSourceUnavailableError,
    StaticFileKnowledgeSource,
)

__all__: tuple[str, ...] = ("run_conformance_suite",)


_UNSERVED_SCOPE = "nope"


def run_conformance_suite(source: KnowledgeSource) -> None:
    """Assert the full knowledge-source contract against any implementation."""
    documents = source.list(scope="org")

    # Documents come back sorted by ref, all in the requested scope.
    refs = [item.ref for item in documents]
    assert refs == sorted(refs)
    assert len(documents) > 0

    # Every document carries the requested scope and a non-empty ref/title/body.
    for item in documents:
        assert item.scope == "org"
        assert item.ref
        assert item.title
        assert item.body

    # get returns exactly the listed document for the same scope+ref.
    for item in documents:
        assert source.get(scope="org", ref=item.ref) == item

    # An unknown ref yields None, never an exception.
    assert source.get(scope="org", ref="does-not-exist") is None

    # An unserved scope raises — never silently returns empty.
    with pytest.raises(KnowledgeSourceUnavailableError):
        source.list(scope=_UNSERVED_SCOPE)
    with pytest.raises(KnowledgeSourceUnavailableError):
        source.get(scope=_UNSERVED_SCOPE, ref="anything")

    # Path-traversal refs are refused.
    assert source.get(scope="org", ref="../escape") is None
    assert source.get(scope="org", ref="a/b") is None


def _write_markdown(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


def test_static_file_source_passes_conformance(tmp_path: Path) -> None:
    org = tmp_path / "org"
    org.mkdir()
    _write_markdown(org, "zeta.md", "# Zeta document\n\nBody of zeta.\n")
    _write_markdown(org, "alpha.md", "# Alpha document\n\nBody of alpha.\n")

    run_conformance_suite(StaticFileKnowledgeSource(tmp_path))


def test_static_file_source_raises_on_missing_heading(tmp_path: Path) -> None:
    org = tmp_path / "org"
    org.mkdir()
    _write_markdown(org, "valid.md", "# Valid document\n\nValid body.\n")
    _write_markdown(org, "naked.md", "This file has no heading at all.\n")

    source = StaticFileKnowledgeSource(tmp_path)
    with pytest.raises(KnowledgeSourceUnavailableError):
        source.list(scope="org")
    with pytest.raises(KnowledgeSourceUnavailableError):
        source.get(scope="org", ref="naked")


class _InMemoryKnowledgeSource:
    """Trivial in-memory fake implementing the KnowledgeSource contract."""

    def __init__(self, documents: dict[tuple[str, str], KnowledgeSourceDocument]) -> None:
        self._documents = documents

    def list(self, *, scope: str) -> tuple[KnowledgeSourceDocument, ...]:
        if scope not in {"org", "project"}:
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} unserved")
        matching = [doc for doc in self._documents.values() if doc.scope == scope]
        return tuple(sorted(matching, key=lambda doc: doc.ref))

    def get(self, *, scope: str, ref: str) -> KnowledgeSourceDocument | None:
        if scope not in {"org", "project"}:
            raise KnowledgeSourceUnavailableError(f"scope {scope!r} unserved")
        if "/" in ref or "\\" in ref or ".." in ref:
            return None
        return self._documents.get((scope, ref))


def test_in_memory_fake_source_passes_conformance() -> None:
    source = _InMemoryKnowledgeSource(
        {
            ("org", "zeta"): KnowledgeSourceDocument(
                scope="org", ref="zeta", title="Zeta", body="Body of zeta."
            ),
            ("org", "alpha"): KnowledgeSourceDocument(
                scope="org", ref="alpha", title="Alpha", body="Body of alpha."
            ),
        }
    )
    run_conformance_suite(source)
