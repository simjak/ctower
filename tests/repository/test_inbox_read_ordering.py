"""The correspondent read's stated order is part of the SQL, provably.

T-021: ``routeTo`` resolves a recipient's project keys from the inbox
correspondents list and defers to that list's order, so the order has to be
stated once — in the kernel's SQL — rather than left to the table's scan
order. With only ``seat_key`` ordered, a seat key two projects share answers
in scan order and two towers can disagree about which project a compose names
first. PR #569 fixed it; this guard keeps it fixed.

This is the standing precedent of ``test_browser_network_chokepoint.py`` and
``test_web_bundle_list_order.py``: assert a source property from repository
structure and fail closed. Every fragment the address query is assembled from
must still exist (a rename cannot silently escape), the ordering fragment must
name BOTH columns in their declared order (a single-column or re-spelled
order is a different answer), and every composition site that assembles a read
from ``_ADDRESSABLE_SEATS`` must append that ordering fragment (no narrowed
read may quietly drop it). The negative controls prove the checks can fail:
an un-ordered composition is caught and a single-column fragment is caught.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_INBOX_SQL = (
    _ROOT / "packages" / "ctower-kernel" / "src" / "ctower_kernel" / "projections" / "_inbox_sql.py"
)

# The fragments the address query is assembled from. Each must still be
# defined exactly once in the module; if one is renamed or moved, name its
# successor here rather than letting the denominator shrink.
_FRAGMENTS = ("_ADDRESSABLE_SEATS", "_IN_ONE_PROJECT", "_IN_GRANTED_PROJECTS", "_BY_SEAT_KEY")

# The declared order itself, verbatim: seat first, project as tiebreak.
_ORDERING = re.compile(r"ORDER BY\s+seat_key\s*,\s*project_key\b")


def _stripped_source(path: Path) -> str:
    """Module text without comments, so prose can neither pass nor fail."""

    return re.sub(r"#.*$", "", path.read_text(encoding="utf-8"), flags=re.MULTILINE)


def _composition_sites(source: str) -> list[str]:
    """Every statement assembling a read from ``_ADDRESSABLE_SEATS``."""

    return [
        line.strip() for line in source.splitlines() if "_ADDRESSABLE_SEATS" in line and "+" in line
    ]


class InboxReadOrderingTests(unittest.TestCase):
    """Fail-closed guard: every addressable-seats read states its order."""

    def test_every_fragment_is_still_defined_exactly_once(self) -> None:
        offenders = [
            f"{fragment} is defined {len(definitions)} time(s), expected exactly once"
            for fragment in _FRAGMENTS
            if len(
                definitions := re.findall(
                    rf"^{fragment}\s*=", _stripped_source(_INBOX_SQL), flags=re.MULTILINE
                )
            )
            != 1
        ]
        self.assertEqual(
            offenders,
            [],
            "an _inbox_sql fragment vanished; the address query is assembled from "
            "these pieces, so point the inventory at wherever they went rather "
            "than letting the check pass vacuously",
        )

    def test_the_ordering_fragment_names_both_columns_in_declared_order(self) -> None:
        source = _stripped_source(_INBOX_SQL)
        match = re.search(r"^_BY_SEAT_KEY\s*=\s*(.+)$", source, flags=re.MULTILINE)
        self.assertIsNotNone(match, "_BY_SEAT_KEY lost its definition")
        literal = match.group(1) if match else ""
        self.assertRegex(
            literal,
            _ORDERING,
            "the correspondents' order must state seat_key then project_key: "
            "seat_key alone leaves a shared seat key to the table's scan order, "
            "so two towers could hand one tenant different first projects "
            "(the T-021 defect)",
        )

    def test_every_addressable_seats_composition_appends_the_ordering(self) -> None:
        source = _stripped_source(_INBOX_SQL)
        sites = _composition_sites(source)
        self.assertTrue(
            sites,
            "no composition of _ADDRESSABLE_SEATS found; either the address "
            "query moved (update this guard) or the denominator shrank",
        )
        unordered = [site for site in sites if "_BY_SEAT_KEY" not in site]
        self.assertEqual(
            unordered,
            [],
            "a read over addressable seats was assembled WITHOUT the declared "
            "order; narrowed and unnarrowed reads must share _BY_SEAT_KEY so "
            "they cannot drift into two different answers",
        )


class OrderingNegativeControlTests(unittest.TestCase):
    """A guard nobody has seen fail is not a guard."""

    def test_a_single_column_fragment_fails_the_column_check(self) -> None:
        self.assertIsNone(_ORDERING.search("    ORDER BY seat_key\\n"))

    def test_a_reordered_column_pair_fails_the_column_check(self) -> None:
        self.assertIsNone(_ORDERING.search("ORDER BY project_key, seat_key"))

    def test_an_unordered_composition_is_detected(self) -> None:
        fixture = (
            "            _ADDRESSABLE_SEATS + _IN_GRANTED_PROJECTS,\n"
            "            _ADDRESSABLE_SEATS + _IN_ONE_PROJECT + _BY_SEAT_KEY,\n"
        )
        unordered = [site for site in _composition_sites(fixture) if "_BY_SEAT_KEY" not in site]
        self.assertEqual(len(unordered), 1)
        self.assertIn("_IN_GRANTED_PROJECTS", unordered[0])


if __name__ == "__main__":
    unittest.main()
