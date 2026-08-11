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

_DECISION_HEADING = re.compile(r"^## (D\d+)", re.MULTILINE)
_DECISION_REFERENCE = re.compile(r"\b(D\d+)\b")
_ACCEPTANCE_ANCHOR = re.compile(r'<a id="(ac-[a-z]+-\d+)"></a>')
_ACCEPTANCE_REFERENCE = re.compile(r"\b(AC-[A-Z]+-\d+)\b")


def _declared_decisions() -> set[str]:
    return set(_DECISION_HEADING.findall(DECISIONS.read_text(encoding="utf-8")))


def _declared_acceptance_criteria() -> set[str]:
    anchors = _ACCEPTANCE_ANCHOR.findall(SPEC.read_text(encoding="utf-8"))
    return {anchor.upper() for anchor in anchors}


class DecisionCitationsResolveTests(unittest.TestCase):
    def test_every_cited_decision_is_declared(self) -> None:
        declared = _declared_decisions()
        self.assertTrue(declared, "DECISIONS.md declares no decisions")
        for source in (DECISIONS, SPEC):
            cited = set(_DECISION_REFERENCE.findall(source.read_text(encoding="utf-8")))
            dangling = sorted(cited - declared, key=lambda name: int(name[1:]))
            self.assertEqual(
                [],
                dangling,
                f"{source.name} cites decisions that do not exist: {dangling}",
            )

    def test_every_cited_acceptance_criterion_is_anchored(self) -> None:
        declared = _declared_acceptance_criteria()
        self.assertTrue(declared, "SPEC.md anchors no acceptance criteria")
        cited = set(_ACCEPTANCE_REFERENCE.findall(SPEC.read_text(encoding="utf-8")))
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


if __name__ == "__main__":
    unittest.main()
