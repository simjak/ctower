"""gh#318 — the Inbox severity chip rendered the record's own generic word.

QA's R2811 sweep found the Inbox message list's severity chip rendering the
literal word `info` (DOM text `info`, chip label `INFO` once the vendored
stylesheet's `text-transform: uppercase` applies) — the exact word the
operator's standing no-generic-status-labels rule bans case-insensitively
(never INFO/WARNING/ERROR/LIVE). `severity_fixtures.ts` drives the real
`severityLabel` chokepoint with the record's actual vocabulary (`tools/notify`
sends exactly P0, P1 and info) and with adversarial values outside it, so the
guard holds as a class: a value this surface has not vetted fails loud rather
than silently reaching a screen as a banned word.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = Path(__file__).with_name("severity_fixtures.ts")
_INBOX_PAGE = _ROOT / "apps/ctower-ui/src/app/inbox/page.tsx"
_SEVERITY_MODULE = _ROOT / "apps/ctower-ui/src/surfaces/severity.ts"
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_OUTCOMES: dict[str, Any] = {}


def _outcomes() -> dict[str, Any]:
    if not _OUTCOMES:
        _OUTCOMES.update(ts.drive(_FIXTURE))
    return _OUTCOMES


def _case(name: str) -> dict[str, Any]:
    case = _outcomes()[name]
    if not isinstance(case, dict):
        raise TypeError(f"severity case {name} is not an object")
    return cast("dict[str, Any]", case)


def _code(path: Path) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8")))


class SeverityLabelTests(unittest.TestCase):
    """The instance: the record's real vocabulary resolves to branded chips."""

    def test_the_info_tier_reads_note_not_the_records_own_word(self) -> None:
        self.assertEqual(_case("realInfo"), {"thrown": False, "label": "NOTE"})

    def test_priority_severities_are_unchanged(self) -> None:
        self.assertEqual(_case("realP0"), {"thrown": False, "label": "P0"})
        self.assertEqual(_case("realP1"), {"thrown": False, "label": "P1"})


class NoGenericStatusLabelClassGuardTests(unittest.TestCase):
    """The class: no value this surface can be handed resolves to a banned word."""

    def test_no_case_of_a_banned_word_resolves_to_itself(self) -> None:
        for severity in ("INFO", "Info", "WARNING", "warning", "ERROR", "error", "LIVE", "Live"):
            with self.subTest(severity=severity):
                case = _case(f"adversarial_{severity}")
                self.assertTrue(
                    case["thrown"],
                    f'"{severity}" resolved to {case["label"]!r} instead of failing loud; a '
                    "banned generic status label reached a chip unvetted",
                )

    def test_the_banned_set_is_unreachable_across_the_whole_domain(self) -> None:
        self.assertTrue(
            _outcomes()["neverResolvesToABannedLabel"],
            "at least one severity resolved to a rendered label matching "
            "INFO|WARNING|ERROR|LIVE — the banned set is still reachable, not impossible",
        )


class SeverityChokepointTests(unittest.TestCase):
    """A severity may only reach the Inbox chip through the vetted label."""

    def test_the_inbox_page_renders_the_label_not_the_raw_severity(self) -> None:
        page = _code(_INBOX_PAGE)
        self.assertIn(
            "severityLabel(message.severity)",
            page,
            "the Inbox chip does not route the message's severity through severityLabel()",
        )
        self.assertNotIn(
            ">{message.severity}<",
            page,
            "the Inbox chip renders the record's raw severity text directly, bypassing the "
            "vetted label and reopening the no-generic-status-labels violation",
        )

    def test_the_severity_module_declares_the_banned_set(self) -> None:
        module = _code(_SEVERITY_MODULE)
        for word in ("info", "warning", "error", "live"):
            with self.subTest(word=word):
                self.assertIn(word, module.lower())


if __name__ == "__main__":
    unittest.main()
