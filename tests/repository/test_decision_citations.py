"""Every decision citation must resolve to a real target.

A citation that points nowhere is worse than a missing one: it reads as provenance,
survives merge, and is invisible to everyone who trusts it. `D58` shipped a repair for
exactly this class after a review caught it attributing a rule to a decision that never
contained one (2026-08-11).

What this gate proves and what it cannot: it proves every cited `D<n>` and `AC-FAM-nn`
identifier RESOLVES to a declared decision heading or acceptance anchor. It cannot prove
that the cited target actually SAYS what the citing sentence claims — a citation whose
number exists but whose content does not support the claim is a reviewer obligation, not a
mechanical one, and the review checklist carries it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "DECISIONS.md"
SPEC = ROOT / "SPEC.md"

_DECISION_HEADING = re.compile(r"^## (D\d+)(?!\w)", re.MULTILINE)
_DECISION_REFERENCE = re.compile(r"\b(D\d+)\b")
_ACCEPTANCE_ANCHOR = re.compile(r'<a id="(ac-[a-z]+-\d+)"></a>')
_ACCEPTANCE_REFERENCE = re.compile(r"\b(AC-[A-Z]+-\d+)\b")
_FENCED_BLOCK = re.compile(r"^(`{3,}|~{3,}).*?^\1\s*$", re.MULTILINE | re.DOTALL)


def _rendered_text(source: str) -> str:
    """Markdown-visible text only: fenced code blocks are examples, not declarations
    or citations. Scanning raw bytes accepted a fenced `## D901` as a real decision
    heading and a fenced anchor tag as a live anchor (the #484 first-review false
    greens); both sides scan symmetric rendered text so a fence can neither declare
    nor cite."""
    return _FENCED_BLOCK.sub("", source)


def _declared_decisions() -> set[str]:
    return set(_DECISION_HEADING.findall(_rendered_text(DECISIONS.read_text(encoding="utf-8"))))


def _declared_acceptance_criteria() -> set[str]:
    anchors = _ACCEPTANCE_ANCHOR.findall(_rendered_text(SPEC.read_text(encoding="utf-8")))
    return {anchor.upper() for anchor in anchors}


class DecisionCitationsResolveTests(unittest.TestCase):
    def test_every_cited_decision_is_declared(self) -> None:
        declared = _declared_decisions()
        self.assertTrue(declared, "DECISIONS.md declares no decisions")
        for source in (DECISIONS, SPEC):
            cited = set(_DECISION_REFERENCE.findall(_rendered_text(source.read_text(encoding="utf-8"))))
            dangling = sorted(cited - declared, key=lambda name: int(name[1:]))
            self.assertEqual(
                [],
                dangling,
                f"{source.name} cites decisions that do not exist: {dangling}",
            )

    def test_every_cited_acceptance_criterion_is_anchored(self) -> None:
        declared = _declared_acceptance_criteria()
        self.assertTrue(declared, "SPEC.md anchors no acceptance criteria")
        cited = set(_ACCEPTANCE_REFERENCE.findall(_rendered_text(SPEC.read_text(encoding="utf-8"))))
        dangling = sorted(cited - declared)
        self.assertEqual(
            [],
            dangling,
            f"SPEC.md cites acceptance criteria that are not anchored: {dangling}",
        )

    def test_a_fabricated_decision_citation_fails_by_name(self) -> None:
        declared = _declared_decisions()
        fabricated = f"D{max(int(name[1:]) for name in declared) + 400}"
        cited = set(_DECISION_REFERENCE.findall(f"per {fabricated} the rule holds"))
        self.assertEqual({fabricated}, cited - declared)

    def test_a_fabricated_acceptance_citation_fails_by_name(self) -> None:
        declared = _declared_acceptance_criteria()
        cited = set(_ACCEPTANCE_REFERENCE.findall("proven by AC-PHANTOM-01"))
        self.assertEqual({"AC-PHANTOM-01"}, cited - declared)




class DeclarationShapedTextIsNotADeclarationTests(unittest.TestCase):
    """The three false-green constructions from the #484 first review, kept RED-provable."""

    def test_a_fenced_decision_heading_declares_nothing(self) -> None:
        source = "## D1 — real\n\n```\n## D901 — example only\n```\nPer D901.\n"
        declared = set(_DECISION_HEADING.findall(_rendered_text(source)))
        cited = set(_DECISION_REFERENCE.findall(_rendered_text(source)))
        self.assertNotIn("D901", declared)
        self.assertEqual({"D901"}, cited - declared - {"D1"})

    def test_a_fenced_anchor_declares_nothing(self) -> None:
        source = "```\n<a id=\"ac-phantom-01\"></a>\n```\nProven by AC-PHANTOM-01.\n"
        declared = {a.upper() for a in _ACCEPTANCE_ANCHOR.findall(_rendered_text(source))}
        self.assertNotIn("AC-PHANTOM-01", declared)

    def test_a_longer_identifier_does_not_declare_its_prefix(self) -> None:
        source = "## D900X not an exact decision heading\n\nPer D900.\n"
        declared = set(_DECISION_HEADING.findall(_rendered_text(source)))
        self.assertEqual(set(), declared)


if __name__ == "__main__":
    unittest.main()
