"""Mint-time uniqueness for the identifiers the authored registries hand out."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from re import Pattern

from markdown_it import MarkdownIt

from tools.checks.report import Finding, Severity

__all__ = ["minted_identity_findings"]

STABLE_ID_REFUSAL = "mint.duplicate-stable-id"
DECISION_REFUSAL = "mint.duplicate-decision"
MIGRATION_REFUSAL = "mint.duplicate-migration"

_SPEC = "docs/internal/SPEC.md"
_DECISIONS = "docs/internal/DECISIONS.md"
_MIGRATIONS = "packages/ctower-kernel/migrations"

# A backlog row mints its stable ID in the first cell only. Every later cell cites an
# identifier some other row minted — the dependency column above all, which is why
# `CT-I1-009` through `CT-I1-013` are each written twice in the shipped table.
_MINTED_STABLE_ID = re.compile(r"^\|\s*(CT-[A-Z0-9]+-[0-9]+)\s*\|")
_MINTED_DECISION = re.compile(r"^#{1,6}\s+(D[0-9]+)(?![0-9A-Za-z])")
_MINTED_MIGRATION = re.compile(r"^([0-9]{4})_.+\.sql$")

_QUOTED_BLOCKS = frozenset({"code_block", "fence", "html_block"})
_MARKDOWN = MarkdownIt("commonmark")


def minted_identity_findings(root: Path) -> tuple[Finding, ...]:
    """Refuse the second mint of any stable ID, decision number, or migration number."""

    return (
        *_document_findings(root, _SPEC, _MINTED_STABLE_ID, STABLE_ID_REFUSAL, "stable ID"),
        *_document_findings(root, _DECISIONS, _MINTED_DECISION, DECISION_REFUSAL, "decision"),
        *_migration_findings(root),
    )


def _document_findings(
    root: Path, relative: str, minted: Pattern[str], rule_id: str, subject: str
) -> tuple[Finding, ...]:
    """Refuse every line of one registry that re-mints an identifier an earlier line took."""

    path = root / relative
    if not path.is_file():
        return ()
    first_mint: dict[str, int] = {}
    findings: list[Finding] = []
    for number, line in _quotation_free_lines(path.read_text(encoding="utf-8")):
        match = minted.match(line)
        if match is None:
            continue
        identifier = match.group(1)
        minted_at = first_mint.setdefault(identifier, number)
        if minted_at != number:
            findings.append(
                _finding(
                    rule_id,
                    relative,
                    f"{subject} {identifier} was already minted at line {minted_at}",
                    line=number,
                )
            )
    return tuple(findings)


def _quotation_free_lines(text: str) -> Iterator[tuple[int, str]]:
    """Number every line CommonMark renders as prose; quoted blocks declare nothing.

    A fenced example, an indented code block, and an HTML comment all spell an identifier
    exactly the way a real heading or backlog row does, so the parser — not the bytes —
    decides which lines can mint.
    """

    quoted = _quoted_lines(text)
    for index, line in enumerate(text.splitlines()):
        if index not in quoted:
            yield index + 1, line


def _quoted_lines(text: str) -> frozenset[int]:
    return frozenset(
        index
        for token in _MARKDOWN.parse(text)
        if token.type in _QUOTED_BLOCKS and token.map is not None
        for index in range(token.map[0], token.map[1])
    )


def _migration_findings(root: Path) -> tuple[Finding, ...]:
    """Refuse every migration whose four-digit number an earlier filename already took."""

    directory = root / _MIGRATIONS
    if not directory.is_dir():
        return ()
    first_mint: dict[str, str] = {}
    findings: list[Finding] = []
    for path in sorted(directory.iterdir()):
        match = _MINTED_MIGRATION.match(path.name)
        if match is None:
            continue
        minted_by = first_mint.setdefault(match.group(1), path.name)
        if minted_by != path.name:
            findings.append(
                _finding(
                    MIGRATION_REFUSAL,
                    f"{_MIGRATIONS}/{path.name}",
                    f"migration number {match.group(1)} was already minted by {minted_by}",
                )
            )
    return tuple(findings)


def _finding(rule_id: str, relative: str, message: str, line: int | None = None) -> Finding:
    return Finding(rule_id, relative, message, Severity.ERROR, line=line, observed=1, limit=0)
