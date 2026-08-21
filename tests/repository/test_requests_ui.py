"""Regression contract for the operator Requests surface.

The Requests API and CLI already exist. This suite keeps the browser slice
honest: it must use the existing bounded read seam, expose the route in the
shared rail, preserve the server-provided row order, and say that exact-order
re-ranking is unavailable instead of wiring the unrelated priority command.

The last three cases cover what the ledger draws. Every value the record can
hold on either of its two axes must have a mark, because an unmapped value
renders as nothing at all; a ticket the record mirrored the ask into must be a
link to the screen that already serves it; and a priority nobody chose must not
be drawn as a decision somebody made.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui/src"


class RequestsSurfaceTests(unittest.TestCase):
    def test_the_requests_route_is_dynamic_and_reads_the_adapter(self) -> None:
        page = _SURFACE / "app/requests/page.tsx"
        self.assertTrue(page.is_file(), "the operator Requests route is missing")
        source = page.read_text(encoding="utf-8")
        self.assertIn('dynamic = "force-dynamic"', source)
        self.assertIn("recordAdapter.requests", source)
        self.assertIn("<Resolved", source)

    def test_the_read_contract_and_adapter_bind_the_existing_requests_endpoint(self) -> None:
        interface = (_SURFACE / "read/interface.ts").read_text(encoding="utf-8")
        adapter = (_SURFACE / "read/adapter.ts").read_text(encoding="utf-8")
        http = (_SURFACE / "read/httpRecordAdapter.ts").read_text(encoding="utf-8")
        self.assertIn("requests:", interface)
        self.assertIn("requests: httpRecordAdapter.requests", adapter)
        self.assertIn('"/v1/requests"', http)
        self.assertIn("unanswered_projects", http)

    def test_the_rail_exposes_requests_once(self) -> None:
        rail = (_SURFACE / "frame/rail.ts").read_text(encoding="utf-8")
        self.assertEqual(rail.count('href: "/requests"'), 1)
        self.assertIn('label: "Requests"', rail)
        self.assertIn(
            '"/requests": icon(', (_SURFACE / "frame/Sidebar.tsx").read_text(encoding="utf-8")
        )

    def test_the_queue_keeps_record_order_and_declares_reranking_unavailable(self) -> None:
        page = (_SURFACE / "app/requests/page.tsx").read_text(encoding="utf-8")
        self.assertNotIn(".sort(", page, "the browser must not invent a ranking")
        self.assertRegex(page, re.compile(r"\.map\(.*request", re.DOTALL))
        self.assertRegex(
            page,
            re.compile(r"re-?ranking is not yet available", re.IGNORECASE),
            "the absent AC-PM-02 permutation command must be visible on the screen",
        )
        self.assertNotIn("request prioritize", page)

    def test_rows_render_unowned_without_a_blank_owner(self) -> None:
        page = (_SURFACE / "app/requests/page.tsx").read_text(encoding="utf-8")
        self.assertIn("unowned", page.lower())
        self.assertNotIn(
            "Count value={rows.length}",
            page,
            "a page count must not be derived from a potentially truncated row array",
        )
        self.assertNotIn(
            "rows.length.toString()",
            page,
            "a page count must not be derived from a potentially truncated row array",
        )

    def test_every_recorded_state_and_triage_value_has_a_mark(self) -> None:
        page = (_SURFACE / "app/requests/page.tsx").read_text(encoding="utf-8")
        for value in ("NEW", "TRIAGED", "WIP", "BLOCKED", "DONE"):
            with self.subTest(state=value):
                self.assertRegex(page, rf"\b{value}: ")
        for value in ("UNTRIAGED", "ACCEPTED", "DUPLICATE", "REJECTED"):
            with self.subTest(triage=value):
                self.assertRegex(page, rf"\b{value}: ")
        self.assertIn(
            "request-triage",
            page,
            "triage is the record's second axis and needs its own mark; folding it into "
            "the state chip draws an accepted row and a duplicate row identically",
        )

    def test_rows_link_the_tickets_the_record_mirrored_them_into(self) -> None:
        page = (_SURFACE / "app/requests/page.tsx").read_text(encoding="utf-8")
        self.assertIn("request.requiredTicketIds", page)
        self.assertIn("request.optionalTicketIds", page)
        self.assertIn(
            "/ticket/${encodeURIComponent(",
            page,
            "a mirrored ticket must be a link to the screen that serves it, not a label",
        )
        self.assertRegex(
            page,
            re.compile(r"links\.length === 0\s*\)\s*\{\s*return null", re.DOTALL),
            "a Request the record mirrored into no ticket must draw no link at all",
        )

    def test_a_default_priority_is_not_drawn_as_a_decision(self) -> None:
        page = (_SURFACE / "app/requests/page.tsx").read_text(encoding="utf-8")
        self.assertIn("request.priorityDefault", page)
        self.assertIn("dflt", page)
        self.assertIn(
            ".pri.dflt",
            (_SURFACE / "app/conductor.css").read_text(encoding="utf-8"),
            "the record's own default priority renders identically to a chosen one",
        )


if __name__ == "__main__":
    unittest.main()
