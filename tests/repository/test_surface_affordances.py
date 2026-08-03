"""Two rules about what the operator can read off a control without clicking it.

Round-3 QA drove every control on the live board and found the same failure in
two places, both of them the surface telling the truth only in a native `title` —
invisible on the screen, absent on touch, unreachable by keyboard:

* `+ New ticket` was a styled `<span>` in the primary call-to-action slot, 219 by
  34 pixels, bordered and filled, doing nothing when clicked, with its only excuse in
  a hover. The Feed composer and the Files Save/Revert controls already did this
  properly — real `disabled` attributes, a visible verdict chip, the reason
  printed on the control — so this broke a pattern the app had right (#240).
* the Inbox seat tabs printed **unread** and the panel beside them printed
  **total**, both as bare numbers, both unlabelled, and they disagreed for the
  same seat in the same viewport. The seat with the most mail on the box, 485
  messages all read, rendered as a bare `0` (#239).

Both checks derive their denominator from the tree, so a new inert control or a
new counted tab is covered the day it is written rather than the day someone
remembers to add it here.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui/src"
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# the two shared treatments every disabled affordance on this surface uses
_INERT_STYLE = re.compile(r"\bINERT_(?:CONTROL|FIELD)\b")
_REAL_CONTROLS = ("button", "textarea", "input", "select")
# a JSX element from its opening angle bracket to the end of its attributes
_ELEMENT = re.compile(r"<([A-Za-z][\w.]*)((?:[^<>{}]|\{[^{}]*\})*?)/?>", re.DOTALL)
# the count pill the vendored stylesheet renders, and the one component allowed
# to write it — the type there pairs every number with the unit it counts in
_COUNT_PILL = re.compile(r'className="n"')
_PILL_OWNER = "apps/ctower-ui/src/surfaces/Count.tsx"


def _code(path: Path) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8")))


def _screens() -> tuple[Path, ...]:
    return tuple(sorted(_SURFACE.rglob("*.tsx")))


class InertAffordanceTests(unittest.TestCase):
    """A control the runtime ignores has to look ignored before it is clicked."""

    def test_the_scan_finds_a_non_empty_denominator(self) -> None:
        self.assertGreater(len(_screens()), 10, "the screen scan found almost nothing")

    def test_every_inert_affordance_is_a_real_control_carrying_disabled(self) -> None:
        offenders: list[str] = []
        for path in _screens():
            for match in _ELEMENT.finditer(_code(path)):
                tag, attributes = match.group(1), match.group(2)
                if _INERT_STYLE.search(attributes) is None:
                    continue
                where = f"{path.relative_to(_ROOT).as_posix()}: <{tag}>"
                if tag not in _REAL_CONTROLS:
                    offenders.append(f"{where} is not a control the browser can disable")
                elif not re.search(r"\bdisabled\b", attributes):
                    offenders.append(f"{where} is styled inert but carries no disabled attribute")
        self.assertEqual(
            offenders,
            [],
            "an inert-looking element is not a disabled control; a styled span that swallows a "
            "click is the dead control the craft rules forbid",
        )

    def test_the_primary_action_slot_holds_a_disabled_button(self) -> None:
        sidebar = _code(_SURFACE / "frame/Sidebar.tsx")
        action = re.search(r'<(\w+)([^>]*?className="sact"[^>]*?)>', sidebar, re.DOTALL)
        self.assertIsNotNone(action, "the primary action slot has no control in it at all")
        assert action is not None
        self.assertEqual(
            action.group(1),
            "button",
            "the app's most prominent control is not a button, so it cannot be disabled",
        )
        self.assertIn("disabled", action.group(2))

    def test_the_primary_action_prints_its_reason_rather_than_hiding_it_in_a_hover(self) -> None:
        sidebar = _code(_SURFACE / "frame/Sidebar.tsx")
        self.assertIn(
            "NEW_TICKET_INERT.reason",
            sidebar,
            "the reason this control cannot be honoured is not rendered on the screen",
        )
        self.assertIn("NEW_TICKET_INERT.verdict", sidebar)
        self.assertNotIn(
            'title="Phase 1 is read-only',
            sidebar,
            "the reason is still carried by a native title, which no touch or keyboard "
            "user reaches",
        )

    def test_the_reason_names_what_the_operator_can_do_instead(self) -> None:
        rail = (_SURFACE / "frame/rail.ts").read_text(encoding="utf-8")
        reason = re.search(r"reason:\s*\n?\s*\"([^\"]+)\"", rail)
        self.assertIsNotNone(reason, "the inert primary action declares no reason")
        assert reason is not None
        self.assertIn("ctowerctl ticket capture", reason.group(1))


class LabelledCountTests(unittest.TestCase):
    """A number on a tab means nothing until the screen says what it counts."""

    def test_the_count_contract_pairs_every_number_with_its_unit(self) -> None:
        tabs = _code(_SURFACE / "surfaces/ChoiceTabs.tsx")
        self.assertIn(
            "readonly unit: string;",
            tabs,
            "the tab count type lets a number be passed without the unit it counts in, which "
            "is how one component came to mean unread on one screen and total on another",
        )
        self.assertNotIn(
            "readonly count?: number;",
            tabs,
            "a bare number is still representable as a tab count",
        )

    def test_the_count_pill_is_written_in_exactly_one_component(self) -> None:
        writers = sorted(
            path.relative_to(_ROOT).as_posix()
            for path in _screens()
            if _COUNT_PILL.search(_code(path))
        )
        self.assertEqual(
            writers,
            [_PILL_OWNER],
            "a screen writes the count pill itself; route it through surfaces/Count.tsx, which "
            "cannot render a number without the unit it counts in — a bare `0` beside a seat "
            "holding 485 read messages is how #239 reached the operator",
        )

    def test_that_component_cannot_render_a_number_without_its_unit(self) -> None:
        count = _code(_SURFACE / "surfaces/Count.tsx")
        self.assertIn(
            "readonly unit: string;", count, "the unit is optional, so it will be omitted"
        )
        self.assertIn("{unit}", count, "the unit is accepted and then not rendered")

    def test_every_screen_that_counts_states_what_it_counts(self) -> None:
        missing = [
            f"{path.relative_to(_ROOT).as_posix()}: {match.group(1)[:60]}"
            for path in _screens()
            for match in re.finditer(r"<Count\b((?:[^<>]|\{[^{}]*\})*?)/>", _code(path), re.DOTALL)
            if "unit=" not in match.group(1)
        ]
        self.assertEqual(missing, [], "a count was rendered without naming what it counts")

    def test_the_inbox_tab_counts_unread_and_says_so(self) -> None:
        inbox = _code(_SURFACE / "app/inbox/page.tsx")
        self.assertIn('unit: "unread"', inbox)

    def test_the_inbox_panel_names_what_its_own_number_counts(self) -> None:
        inbox = _code(_SURFACE / "app/inbox/page.tsx")
        self.assertIn(
            "messages this seat holds",
            inbox,
            "the panel prints a total a few pixels from a tab printing unread, unlabelled",
        )

    def test_the_tab_row_wraps_rather_than_clipping_its_last_tab(self) -> None:
        for name in ("surfaces/ChoiceTabs.tsx", "surfaces/board/SourceTabs.tsx"):
            with self.subTest(component=name):
                self.assertIn(
                    'flexWrap: "wrap"',
                    _code(_SURFACE / name),
                    "the tab row clips instead of wrapping, and the clipped tab is the one "
                    "whose count most needs reading",
                )


if __name__ == "__main__":
    unittest.main()
