"""Regression contract for the operator Requests surface.

The Requests API and CLI already exist. This suite keeps the browser slice
honest: it must use the existing bounded read seam, expose the route in the
shared rail, preserve the server-provided row order, and say that exact-order
re-ranking is unavailable instead of wiring the unrelated priority command.
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


if __name__ == "__main__":
    unittest.main()
