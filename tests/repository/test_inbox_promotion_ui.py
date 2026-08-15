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

    def test_a_transient_status_retries_when_the_body_is_not_a_problem_document(self) -> None:
        """A `text/plain` or empty 5xx is a transient status, not a parse failure.

        A proxy in front of the API answers `503 service unavailable` as text.
        Reading that body as JSON before the status was classified turned a
        retryable crossing into a terminal `SyntaxError` and the mutation
        stopped after one attempt.
        """
        outcomes = ts.drive(_FIXTURE)
        plain_text = cast("dict[str, Any]", outcomes["plainTextRetryThenSuccess"])
        empty_body = cast("dict[str, Any]", outcomes["emptyBodyExhaustion"])
        refusal = cast("dict[str, Any]", outcomes["plainTextRefusal"])

        self.assertEqual(
            plain_text["result"],
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
        self.assertEqual(
            plain_text["keys"], ["promotion-plain-text-key", "promotion-plain-text-key"]
        )

        failure = cast("dict[str, Any]", empty_body["failure"])
        self.assertEqual(failure["attempts"], 3)
        self.assertEqual(failure["status"], 503)
        self.assertEqual(failure["failureClass"], "transient")
        self.assertEqual(
            empty_body["keys"],
            ["promotion-empty-body-key", "promotion-empty-body-key", "promotion-empty-body-key"],
        )

        self.assertEqual(refusal["kind"], "refused")
        self.assertEqual(
            refusal["message"], "The server refused the promotion without a usable explanation."
        )


class InboxPromotionComponentTests(unittest.TestCase):
    def test_the_client_has_local_action_state_but_no_credential_or_network_client(self) -> None:
        component = (_SURFACE / "surfaces/chat/LinkTicket.tsx").read_text(encoding="utf-8")
        action = (_SURFACE / "app/inbox/actions.ts").read_text(encoding="utf-8")
        page = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")

        self.assertIn('"use client"', component)
        self.assertIn("useActionState", component)
        self.assertIn("new ticket from this conversation", component)
        self.assertIn("link an existing ticket", component)
        self.assertNotIn("fetch(", component)
        self.assertNotIn("Authorization", component)
        self.assertIn('"use server"', action)
        self.assertIn("promoteInboxThread(threadId, ticketId)", action)
        self.assertIn("<LinkTicket", page)
        self.assertIn("thread.promotedTicketId === null", page)

    def test_no_read_only_claim_survives_outside_the_control_that_earns_it(self) -> None:
        """This surface writes. Only the one action it cannot honour says otherwise.

        The provenance foot once carried an authority sentence on every screen
        and the rail called its inert action `read-only v1`. Both were app-wide
        claims about a surface that sends messages, starts conversations and
        links tickets. What is actually true is narrower: ctower captures a
        ticket through its CLI, so that one control is the only thing that says
        it cannot be pressed, and it says why in two words.
        """
        foot = (_SURFACE / "frame/RecordFoot.tsx").read_text(encoding="utf-8")
        rail = (_SURFACE / "frame/rail.ts").read_text(encoding="utf-8")

        self.assertNotIn("read-only", foot)
        self.assertIn('label: "New ticket"', rail)
        self.assertIn('verdict: "cli only"', rail)


if __name__ == "__main__":
    unittest.main()
