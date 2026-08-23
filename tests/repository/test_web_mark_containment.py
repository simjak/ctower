"""A mark's hidden word may not escape whatever clips the mark.

`apps/ctower-web/src/ui/marks.tsx` renders a screen-reader word next to every
mark glyph. That word carries Tailwind's `sr-only`, which is `position:
absolute`; an absolutely positioned box with no positioned ancestor resolves
against the initial containing block, so a mark inside a scrolling pane lays its
hidden word out against the document instead, and every mark past the fold
extends the page's own scroll box rather than the pane's. The wrapper's
`relative` is the whole fix: it makes the mark itself the containing block, so
the word stays inside the same clip as the glyph it belongs to.

QA found that defect in custody on the cockpit's Work pane (2026-08-22) and it
was repaired in the shared `Mark`. This suite is the guard T-017 asks for: the
repair is one word in one class list, and nothing else in the tree notices if a
restyle drops it.

The rule is asserted from repository structure, not from a browser. D75 keeps
browser suites out of this repository's gates, and the headless walk in
mission-control owns the layout half of the evidence. What is owned here is the
source property that layout depends on — the half that regresses in a diff. So
the enclosing element is discovered by walking the file's own JSX rather than by
grepping for a word that could sit anywhere in the file, and it must open a
positioning context.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MARKS = "apps/ctower-web/src/ui/marks.tsx"

# One JSX tag. A braced attribute value can hold `<`, `>`, and a nested brace,
# so it is consumed whole instead of character by character; the attributes are
# non-greedy so a self-closing slash stays out of them.
_TAG = re.compile(
    r"<(?P<close>/?)[A-Za-z][\w.]*"
    r"(?P<attributes>(?:[^<>{}]|\{(?:[^{}]|\{[^{}]*\})*\})*?)"
    r"(?P<selfclose>/?)>"
)
_HIDDEN_WORD = re.compile(r"(?<![\w-])sr-only(?![\w-])")
# The values that make an element a containing block for an absolutely
# positioned child. Anything else leaves the child anchored to the document.
_POSITIONING = re.compile(r"(?<![\w-])(?:relative|absolute|fixed|sticky)(?![\w-])")

__all__: tuple[str, ...] = ()


def _wrappers_of_hidden_words(source: str) -> tuple[str, ...]:
    """The attributes of the element enclosing each hidden word, in source order.

    An unenclosed hidden word yields the empty attributes of the document, which
    positions nothing — the exact state this suite exists to reject.
    """

    open_elements: list[str] = [""]
    wrappers: list[str] = []
    for tag in _TAG.finditer(source):
        attributes = tag.group("attributes")
        if tag.group("close"):
            open_elements = open_elements[:-1] or [""]
            continue
        if _HIDDEN_WORD.search(attributes):
            wrappers.append(open_elements[-1])
        if not tag.group("selfclose"):
            open_elements.append(attributes)
    return tuple(wrappers)


class MarkHiddenWordContainmentTests(unittest.TestCase):
    """The `Mark` keeps its screen-reader word inside its own box."""

    def setUp(self) -> None:
        self.wrappers = _wrappers_of_hidden_words((_ROOT / _MARKS).read_text(encoding="utf-8"))

    def test_the_mark_still_hides_one_word_for_a_screen_reader(self) -> None:
        """The denominator, so a silent rename cannot turn this suite into a no-op."""

        self.assertEqual(
            len(self.wrappers),
            1,
            f"{_MARKS} no longer renders exactly one screen-reader-only word; either the "
            "accessible word DESIGN.md requires is gone, or this suite is asserting nothing",
        )

    def test_the_hidden_word_stays_inside_what_clips_the_mark(self) -> None:
        for index, attributes in enumerate(self.wrappers):
            with self.subTest(wrapper=index):
                self.assertRegex(
                    attributes,
                    _POSITIONING,
                    f"the element enclosing the hidden word in {_MARKS} opens no positioning "
                    "context, so the word resolves against the document: a mark in a scrolling "
                    "pane would extend the page's scroll box instead of its own",
                )

    def test_an_unpositioned_wrapper_is_still_detectable(self) -> None:
        """The regressed shape, so the guard cannot pass by failing to see anything."""

        regressed = _wrappers_of_hidden_words(
            '<span className="inline-block"><span className="sr-only">done</span></span>'
        )

        self.assertEqual(len(regressed), 1)
        self.assertNotRegex(regressed[0], _POSITIONING)


if __name__ == "__main__":
    unittest.main()
