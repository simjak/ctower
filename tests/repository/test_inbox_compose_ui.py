"""The Inbox compose box opens a thread to a seat the record itself listed."""

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
_SURFACE = _ROOT / "apps/ctower-ui/src"
_FIXTURE = Path(__file__).with_name("inbox_compose_fixtures.ts")
_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000600"
_EXPECTED_BODY = '{"text":"open the conversation","to":"director"}'
_UNCONFIRMED_SENTENCE = (
    "The server has not confirmed this message, so the thread is not started yet. "
    "Press Retry to send the same message again."
)
_UNLISTED_SENTENCE = (
    "That seat is not one the record lists, so nothing was sent. "
    "Pick a seat from the list and try again."
)
_LOST_REPLAY_SENTENCE = (
    "This retry lost track of the message waiting for confirmation. "
    "Reload the page and send it again."
)


class InboxComposeTransportTests(unittest.TestCase):
    def test_the_command_carries_only_the_message_and_a_server_listed_seat(self) -> None:
        """The browser names a listed address, never a sender and never a thread.

        A compose has no thread to bind and no correspondent to read back, so
        the recipient is chosen. What makes that safe is where the choices came
        from: the server's own registered-seat list is read again at submit
        time and the chosen seat is checked against it, so this path can carry
        an address the record listed and nothing else. The thread is not on the
        wire at all — the server derives one per seat pair.
        """
        outcomes = ts.drive(_FIXTURE)
        attempts = cast("list[dict[str, Any]]", outcomes["accepted"])
        success = cast("dict[str, Any]", outcomes["success"])

        self.assertEqual([attempt["method"] for attempt in attempts], ["GET", "POST"])
        self.assertTrue(attempts[0]["url"].endswith("/v1/inbox/correspondents"))
        self.assertTrue(attempts[1]["url"].endswith("/v1/inbox/notifications"))
        self.assertEqual(attempts[1]["bodyKeys"], ["text", "to"])
        self.assertEqual(attempts[1]["body"], _EXPECTED_BODY)
        self.assertRegex(cast("str", attempts[1]["idempotencyKey"]), r"^[0-9a-f-]{36}$")
        self.assertTrue(attempts[1]["authorized"])
        self.assertIsNone(attempts[0]["idempotencyKey"])

        self.assertEqual(
            success,
            {
                "kind": "started",
                "threadId": _THREAD_ID,
                "message": {
                    "messageId": "018f0d5e-7b9a-7c01-8000-000000000702",
                    "position": 1,
                    "from": "ctower-commander",
                    "to": "director",
                    "text": "open the conversation",
                    "sentAt": "2026-08-09T03:05:00Z",
                },
            },
        )

    def test_a_seat_the_record_does_not_list_reaches_no_boundary_at_all(self) -> None:
        """The picker's closed world is enforced, not merely displayed.

        The dropdown is what an operator sees, but it is not what makes this
        path closed: a submission naming any other seat is refused here, before
        a command exists, so no browser can address an identity the record did
        not list.
        """
        outcomes = ts.drive(_FIXTURE)
        stranger = cast("dict[str, Any]", outcomes["stranger"])
        unpicked = cast("dict[str, Any]", outcomes["unpicked"])
        blank = cast("dict[str, Any]", outcomes["blank"])

        self.assertEqual(stranger["kind"], "refused")
        self.assertEqual(stranger["message"], _UNLISTED_SENTENCE)
        self.assertEqual(stranger["text"], "hello?")
        self.assertEqual(
            [attempt["method"] for attempt in cast("list[Any]", outcomes["strangerAttempts"])],
            ["GET"],
        )

        self.assertEqual(unpicked["kind"], "refused")
        self.assertEqual(unpicked["message"], "Pick the seat this message is for.")
        self.assertEqual(cast("list[Any]", outcomes["unpickedAttempts"]), [])

        self.assertEqual(blank["kind"], "refused")
        self.assertEqual(blank["message"], "Write a message before sending.")
        self.assertEqual(cast("list[Any]", outcomes["blankAttempts"]), [])

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
        # a refusal costs the operator neither their words nor their chosen seat
        self.assertEqual(refusal["text"], "who am I here?")
        self.assertEqual(refusal["to"], "director")
        self.assertEqual(opaque["kind"], "refused")
        self.assertEqual(
            opaque["message"], "The server refused the message without a usable explanation."
        )

    def test_a_retryable_status_reuses_the_one_minted_idempotency_key(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        retried = cast("dict[str, Any]", outcomes["retried"])
        keys = cast("list[str]", outcomes["retryKeys"])

        self.assertEqual(retried["kind"], "started")
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])
        self.assertRegex(keys[0], r"^[0-9a-f-]{36}$")


