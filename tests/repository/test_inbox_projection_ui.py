"""The inbox UI renders only strict, projection-backed durable-thread facts."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui/src"
_FIXTURE = Path(__file__).with_name("inbox_projection_fixtures.ts")


class InboxProjectionParserTests(unittest.TestCase):
    def test_projection_shapes_are_strict_and_keep_the_promotion_link(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        projection = cast("dict[str, Any]", outcomes["projection"])
        thread = cast("dict[str, Any]", outcomes["thread"])

        self.assertEqual(projection["recipient"], "ctower-commander")
        self.assertEqual(projection["totalUnread"], 1)
        self.assertEqual(projection["threads"][0]["unreadCount"], 1)
        self.assertEqual(
            projection["threads"][0]["promotedTicketId"],
            "018f0d5e-7b9a-7c01-8000-000000000010",
        )
        self.assertEqual(thread["messages"][0]["position"], 1)
        self.assertEqual(thread["readThroughPosition"], 1)
        self.assertEqual(thread["promotedTicketId"], "018f0d5e-7b9a-7c01-8000-000000000010")
        self.assertTrue(outcomes["rejectsNonBooleanUnreadOnly"]["thrown"])
        self.assertTrue(outcomes["rejectsNonIntegerUnreadCount"]["thrown"])
        accepts_explicit_null = cast("dict[str, Any]", outcomes["acceptsExplicitNullPromotion"])
        self.assertIsNone(accepts_explicit_null["projection"]["threads"][0]["promotedTicketId"])
        self.assertIsNone(accepts_explicit_null["thread"]["promotedTicketId"])
        self.assertTrue(outcomes["rejectsMissingProjectionPromotion"]["thrown"])
        self.assertTrue(outcomes["rejectsMissingThreadPromotion"]["thrown"])
        self.assertTrue(outcomes["rejectsMalformedProjectionPromotion"]["thrown"])
        self.assertTrue(outcomes["rejectsMalformedThreadPromotion"]["thrown"])


class InboxProjectionWiringTests(unittest.TestCase):
    def test_the_inbox_uses_only_the_projection_reads(self) -> None:
        adapter = (_SURFACE / "read/adapter.ts").read_text(encoding="utf-8")
        page = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")

        self.assertIn(
            '"ctower API · /v1/inbox/threads + /v1/inbox/threads/{id}'
            ' + /v1/inbox/messages + /promotion"',
            adapter,
        )
        self.assertIn("inbox: httpRecordAdapter.inbox", adapter)
        self.assertIn("inboxThread: httpRecordAdapter.inboxThread", adapter)
        self.assertIn("inboxCorrespondent: httpRecordAdapter.inboxCorrespondent", adapter)
        self.assertNotIn("inboxFile", adapter)
        self.assertIn("recordAdapter.inboxThread(threadId)", page)
        self.assertIn("recordAdapter.inbox()", page)

    def test_a_promoted_thread_and_its_ticket_are_linked_both_ways(self) -> None:
        inbox = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")
        ticket = (_SURFACE / "surfaces/ticket/TicketScreen.tsx").read_text(encoding="utf-8")

        self.assertIn("thread.promotedTicketId", inbox)
        self.assertIn("ticketHref(ticketId)", inbox)
        self.assertIn("row.inboxThreadIds", ticket)
        self.assertIn("/inbox?thread=${encodeURIComponent(threadId)}", ticket)


if __name__ == "__main__":
    unittest.main()
