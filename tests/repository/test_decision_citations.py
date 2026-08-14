"""Every decision citation must resolve to a real rendered target.

A citation that points nowhere is worse than a missing one: it reads as provenance,
survives merge, and is invisible to everyone who trusts it. `D58` shipped a repair for
exactly this class after a review caught it attributing a rule to a decision that never
contained one (2026-08-11).

One hash-locked CommonMark parser supplies the only structural oracle. Declarations
come from its heading and inline-HTML tokens, and citations come from its rendered-text
tokens. Code tokens are excluded; source lines are never scanned for Markdown structure.

What this gate proves and what it cannot: it proves every cited `D<n>` and `AC-FAM-nn`
identifier RESOLVES to a rendered decision heading or acceptance anchor. It cannot prove
that the cited target actually SAYS what the citing sentence claims. Content support is
the reviewer's half of this control under review-checklist v2.7 item 10.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "docs/internal/DECISIONS.md"
SPEC = ROOT / "docs/internal/SPEC.md"

_DECISION_ID = re.compile(r"^(D\d+)(?!\w)")
_DECISION_REFERENCE = re.compile(r"\b(D\d+)\b")
_ACCEPTANCE_ID = re.compile(r"^ac-[a-z]+-\d+$")
_ACCEPTANCE_REFERENCE = re.compile(r"\b(AC-[A-Z]+-\d+)\b")
_RENDERED_TEXT_TOKEN_TYPES = frozenset({"text", "text_special"})
_MARKDOWN = MarkdownIt("commonmark")


@dataclass(frozen=True, slots=True)
class _MarkdownFacts:
    declared_decisions: frozenset[str]
    declared_acceptance_criteria: frozenset[str]
    cited_decisions: frozenset[str]
    cited_acceptance_criteria: frozenset[str]


class _InlineAnchorParser(HTMLParser):
    """Collect acceptance ids from one parser-classified inline HTML token."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        anchor_id = dict(attrs).get("id")
        if anchor_id is not None and _ACCEPTANCE_ID.fullmatch(anchor_id):
            self.ids.add(anchor_id.upper())


def _inline_text(token: Token) -> str:
    """Return rendered non-code text for one inline token."""
    parts: list[str] = []
    for child in token.children or []:
        if child.type in _RENDERED_TEXT_TOKEN_TYPES:
            parts.append(child.content)
        elif child.type in {"code_inline", "softbreak", "hardbreak"}:
            parts.append(" ")
    return "".join(parts)


def _inline_anchor_ids(token: Token) -> set[str]:
    declared: set[str] = set()
    for child in token.children or []:
        if child.type != "html_inline":
            continue
        parser = _InlineAnchorParser()
        parser.feed(child.content)
        declared.update(parser.ids)
    return declared


def _facts(source: str) -> _MarkdownFacts:
    tokens = _MARKDOWN.parse(source)
    declared_decisions: set[str] = set()
    declared_acceptance_criteria: set[str] = set()
    rendered_text: list[str] = []

    for index, token in enumerate(tokens):
        if token.type != "inline":
            continue
        text = _inline_text(token)
        rendered_text.append(text)
        declared_acceptance_criteria.update(_inline_anchor_ids(token))
        if index and tokens[index - 1].type == "heading_open":
            match = _DECISION_ID.match(text.strip())
            if match is not None:
                declared_decisions.add(match.group(1))

    citation_text = "\n".join(rendered_text)
    return _MarkdownFacts(
        declared_decisions=frozenset(declared_decisions),
        declared_acceptance_criteria=frozenset(declared_acceptance_criteria),
        cited_decisions=frozenset(_DECISION_REFERENCE.findall(citation_text)),
        cited_acceptance_criteria=frozenset(_ACCEPTANCE_REFERENCE.findall(citation_text)),
    )


class DecisionCitationsResolveTests(unittest.TestCase):
    def test_every_cited_decision_is_declared(self) -> None:
        decisions = _facts(DECISIONS.read_text(encoding="utf-8"))
        self.assertTrue(
            decisions.declared_decisions, "docs/internal/DECISIONS.md declares no decisions"
        )
        for source in (DECISIONS, SPEC):
            cited = _facts(source.read_text(encoding="utf-8")).cited_decisions
            dangling = sorted(
                cited - decisions.declared_decisions,
                key=lambda name: int(name[1:]),
            )
            self.assertEqual(
                [],
                dangling,
                f"{source.name} cites decisions that do not exist: {dangling}",
            )

    def test_every_cited_acceptance_criterion_is_anchored(self) -> None:
        facts = _facts(SPEC.read_text(encoding="utf-8"))
        self.assertTrue(
            facts.declared_acceptance_criteria,
            "docs/internal/SPEC.md anchors no acceptance criteria",
        )
        dangling = sorted(facts.cited_acceptance_criteria - facts.declared_acceptance_criteria)
        self.assertEqual(
            [],
            dangling,
            f"docs/internal/SPEC.md cites acceptance criteria that are not anchored: {dangling}",
        )


