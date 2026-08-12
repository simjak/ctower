"""Every decision citation must resolve to a real rendered target.

A citation that points nowhere is worse than a missing one: it reads as provenance,
survives merge, and is invisible to everyone who trusts it. `D58` shipped a repair for
exactly this class after a review caught it attributing a rule to a decision that never
contained one (2026-08-11).

Targets are extracted from the RENDERED document, not source bytes: the review of this
gate proved four source-scanning false greens (a fence closed by a longer delimiter, an
HTML comment, inline code, and an indented code block can all carry declaration-shaped
text that GitHub renders as code or nothing). One real CommonMark/GFM-family renderer
(the hash-locked `markdown` package) decides what is a heading, an anchor, or prose;
this module never re-implements that judgment with regexes over source.

What this gate proves and what it cannot: it proves every cited `D<n>` and `AC-FAM-nn`
identifier RESOLVES to a rendered decision heading or acceptance anchor. It cannot prove
that the cited target actually SAYS what the citing sentence claims — that half is a
reviewer obligation carried by the review checklist, not a mechanical one.
"""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "DECISIONS.md"
SPEC = ROOT / "SPEC.md"

_DECISION_ID = re.compile(r"^(D\d+)(?!\w)")
_DECISION_REFERENCE = re.compile(r"\b(D\d+)\b")
_ACCEPTANCE_REFERENCE = re.compile(r"\b(AC-[A-Z]+-\d+)\b")


