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

    def test_retryable_responses_retry_with_one_key_and_exhaust_under_the_bound(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        retry = cast("dict[str, Any]", outcomes["retryThenSuccess"])
        exhaustion = cast("dict[str, Any]", outcomes["exhaustion"])

        self.assertEqual(
            retry["result"],
            {
                "command_id": "018f0d5e-7b9a-7c01-8000-000000000700",
                "durability_state": "accepted",
                "event_ids": ["018f0d5e-7b9a-7c01-8000-000000000701"],
                "outcome": "ticket_linked",
                "thread_id": "018f0d5e-7b9a-7c01-8000-000000000600",
                "thread_version": 3,
                "ticket_id": "018f0d5e-7b9a-7c01-8000-000000000010",
            },
        )
        self.assertEqual(retry["keys"], ["promotion-retry-key", "promotion-retry-key"])
        retryable_status_keys = cast("list[dict[str, Any]]", outcomes["retryableStatusKeys"])
        self.assertEqual(
            [entry["status"] for entry in retryable_status_keys],
            [408, 425, 429, 500, 502, 503, 504],
        )
        for entry in retryable_status_keys:
            self.assertEqual(
                entry["keys"],
                [
                    f"promotion-retry-{entry['status']}-key",
                    f"promotion-retry-{entry['status']}-key",
                ],
            )
        self.assertEqual(exhaustion["attempts"], 3)
        self.assertEqual(exhaustion["status"], 503)
        self.assertEqual(exhaustion["failureClass"], "transient")
        self.assertEqual(
            outcomes["exhaustionKeys"],
            ["promotion-exhaustion-key", "promotion-exhaustion-key", "promotion-exhaustion-key"],
        )


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

    def test_inbox_copy_scopes_read_only_to_the_disabled_new_ticket_affordance(self) -> None:
        foot = (_SURFACE / "frame/RecordFoot.tsx").read_text(encoding="utf-8")
        rail = (_SURFACE / "frame/rail.ts").read_text(encoding="utf-8")

        self.assertNotIn("read-only v1 · no mutation path exists on this surface", foot)
        self.assertIn("server-authorized Inbox promotion path", foot)
        self.assertIn('label: "New ticket"', rail)
        self.assertIn('verdict: "read-only v1 · disabled"', rail)


if __name__ == "__main__":
    unittest.main()
