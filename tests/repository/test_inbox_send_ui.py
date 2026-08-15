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
_UNCONFIRMED_SENTENCE = (
    "The server has not confirmed this message, so it is not sent yet. "
    "Press send again to send the same message."
)
_LOST_REPLAY_SENTENCE = (
    "This retry lost track of the message waiting for confirmation. "
    "Reload the thread and send it again."
)


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


class InboxSendDurabilityTests(unittest.TestCase):
    """An answer that says it is not accepted is not read as an accepted one.

    ``202``/``durability_pending`` is the record telling this surface that the
    off-host acknowledgement its own acceptance rule requires has not
    committed. Every other byte of that answer is identical to the accepted
    one, so the discriminator is the whole difference between a recorded
    message and a message nobody has promised to keep.
    """

    def test_a_non_accepted_answer_is_not_read_as_a_sent_message(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        held = cast("dict[str, Any]", outcomes["held"])
        keys = cast("list[str]", outcomes["heldKeys"])

        self.assertEqual(held["kind"], "pending")
        self.assertNotIn("message_id", str(held))
        self.assertEqual(held["message"], _UNCONFIRMED_SENTENCE)
        # the words are the sender's until the record says otherwise, spaces and all
        self.assertEqual(held["text"], "  is this recorded?  ")
        self.assertEqual(len(keys), 1)
        self.assertEqual(held["commandId"], keys[0])

    def test_the_retry_of_an_unconfirmed_send_carries_its_command_identity(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        unresolved = cast("dict[str, Any]", outcomes["unresolved"])
        resolved = cast("dict[str, Any]", outcomes["resolved"])
        keys = cast("list[str]", outcomes["replayKeys"])

        self.assertEqual(unresolved["kind"], "pending")
        self.assertEqual(resolved["kind"], "sent")
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[0], unresolved["commandId"])

    def test_an_edited_message_is_a_new_command_rather_than_a_replay(self) -> None:
        """One key for two different requests is a conflict, not a retry."""
        outcomes = ts.drive(_FIXTURE)
        keys = cast("list[str]", outcomes["editedKeys"])
        edited = cast("dict[str, Any]", outcomes["edited"])

        self.assertEqual(edited["kind"], "pending")
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0], keys[1])
        self.assertEqual(keys[1], edited["commandId"])

    def test_an_unreadable_replay_identity_reaches_no_boundary_at_all(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        forged = cast("dict[str, Any]", outcomes["forged"])

        self.assertEqual(forged["kind"], "refused")
        self.assertEqual(forged["message"], _LOST_REPLAY_SENTENCE)
        self.assertEqual(forged["text"], "tampered state")
        self.assertEqual(cast("list[Any]", outcomes["forgedAttempts"]), [])


class InboxSendComponentTests(unittest.TestCase):
    def test_the_send_box_holds_no_credential_network_client_or_identity_field(self) -> None:
        component = (_SURFACE / "surfaces/chat/Composer.tsx").read_text(encoding="utf-8")
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

        self.assertIn("<ChatComposer", page)
        self.assertIn("sendMessageAction.bind(null, thread.threadId)", page)
        # the accepted row is drawn only while the thread read lacks its identity
        self.assertIn("const settled = thread.messages.map((message) => message.messageId);", page)
        self.assertIn("settled={settled}", page)
        self.assertIn("!settled.includes(state.message.messageId)", component)

    def test_the_unconfirmed_answer_has_its_own_render_and_its_own_retry(self) -> None:
        """Three answers, three renderings: sent, refused, and not yet confirmed."""
        component = (_SURFACE / "surfaces/chat/Composer.tsx").read_text(encoding="utf-8")
        action = (_SURFACE / "app/inbox/actions.ts").read_text(encoding="utf-8")

        # a refusal is an alert; an unconfirmed send is a status, not an error
        self.assertIn('role="status"', component)
        self.assertIn('role="alert"', component)
        # only an accepted answer draws the message row
        self.assertIn('state.kind === "sent"', component)
        self.assertIn('"Send again"', component)
        # still one field: the replay identity rides the previous answer, not a form input
        self.assertEqual(component.count('name="'), 1)

        # the send action reads the previous answer instead of discarding it,
        # and hands it to the one module that knows what to do with it
        self.assertIn("previous: InboxSendState", action)
        self.assertIn("sendInboxMessage(threadId,", action)
        self.assertIn(", previous)", action)

    def test_the_provenance_line_makes_no_read_only_claim_about_the_surface(self) -> None:
        """The foot names the instance it read, and claims nothing about authority.

        It used to carry a sentence naming the three server-authorized inbox
        paths on every screen in the app. The de-texting amendment retired it:
        the composer is a live control an operator can see and press, which is a
        better statement that this surface writes than a line of prose is, and
        the one control that *cannot* be honoured carries its own verdict.
        """
        foot = (_SURFACE / "frame/RecordFoot.tsx").read_text(encoding="utf-8")

        self.assertNotIn("read-only", foot)
        self.assertNotIn("no mutation path", foot)
        self.assertIn("recordAdapter.instance.baseUrl", foot)
        self.assertIn("recordAdapter.instance.posture", foot)


if __name__ == "__main__":
    unittest.main()