class _RenderedTargets(HTMLParser):
    """Collects rendered h2 headings, anchor ids, and prose text (code excluded)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[str] = []
        self.anchor_ids: list[str] = []
        self.prose: list[str] = []
        self._in_h2 = False
        self._h2_text: list[str] = []
        self._code_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"code", "pre"}:
            self._code_depth += 1
        elif tag == "h2":
            self._in_h2 = True
            self._h2_text = []
        elif tag == "a":
            anchor_id = dict(attrs).get("id")
            if anchor_id:
                self.anchor_ids.append(anchor_id)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"code", "pre"} and self._code_depth:
            self._code_depth -= 1
        elif tag == "h2":
            self._in_h2 = False
            self.headings.append("".join(self._h2_text).strip())

    def handle_data(self, data: str) -> None:
        if self._code_depth:
            return
        if self._in_h2:
            self._h2_text.append(data)
        else:
            self.prose.append(data)


def _render(source: str) -> _RenderedTargets:
    # fenced_code is required for GFM-style backtick fences — without it a fenced
    # "## D901" renders as a real heading and the first false-green class returns.
    _refuse_ambiguous_fences(source)
    html = markdown.markdown(source, extensions=["fenced_code"])
    parser = _RenderedTargets()
    parser.feed(html)
    return parser


_FENCE_LINE = re.compile(r"^(`{3,}|~{3,})\s*\S*\s*$")


class AmbiguousFenceError(AssertionError):
    """A fence construct on which CommonMark/GFM and the locked renderer disagree."""


def _refuse_ambiguous_fences(source: str) -> None:
    """Fail closed where renderers disagree instead of guessing.

    CommonMark/GFM closes a fence with any delimiter AT LEAST as long as its opener;
    the locked `markdown` package requires an exact match and otherwise renders the
    block's contents (the review-proven D902 false green). Rather than re-implement
    CommonMark or add a dependency, the gate REFUSES a canonical document containing
    an opener whose closer is longer (or that never closes): where the oracles
    disagree, the document is the thing that must change — normalize the fence."""
    open_len: int | None = None
    open_line = 0
    for number, line in enumerate(source.splitlines(), start=1):
        match = _FENCE_LINE.match(line)
        if not match:
            continue
        length = len(match.group(1))
        if open_len is None:
            open_len, open_line = length, number
        elif length == open_len:
            open_len = None
        elif length > open_len:
            raise AmbiguousFenceError(
                f"ambiguous fence: opener of length {open_len} at line {open_line} "
                f"closed by length {length} at line {number} — renderers disagree; "
                "normalize the fence to equal delimiters"
            )
    if open_len is not None:
        raise AmbiguousFenceError(
            f"unclosed fence opened at line {open_line} — renderers disagree on the "
            "rest of the document; close the fence"
        )


def _declared_decisions(source: str) -> set[str]:
    rendered = _render(source)
    declared: set[str] = set()
    for heading in rendered.headings:
        match = _DECISION_ID.match(heading)
        if match:
            declared.add(match.group(1))
    return declared


def _declared_acceptance_criteria(source: str) -> set[str]:
    return {anchor.upper() for anchor in _render(source).anchor_ids}


def _cited(source: str, pattern: re.Pattern[str]) -> set[str]:
    return set(pattern.findall(" ".join(_render(source).prose)))


class DecisionCitationsResolveTests(unittest.TestCase):
    def test_every_cited_decision_is_declared(self) -> None:
        declared = _declared_decisions(DECISIONS.read_text(encoding="utf-8"))
        self.assertTrue(declared, "DECISIONS.md declares no decisions")
        for source in (DECISIONS, SPEC):
            cited = _cited(source.read_text(encoding="utf-8"), _DECISION_REFERENCE)
            dangling = sorted(cited - declared, key=lambda name: int(name[1:]))
            self.assertEqual(
                [],
                dangling,
                f"{source.name} cites decisions that do not exist: {dangling}",
            )

    def test_every_cited_acceptance_criterion_is_anchored(self) -> None:
        spec = SPEC.read_text(encoding="utf-8")
        declared = _declared_acceptance_criteria(spec)
        self.assertTrue(declared, "SPEC.md anchors no acceptance criteria")
        dangling = sorted(_cited(spec, _ACCEPTANCE_REFERENCE) - declared)
        self.assertEqual(
            [],
            dangling,
            f"SPEC.md cites acceptance criteria that are not anchored: {dangling}",
        )

    def test_a_fabricated_decision_citation_fails_by_name(self) -> None:
        declared = _declared_decisions(DECISIONS.read_text(encoding="utf-8"))
        fabricated = f"D{max(int(name[1:]) for name in declared) + 400}"
        cited = _cited(f"per {fabricated} the rule holds", _DECISION_REFERENCE)
        self.assertEqual({fabricated}, cited - declared)

    def test_a_fabricated_acceptance_citation_fails_by_name(self) -> None:
        declared = _declared_acceptance_criteria(SPEC.read_text(encoding="utf-8"))
        cited = _cited("proven by AC-PHANTOM-01", _ACCEPTANCE_REFERENCE)
        self.assertEqual({"AC-PHANTOM-01"}, cited - declared)


class DeclarationShapedTextIsNotADeclarationTests(unittest.TestCase):
    """Every source-scanning false green from both review rounds, RED-provable against
    any regex-over-source implementation because the renderer decides."""

    def test_a_fenced_decision_heading_declares_nothing(self) -> None:
        source = "## D1 real\n\n```\n## D901 example only\n```\n\nPer D901.\n"
        self.assertNotIn("D901", _declared_decisions(source))
        self.assertIn("D901", _cited(source, _DECISION_REFERENCE))

    def test_a_longer_closing_fence_is_refused_not_guessed(self) -> None:
        """CommonMark fences this; the locked renderer renders it. The gate refuses
        the ambiguous document by name instead of siding with either oracle."""
        source = "## D1 real\n\n```\n## D902 example\n````\n\nPer D902.\n"
        with self.assertRaises(AmbiguousFenceError):
            _declared_decisions(source)

    def test_an_html_comment_declares_nothing(self) -> None:
        source = "## D1 real\n\n<!--\n## D903 hidden\n-->\n\nPer D903.\n"
        self.assertNotIn("D903", _declared_decisions(source))

    def test_inline_code_anchor_declares_nothing(self) -> None:
        source = '`<a id="ac-phantom-01"></a>` then AC-PHANTOM-01.\n'
        self.assertNotIn("AC-PHANTOM-01", _declared_acceptance_criteria(source))

    def test_indented_code_anchor_declares_nothing(self) -> None:
        source = 'text\n\n    <a id="ac-phantom-02"></a>\n\nAC-PHANTOM-02.\n'
        self.assertNotIn("AC-PHANTOM-02", _declared_acceptance_criteria(source))

    def test_a_longer_identifier_does_not_declare_its_prefix(self) -> None:
        source = "## D900X not an exact decision heading\n\nPer D900.\n"
        self.assertEqual(set(), _declared_decisions(source))


if __name__ == "__main__":
    unittest.main()
