"""The Inbox send box asks the server for one message and claims no identity."""

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
_FIXTURE = Path(__file__).with_name("inbox_send_fixtures.ts")
_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000600"
_EXPECTED_BODY = f'{{"text":"ready for the taste gate","thread_id":"{_THREAD_ID}","to":"engineer"}}'


class InboxSendTransportTests(unittest.TestCase):
    def test_the_command_carries_only_text_thread_and_a_server_read_recipient(self) -> None:
        """The browser names no sender, no recipient, and no authorization fact.

        `to` is an identity. It is therefore read back from the server's own
        recipient-scoped projection at submit time rather than posted from a
        form, so a recipient a browser could edit does not exist on this path.
        """
        outcomes = ts.drive(_FIXTURE)
        attempts = cast("list[dict[str, Any]]", outcomes["accepted"])
        success = cast("dict[str, Any]", outcomes["success"])

        self.assertEqual([attempt["method"] for attempt in attempts], ["GET", "POST"])
        self.assertTrue(attempts[0]["url"].endswith("/v1/inbox/threads"))
        self.assertTrue(attempts[1]["url"].endswith("/v1/inbox/messages"))
        self.assertEqual(attempts[1]["bodyKeys"], ["text", "thread_id", "to"])
        self.assertEqual(attempts[1]["body"], _EXPECTED_BODY)
        self.assertRegex(cast("str", attempts[1]["idempotencyKey"]), r"^[0-9a-f-]{36}$")
        self.assertTrue(attempts[1]["authorized"])
        self.assertIsNone(attempts[0]["idempotencyKey"])

        self.assertEqual(
            success,
            {
                "kind": "sent",
                "message": {
                    "messageId": "018f0d5e-7b9a-7c01-8000-000000000702",
                    "position": 2,
                    "from": "designer",
                    "to": "engineer",
                    "text": "ready for the taste gate",
                    "sentAt": "2026-08-09T03:05:00Z",
                },
            },
        )

    def test_a_server_refusal_reaches_the_operator_as_its_own_human_sentence(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        refusal = cast("dict[str, Any]", outcomes["refusal"])
        opaque = cast("dict[str, Any]", outcomes["opaque"])

        self.assertEqual(refusal["kind"], "refused")
        self.assertEqual(
            refusal["message"], "The authenticated principal has no addressable project seat."
        )
        self.assertNotIn("{", refusal["message"])
        self.assertNotIn("422", refusal["message"])
        self.assertEqual(opaque["kind"], "refused")
        self.assertEqual(
            opaque["message"], "The server refused the message without a usable explanation."
        )

    def test_an_unaddressable_thread_and_an_empty_message_send_no_command(self) -> None:
        """Refusing before the boundary is refusing without a recorded attempt."""
        outcomes = ts.drive(_FIXTURE)
        stranger = cast("dict[str, Any]", outcomes["stranger"])
        blank = cast("dict[str, Any]", outcomes["blank"])

        self.assertEqual(stranger["kind"], "refused")
        self.assertEqual(
            stranger["message"],
            "This thread's other participant could not be read, so nothing was sent.",
        )
        self.assertEqual(
            [attempt["method"] for attempt in cast("list[Any]", outcomes["strangerAttempts"])],
            ["GET"],
        )

        self.assertEqual(blank["kind"], "refused")
        self.assertEqual(blank["message"], "Write a message before sending.")
        self.assertEqual(cast("list[Any]", outcomes["blankAttempts"]), [])

    def test_a_retryable_status_reuses_the_one_minted_idempotency_key(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        retried = cast("dict[str, Any]", outcomes["retried"])
        keys = cast("list[str]", outcomes["retryKeys"])

        self.assertEqual(retried["kind"], "sent")
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])
        self.assertRegex(keys[0], r"^[0-9a-f-]{36}$")


class InboxSendComponentTests(unittest.TestCase):
    def test_the_send_box_holds_no_credential_network_client_or_identity_field(self) -> None:
        component = (_SURFACE / "surfaces/inbox/SendMessage.tsx").read_text(encoding="utf-8")
        action = (_SURFACE / "app/inbox/actions.ts").read_text(encoding="utf-8")
        page = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")

        self.assertIn('"use client"', component)
        self.assertIn("useActionState", component)
        self.assertNotIn("fetch(", component)
        self.assertNotIn("Authorization", component)
        # one field, and it is the message: no sender, recipient or scope input
        self.assertEqual(component.count('name="'), 1)
        self.assertIn('name="text"', component)

        self.assertIn('"use server"', action)
        self.assertIn("sendInboxMessage(threadId,", action)
        self.assertIn('revalidatePath("/inbox")', action)

        self.assertIn("<SendMessage", page)
        self.assertIn("sendMessageAction.bind(null, thread.threadId)", page)
        # the accepted row is drawn only while the thread read lacks its identity
        self.assertIn("settled={thread.messages.map((message) => message.messageId)}", page)
        self.assertIn("!settled.includes(state.message.messageId)", component)

    def test_the_provenance_line_names_both_server_authorized_paths(self) -> None:
        foot = (_SURFACE / "frame/RecordFoot.tsx").read_text(encoding="utf-8")

        self.assertIn("server-authorized Inbox send and promotion paths", foot)
        self.assertNotIn("read-only v1 · no mutation path exists on this surface", foot)


if __name__ == "__main__":
    unittest.main()