class InboxComposeDurabilityTests(unittest.TestCase):
    """An answer that says it is not accepted does not become a conversation.

    ``202``/``durability_pending`` carries the same thread identity, message
    identity, position and timestamp the accepted answer does. Drawing a
    started thread from it would tell the operator they have a conversation the
    record has not promised to keep.
    """

    def test_a_non_accepted_answer_is_not_read_as_a_started_thread(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        held = cast("dict[str, Any]", outcomes["held"])
        keys = cast("list[str]", outcomes["heldKeys"])

        self.assertEqual(held["kind"], "pending")
        self.assertNotIn("message_id", str(held))
        self.assertNotIn("threadId", held)
        self.assertEqual(held["message"], _UNCONFIRMED_SENTENCE)
        # the words are the sender's until the record says otherwise, spaces and all
        self.assertEqual(held["text"], "  is this recorded?  ")
        self.assertEqual(held["to"], "director")
        self.assertEqual(len(keys), 1)
        self.assertEqual(held["commandId"], keys[0])

    def test_the_retry_of_an_unconfirmed_compose_carries_its_command_identity(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        unresolved = cast("dict[str, Any]", outcomes["unresolved"])
        resolved = cast("dict[str, Any]", outcomes["resolved"])
        keys = cast("list[str]", outcomes["replayKeys"])

        self.assertEqual(unresolved["kind"], "pending")
        self.assertEqual(resolved["kind"], "started")
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[0], unresolved["commandId"])

    def test_the_same_words_to_another_seat_are_a_new_command(self) -> None:
        """One key for two different requests is a conflict, not a retry."""
        outcomes = ts.drive(_FIXTURE)
        keys = cast("list[str]", outcomes["readdressedKeys"])
        readdressed = cast("dict[str, Any]", outcomes["readdressed"])

        self.assertEqual(readdressed["kind"], "pending")
        self.assertEqual(readdressed["to"], "engineer")
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0], keys[1])
        self.assertEqual(keys[1], readdressed["commandId"])

    def test_an_unreadable_replay_identity_reaches_no_boundary_at_all(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        forged = cast("dict[str, Any]", outcomes["forged"])

        self.assertEqual(forged["kind"], "refused")
        self.assertEqual(forged["message"], _LOST_REPLAY_SENTENCE)
        self.assertEqual(forged["text"], "tampered state")
        self.assertEqual(cast("list[Any]", outcomes["forgedAttempts"]), [])


class InboxComposeComponentTests(unittest.TestCase):
    def test_the_compose_box_offers_a_closed_list_and_holds_no_credential(self) -> None:
        component = (_SURFACE / "surfaces/inbox/ComposeThread.tsx").read_text(encoding="utf-8")
        action = (_SURFACE / "app/inbox/actions.ts").read_text(encoding="utf-8")
        page = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")

        self.assertIn('"use client"', component)
        self.assertIn("useActionState", component)
        self.assertNotIn("fetch(", component)
        self.assertNotIn("Authorization", component)
        # two fields, and neither is an identity: the seat is picked from the
        # server's own list, and there is no sender or thread input at all
        self.assertEqual(component.count('name="'), 2)
        self.assertIn('name="to"', component)
        self.assertIn('name="text"', component)
        self.assertNotIn('name="from"', component)
        self.assertNotIn('name="thread', component)
        # a dropdown over the server's list, never a typed-in address
        self.assertIn("<select", component)
        self.assertIn("correspondents.choices", component)
        self.assertNotIn('type="text"', component)

        self.assertIn('"use server"', action)
        self.assertIn("composeInboxThread(", action)
        self.assertIn('revalidatePath("/inbox")', action)

        self.assertIn("<ComposeThread", page)
        self.assertIn("action={composeThreadAction}", page)
        self.assertIn("recordAdapter.inboxCorrespondents()", page)

    def test_three_answers_get_three_renderings_and_the_pending_one_retries(self) -> None:
        component = (_SURFACE / "surfaces/inbox/ComposeThread.tsx").read_text(encoding="utf-8")

        # a refusal is an alert; an unconfirmed compose is a status, not an error
        self.assertIn('role="status"', component)
        self.assertIn('role="alert"', component)
        # only an accepted answer draws the message row and offers the thread
        self.assertIn('state.kind === "started"', component)
        self.assertIn("state.threadId", component)
        self.assertIn('"Retry"', component)
        # an empty closed world does not invite a compose it cannot honor
        self.assertIn("seats.length === 0", component)
        self.assertIn("disabled={idle}", component)

    def test_the_offered_list_is_the_records_own_and_an_empty_one_says_which(self) -> None:
        """The browser never edits the list, and never guesses why it is empty.

        The read already answers with the addresses the command accepts, so
        folding, filtering or supplementing them here could only make the picker
        disagree with the command it exists to reach. And an empty list has two
        different causes — nobody addressable to write to, or no seat of this
        principal's own to write from — which get two different sentences,
        because naming the wrong one tells the operator to fix the wrong thing.
        """
        component = (_SURFACE / "surfaces/inbox/ComposeThread.tsx").read_text(encoding="utf-8")

        self.assertIn("correspondents.choices.map", component)
        self.assertNotIn("new Set", component)
        self.assertNotIn("choices.filter", component)
        self.assertIn('"unaddressable"', component)
        self.assertIn("no registered seat", component)
        self.assertIn("no other seat this server can write to", component)

    def test_a_control_this_surface_switched_off_is_drawn_switched_off(self) -> None:
        """A dead control that looks live is an invitation the page cannot honor.

        The compose box disables its picker, its field and its button whenever
        there is no address to send to or a send is in flight, and until now
        nothing in the design system drew that state differently from a live
        one. The rule belongs to the shared field and button rather than to this
        box, so every switched-off control on the surface reads as one.
        """
        stylesheet = (_ROOT / "apps/ctower-ui/design-reference/app.css").read_text(encoding="utf-8")

        for rule in (".field:disabled", ".btn:disabled"):
            with self.subTest(rule=rule):
                match = re.search(rf"{re.escape(rule)}[^{{]*\{{([^}}]+)\}}", stylesheet)
                self.assertIsNotNone(match, f"{rule} has no shared style rule")
                assert match is not None
                self.assertIn("cursor: not-allowed", match.group(1))
                self.assertIn("var(--ink-3)", match.group(1))

    def test_the_control_is_on_the_list_screen_where_no_thread_exists_yet(self) -> None:
        """A new thread starts where there is no thread: the Inbox list."""
        page = (_SURFACE / "app/inbox/page.tsx").read_text(encoding="utf-8")
        list_screen, thread_screen = page.split("function InboxThreadBody", maxsplit=1)

        self.assertIn("<ComposeThread", list_screen)
        self.assertNotIn("<ComposeThread", thread_screen)


if __name__ == "__main__":
    unittest.main()