class CommonMarkTokenStreamRegressionTests(unittest.TestCase):
    """GitHub/CommonMark truth for every construction found across three reviews."""

    def test_a_fenced_heading_is_code_not_a_declaration(self) -> None:
        facts = _facts("## D1 real\n\n```\n## D901 hidden\n```\n\nPer D901.\n")
        self.assertNotIn("D901", facts.declared_decisions)
        self.assertIn("D901", facts.cited_decisions)

    def test_a_longer_closing_fence_is_code_not_a_declaration(self) -> None:
        facts = _facts("## D1 real\n\n```\n## D902 hidden\n````\n\nPer D902.\n")
        self.assertNotIn("D902", facts.declared_decisions)
        self.assertIn("D902", facts.cited_decisions)

    def test_an_html_comment_declares_nothing(self) -> None:
        source = "## D1 real\n\n<!--\n## D903 hidden\n-->\n\nPer D903.\n"
        facts = _facts(source)
        self.assertNotIn("D903", facts.declared_decisions)
        self.assertIn("D903", facts.cited_decisions)

    def test_an_inline_code_anchor_declares_nothing(self) -> None:
        source = '`<a id="ac-phantom-01"></a>` then AC-PHANTOM-01.\n'
        facts = _facts(source)
        self.assertNotIn("AC-PHANTOM-01", facts.declared_acceptance_criteria)
        self.assertIn("AC-PHANTOM-01", facts.cited_acceptance_criteria)

    def test_an_indented_code_block_anchor_declares_nothing(self) -> None:
        source = 'text\n\n    <a id="ac-phantom-02"></a>\n\nAC-PHANTOM-02.\n'
        facts = _facts(source)
        self.assertNotIn("AC-PHANTOM-02", facts.declared_acceptance_criteria)
        self.assertIn("AC-PHANTOM-02", facts.cited_acceptance_criteria)

    def test_a_three_space_indented_fence_is_code_not_a_declaration(self) -> None:
        source = "## D1 real\n\n   ```text\n## D904 hidden\n   ```\n\nPer D904.\n"
        facts = _facts(source)
        self.assertNotIn("D904", facts.declared_decisions)
        self.assertIn("D904", facts.cited_decisions)

    def test_a_blockquote_nested_fence_is_code_not_a_declaration(self) -> None:
        source = "## D1 real\n\n> ```text\n> ## D905 hidden\n> ```\n\nPer D905.\n"
        facts = _facts(source)
        self.assertNotIn("D905", facts.declared_decisions)
        self.assertIn("D905", facts.cited_decisions)

    def test_a_longer_identifier_does_not_declare_its_prefix(self) -> None:
        facts = _facts("## D900X not an exact decision heading\n\nPer D900.\n")
        self.assertNotIn("D900", facts.declared_decisions)
        self.assertIn("D900", facts.cited_decisions)

    def test_fabricated_ids_in_heading_text_are_citations(self) -> None:
        source = (
            '## D1 — supersedes D999\n\n<a id="ac-real-01"></a> AC-REAL-01\n\n'
            "## Requirement AC-PHANTOM-01\n"
        )
        facts = _facts(source)
        self.assertEqual({"D999"}, facts.cited_decisions - facts.declared_decisions)
        self.assertEqual(
            {"AC-PHANTOM-01"},
            facts.cited_acceptance_criteria - facts.declared_acceptance_criteria,
        )

    def test_fabricated_ids_in_prose_are_citations(self) -> None:
        source = '## D1 real\n\n<a id="ac-real-01"></a> AC-REAL-01\n\nPer D999 and AC-PHANTOM-01.\n'
        facts = _facts(source)
        self.assertEqual({"D999"}, facts.cited_decisions - facts.declared_decisions)
        self.assertEqual(
            {"AC-PHANTOM-01"},
            facts.cited_acceptance_criteria - facts.declared_acceptance_criteria,
        )


if __name__ == "__main__":
    unittest.main()
