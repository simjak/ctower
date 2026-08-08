"""The Inbox promote control delegates exactly one authority-bearing request to the server."""

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
_FIXTURE = Path(__file__).with_name("inbox_promotion_fixtures.ts")


class InboxPromotionTransportTests(unittest.TestCase):
    def test_promotion_posts_only_the_optional_target_and_surfaces_the_problem_detail(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        success = cast("dict[str, Any]", outcomes["success"])
        refusal = cast("dict[str, Any]", outcomes["refusal"])
        request = cast("dict[str, Any]", outcomes["request"])

        self.assertEqual(success["kind"], "promoted")
        self.assertEqual(success["outcome"], "ticket_linked")
        self.assertEqual(success["ticketId"], "018f0d5e-7b9a-7c01-8000-000000000010")
        self.assertEqual(request["method"], "POST")
        self.assertTrue(
            request["url"].endswith(
                "/v1/inbox/threads/018f0d5e-7b9a-7c01-8000-000000000600/promotion"
            )
        )
        self.assertEqual(request["body"], '{"ticket_id":"018f0d5e-7b9a-7c01-8000-000000000010"}')
        self.assertRegex(cast("str", request["idempotencyKey"]), r"^[0-9a-f-]{36}$")
        self.assertEqual(refusal["kind"], "refused")
        self.assertEqual(refusal["message"], "The inbox thread is already linked to a ticket.")
        self.assertNotIn("{", refusal["message"])


class InboxPromotionComponentTests(unittest.TestCase):
    def test_the_client_has_local_action_state_but_no_credential_or_network_client(self) -> None:
        component = (_SURFACE / "surfaces/inbox/PromoteThread.tsx").read_text(encoding="utf-8")
        action = (_SURFACE / "app/inbox/actions.ts").read_text(encoding="utf-8")
        page = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")

        self.assertIn('"use client"', component)
        self.assertIn("useActionState", component)
        self.assertIn("Promote thread", component)
        self.assertIn("Create a new ticket from this thread", component)
        self.assertNotIn("fetch(", component)
        self.assertNotIn("Authorization", component)
        self.assertIn('"use server"', action)
        self.assertIn("promoteInboxThread(threadId, ticketId)", action)
        self.assertIn("<PromoteThread", page)
        self.assertIn("thread.promotedTicketId === null", page)


if __name__ == "__main__":
    unittest.main()
