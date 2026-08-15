"""What the dogfood Inbox surface renders and does, read out of a real browser.

Several of this boundary's claims are only true in a running browser.

The copy D41 clause 3 governs is not a fact about any one file. It is composed
at render time from a frame component, a rail constant and a screen, so a test
that greps those sources can pass while the page an operator looks at still
carries a retired claim.

The two write boxes' claims are stronger still: a message typed into one appears
— in the thread, or as the conversation it just started — *without a reload*.
That is a statement about one document's lifetime, and no source file can carry
it. D44 and D55 therefore permit this suite, and only this suite, to submit the
send and compose boxes from the browser. It stays a dogfood claim: the browser
posts to this server's own Server Action, receives no credential, and never
addresses a running instance.

The other half of each claim is the same statement inverted: a message the
record has *not* accepted must not appear as one. A `202`/`durability_pending`
answer carries the same identity, position and timestamp an accepted answer
does, so only a rendered page can show whether the surface drew a row anyway,
kept the sender's words, and retried under the identity the first attempt
minted.

The apparatus — the stub record source, the built and served surface, the
browser driver — is `_inbox_stub`. One build and one browser serve every
assertion below, so the drive happens once for the module rather than once per
class.

The promotion form is still never submitted here: its transport is proved
against the real module in ``tests/repository/test_inbox_promotion_ui``, the
send transport the same way in ``test_inbox_send_ui``, and the compose
transport in ``test_inbox_compose_ui``.

This is the one suite the D41/D42/D44/D55 dogfood exception activates. It is
deliberately outside ``tests/repository`` so the warm ``just check`` gate never
pays for a production build and a browser; the release gate runs it through the
expected-suite manifest.
"""

from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from dogfood import _inbox_stub as stub
else:
    from tests.dogfood import _inbox_stub as stub

__all__ = ()

_WIDTHS = stub.WIDTHS
_RETIRED_CLAIM = "no mutation path exists on this surface"
_NEW_TICKET_VERDICT = "cli only"
_NEW_TICKET_COMMAND = "ctowerctl ticket capture"
_UNCONFIRMED_SENTENCE = (
    "The server has not confirmed this message, so it is not sent yet. "
    "Press send again to send the same message."
)
# what the line under the box reads, chip included; the chip's own stylesheet
# upper-cases it on screen
_UNCONFIRMED_NOTICE = f"not confirmed {_UNCONFIRMED_SENTENCE}"
_UNCONFIRMED_COMPOSE_SENTENCE = (
    "The server has not confirmed this message, so the thread is not started yet. "
    "Press send again to send the same message."
)
_UNCONFIRMED_COMPOSE_NOTICE = f"not confirmed {_UNCONFIRMED_COMPOSE_SENTENCE}"
_SEND_FIELDS = ("text", "thread_id", "to")
_COMPOSE_FIELDS = ("text", "to")


class _Drive:
    """One build, one browser, one report — shared by every class below."""

    def __init__(self) -> None:
        self.stack = ExitStack()
        self.record = stub.Record()
        self.captures: list[dict[str, Any]] = []
        self.drives: list[dict[str, Any]] = []
        self.composes: list[dict[str, Any]] = []
        self.thread_source = ""

    def open(self) -> None:
        try:
            source = self.stack.enter_context(stub.record_stub(self.record))
            port = self.stack.enter_context(stub.dogfood_server(source))
            shots = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
            self.thread_source = stub.route_body(port, f"/inbox?thread={stub.THREAD_ID}") or ""
            report = stub.drive_surface(port, shots)
            self.captures = cast("list[dict[str, Any]]", report["captures"])
            self.drives = cast("list[dict[str, Any]]", report["drives"])
            self.composes = cast("list[dict[str, Any]]", report["composes"])
        except BaseException:
            self.stack.close()
            raise


_DRIVE = _Drive()


def setUpModule() -> None:
    _DRIVE.open()


def tearDownModule() -> None:
    _DRIVE.stack.close()


class InboxSurfaceRenderTests(unittest.TestCase):
    """Assertions about the rendered page and what it did, not about its sources."""

    captures: ClassVar[list[dict[str, Any]]] = []
    drives: ClassVar[list[dict[str, Any]]] = []
    record: ClassVar[stub.Record]
    thread_source: ClassVar[str] = ""

    def setUp(self) -> None:
        # one module-level build and browser answer every class here; binding
        # the report per test keeps each assertion on that one session
        type(self).captures = _DRIVE.captures
        type(self).drives = _DRIVE.drives
        type(self).record = _DRIVE.record
        type(self).thread_source = _DRIVE.thread_source

    def test_every_width_and_route_rendered(self) -> None:
        self.assertEqual(
            [(capture["route"], capture["width"]) for capture in self.captures],
            [(route, width) for width in _WIDTHS for route in ("list", "thread")],
        )

    def test_the_rendered_surface_makes_no_read_only_claim_at_all(self) -> None:
        """This surface writes, and nothing on it says otherwise any more.

        The foot used to carry an authority sentence on every screen and the
        rail called its inert action `read-only v1`. Both were app-wide claims
        about a surface whose composer sends a real message. What survives is
        narrower and true: one control ctower answers through its CLI instead.
        """
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                self.assertNotIn(_RETIRED_CLAIM, capture["rendered"])
                self.assertNotIn("read-only", capture["rendered"])
                self.assertNotIn("read-only", capture["foot"])

    def test_the_one_action_this_surface_cannot_take_shows_the_command_that_can(self) -> None:
        """De-texted: a disabled control, a two-word verdict, and the command.

        Round-3 QA (#240) got the reason printed under the button; the operator's
        de-texting amendment moved that sentence into the control's hover and put
        the thing that *does* work — the command itself — on the rail instead.
        """
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                affordance = cast("dict[str, Any]", capture["newTicket"])
                self.assertEqual(affordance["label"], "New ticket")
                self.assertTrue(affordance["disabled"])
                self.assertEqual(affordance["verdict"], _NEW_TICKET_VERDICT)
                self.assertEqual(affordance["command"], _NEW_TICKET_COMMAND)
                # the caveat is reachable, and it is not on the screen
                self.assertNotEqual(affordance["reason"], "")
                self.assertNotIn(affordance["reason"], capture["visible"])

    def test_the_surface_rendered_the_recorded_threads_and_both_controls(self) -> None:
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                # the provenance rule holds on the workspace too: the instance
                # and the origin it was read from, on every route and width
                self.assertIn(f"ctower · {stub.INSTANCE_LABEL} instance", capture["foot"])
                if capture["route"] == "list":
                    # the conversation column carries the record's own preview
                    self.assertIn(stub.PREVIEW, capture["visible"])
                else:
                    # the transcript carries the message the preview came from
                    self.assertIn(stub.PREVIEW, capture["visible"])
                    # the link control, which fills the work pane beside the
                    # conversation, and the reply box under it
                    self.assertIn("new ticket from this conversation", capture["rendered"])
                    # the transcript names whose turn it is once per group,
                    # rather than repeating from/to on every message row
                    self.assertIn(stub.OTHER_SEAT, capture["visible"])
                    # who a reply goes out as is a chip, not a sentence about
                    # authority; the seat is its own element inside it, so the
                    # words are read with their layout whitespace collapsed
                    self.assertIn(
                        f"as {stub.SELF_SEAT}",
                        " ".join(cast("str", capture["visible"]).split()),
                    )

    def test_the_transcript_draws_the_records_own_delivery_marks(self) -> None:
        """The approved chat surface marks every message sent / delivered / read.

        These are three recorded events with their own ids, served by
        `/v1/inbox/threads/{id}/read-state` — not something derivable from the
        thread read's cursor. They are also composed at render time from a
        separate read, so only a browser can show whether the marks arrived: a
        surface whose delivery read quietly 404s still renders every message,
        just without the truth on it.
        """
        for capture in self.captures:
            if capture["route"] != "thread":
                continue
            with self.subTest(width=capture["width"]):
                marks = cast("list[dict[str, Any]]", capture["delivery"])
                self.assertEqual(
                    len(marks), 1, "the transcript drew no delivery mark for its one message"
                )
                mark = marks[0]
                # the record says this message was read, so all three dots fill
                self.assertEqual(mark["filled"], 3)
                # the dots are the element; the exact times are their hover
                self.assertIn("sent ", mark["title"])
                self.assertIn("delivered ", mark["title"])
                self.assertIn("read ", mark["title"])
                self.assertNotIn("not recorded", mark["title"])
                # and none of those timestamps is on the screen as prose
                self.assertNotIn(mark["title"], capture["visible"])

    def test_the_thread_head_teaches_the_three_marks_once(self) -> None:
        """One legend, in the head — the approved surface's own placement."""
        for capture in self.captures:
            if capture["route"] != "thread":
                continue
            with self.subTest(width=capture["width"]):
                legend = cast("str", capture["legend"])
                for state in ("sent", "delivered", "read"):
                    self.assertIn(state, legend)

    def test_a_typed_message_appears_in_the_thread_without_a_reload(self) -> None:
        """The claim the send box exists to make, made in a browser at every width.

        The stub's thread read lags one read behind its accepted commands, the
        way a folded projection lags a committed event. So the row that shows
        up in the submitting document can only have come from the command's own
        answer, and it carries the marker that says so.
        """
        sends = [drive for drive in self.drives if drive["outcome"] == "sent"]
        self.assertEqual([drive["width"] for drive in sends], list(_WIDTHS))
        for drive in sends:
            with self.subTest(width=drive["width"]):
                self.assertIn(drive["typed"], drive["messages"])
                self.assertEqual(drive["unfolded"], [drive["typed"]])
                self.assertTrue(drive["sameDocument"])
                self.assertEqual(drive["fieldAfter"], "")
                self.assertEqual(drive["button"], "Send")

    def test_the_projection_takes_the_message_over_and_the_marker_goes_away(self) -> None:
        """One message, never two: the row is the command's until the read has it."""
        for drive in (item for item in self.drives if item["outcome"] == "sent"):
            with self.subTest(width=drive["width"]):
                reloaded = cast("list[str]", drive["messagesReloaded"])
                self.assertIn(drive["typed"], reloaded)
                self.assertEqual(reloaded.count(drive["typed"]), 1)
                self.assertEqual(drive["unfoldedReloaded"], [])

    def test_a_non_accepted_answer_is_never_rendered_as_a_sent_message(self) -> None:
        """`202`/`durability_pending` is the record saying it has not accepted.

        Its answer carries the same message identity, position and timestamp an
        accepted one does, so a surface that reads the envelope instead of the
        discriminator shows an unkept message as a recorded fact. Here the row
        is not drawn at all: the words stay in the box, and the box says the
        server has not confirmed them.
        """
        held = [drive for drive in self.drives if drive["outcome"] == "unconfirmed"]
        self.assertEqual([drive["width"] for drive in held], list(_WIDTHS))
        for drive in held:
            with self.subTest(width=drive["width"]):
                self.assertNotIn(drive["typed"], drive["messages"])
                self.assertEqual(drive["unfolded"], [])
                self.assertEqual(drive["notice"], _UNCONFIRMED_NOTICE)
                self.assertEqual(drive["refusal"], "")
                # the draft survives, and the control names the retry it offers
                self.assertEqual(drive["fieldAfter"], drive["typed"])
                self.assertEqual(drive["button"], "Send again")
                self.assertTrue(drive["sameDocument"])
                self.assertNotIn(drive["typed"], drive["messagesReloaded"])

    def test_the_retry_of_an_unconfirmed_send_reuses_one_command_identity(self) -> None:
        """Pressing the box again replays one command; it does not send a second."""
        for drive in (item for item in self.drives if item["outcome"] == "unconfirmed"):
            with self.subTest(width=drive["width"]):
                retried = cast("dict[str, Any]", drive["retried"])
                self.assertEqual(retried["notice"], _UNCONFIRMED_NOTICE)
                self.assertEqual(retried["fieldAfter"], drive["typed"])
                self.assertEqual(retried["button"], "Send again")
                self.assertNotIn(drive["typed"], retried["messages"])

        keys = [
            command["idempotency_key"]
            for command in self.record.commands
            if str(cast("dict[str, Any]", command["payload"])["thread_id"])
            == stub.UNCONFIRMED_THREAD_ID
        ]
        self.assertEqual(len(keys), len(_WIDTHS) * 2)
        self.assertEqual(len(set(keys)), len(_WIDTHS))
        for first, second in zip(keys[::2], keys[1::2], strict=True):
            self.assertEqual(first, second)

    def test_the_command_carried_the_message_and_no_claimed_identity(self) -> None:
        commands = self.record.commands
        # one accepted send, one refused send, and two attempts at one
        # unconfirmed send, at each width
        self.assertEqual(len(commands), len(_WIDTHS) * 4)
        keys = [command["idempotency_key"] for command in commands]
        self.assertEqual(len(set(keys)), len(_WIDTHS) * 3)
        for command in commands:
            payload = cast("dict[str, Any]", command["payload"])
            with self.subTest(text=payload.get("text")):
                self.assertEqual(tuple(sorted(payload)), _SEND_FIELDS)
                self.assertIn(
                    payload["to"], (stub.OTHER_SEAT, stub.STRANGER_SEAT, stub.UNDURABLE_SEAT)
                )
                self.assertRegex(cast("str", command["idempotency_key"]), r"^[0-9a-f-]{36}$")

    def test_a_refused_send_renders_the_servers_own_sentence(self) -> None:
        refusals = [drive for drive in self.drives if drive["outcome"] == "refused"]
        self.assertEqual([drive["width"] for drive in refusals], list(_WIDTHS))
        for drive in refusals:
            with self.subTest(width=drive["width"]):
                self.assertEqual(drive["refusal"], f"refused {stub.REFUSAL_DETAIL}")
                self.assertNotIn(drive["typed"], drive["messages"])
                self.assertNotIn(drive["typed"], drive["messagesReloaded"])
                self.assertTrue(drive["sameDocument"])
                # the words survive the refusal: nobody retypes a rejected send
                self.assertEqual(drive["fieldAfter"], drive["typed"])
                # a refused command has no identity to replay, so this is a fresh send
                self.assertEqual(drive["button"], "Send")

    def test_the_served_document_carries_no_credential(self) -> None:
        """D41 clause 1: the browser receives no bearer, in markup or in props."""
        self.assertIn(stub.THREAD_ID, self.thread_source)
        self.assertNotIn(stub.CREDENTIAL, self.thread_source)
        self.assertNotIn("Bearer", self.thread_source)


class InboxComposeRenderTests(unittest.TestCase):
    """What the compose box put on the screen, and what it refused to put there."""

    composes: ClassVar[list[dict[str, Any]]] = []
    record: ClassVar[stub.Record]

    def setUp(self) -> None:
        type(self).composes = _DRIVE.composes
        type(self).record = _DRIVE.record

    def test_the_compose_picker_offers_the_records_own_closed_world(self) -> None:
        """The dropdown rule, in a browser: the seats are the record's, verbatim.

        Every seat the record listed is offered and nothing else is, so the
        operator cannot type an address at all — the only way to name one is to
        pick one the server itself answered with.
        """
        for compose in self.composes:
            with self.subTest(width=compose["width"], outcome=compose["outcome"]):
                self.assertEqual(compose["seats"], list(stub.ADDRESSABLE))
                self.assertIn(stub.COMPOSE_SEAT, compose["seats"])

    def test_composing_starts_the_thread_in_the_same_document(self) -> None:
        """The claim the compose box exists to make, made in a browser.

        The seat picked here had no thread with this principal at all, so the
        row that appears can only have come from the command's own answer — the
        thread projection has nothing to give yet. The stamp says the document
        never reloaded, and the panel names the thread the record derived.
        """
        started = [item for item in self.composes if item["outcome"] == "started"]
        self.assertEqual([item["width"] for item in started], list(_WIDTHS))
        for compose in started:
            with self.subTest(width=compose["width"]):
                self.assertEqual(compose["composed"], [compose["typed"]])
                self.assertTrue(compose["sameDocument"])
                self.assertEqual(compose["fieldAfter"], "")
                self.assertEqual(compose["seatAfter"], "")
                self.assertEqual(compose["button"], "Send")
                self.assertEqual(compose["refusal"], "")
                self.assertEqual(compose["notice"], "")
                # the row is the compose panel's own; the list did not have it
                self.assertNotIn(compose["typed"], compose["listed"])
                self.assertIn(f"thread={stub.COMPOSED_THREAD_ID}", compose["opened"])

    def test_the_started_thread_is_readable_and_joins_the_list(self) -> None:
        """What the panel drew and what the record holds end up the same thing.

        The row in the panel came from the command's answer; the thread and the
        list come from the projection. The whole idiom is only honest if those
        two agree once the projection has folded — so the thread is re-read in
        a fresh document, and the Inbox list gains the conversation that was
        not there before.
        """
        seeded = 3
        for compose in (item for item in self.composes if item["outcome"] == "started"):
            with self.subTest(width=compose["width"]):
                self.assertIn(compose["typed"], compose["threadMessages"])
                self.assertEqual(compose["threadMessages"].count(compose["typed"]), 1)
                self.assertEqual(len(compose["listedReloaded"]), seeded + 1)

    def test_composing_twice_never_opens_a_second_thread(self) -> None:
        """One correspondent, one conversation — the pair-grouped guarantee.

        Each width composes to the same seat, and every one of them lands in
        the thread the first opened. A control that minted a thread per send
        would scatter one correspondent's conversation across three.
        """
        opened = {item["opened"] for item in self.composes if item["outcome"] == "started"}
        self.assertEqual(len(opened), 1)
        last = [item for item in self.composes if item["outcome"] == "started"][-1]
        self.assertEqual(len(last["threadMessages"]), len(_WIDTHS))

    def test_a_compose_the_record_has_not_confirmed_starts_no_thread(self) -> None:
        """`202`/`durability_pending` is the record saying it has not accepted.

        Its answer carries a thread identity, a message identity and a position,
        so a surface reading the envelope instead of the discriminator would
        tell the operator they have a conversation nobody promised to keep.
        Here no row is drawn, the words and the picked seat both survive, and
        the box says so.
        """
        held = [item for item in self.composes if item["outcome"] == "unconfirmed"]
        self.assertEqual([item["width"] for item in held], list(_WIDTHS))
        for compose in held:
            with self.subTest(width=compose["width"]):
                self.assertEqual(compose["composed"], [])
                self.assertEqual(compose["opened"], "")
                self.assertEqual(compose["notice"], _UNCONFIRMED_COMPOSE_NOTICE)
                self.assertEqual(compose["refusal"], "")
                self.assertEqual(compose["fieldAfter"], compose["typed"])
                self.assertEqual(compose["seatAfter"], stub.UNDURABLE_SEAT)
                self.assertEqual(compose["button"], "Send again")
                self.assertTrue(compose["sameDocument"])
                self.assertNotIn(compose["typed"], compose["listedReloaded"])

    def test_a_refused_compose_renders_the_servers_own_sentence(self) -> None:
        refusals = [item for item in self.composes if item["outcome"] == "refused"]
        self.assertEqual([item["width"] for item in refusals], list(_WIDTHS))
        for compose in refusals:
            with self.subTest(width=compose["width"]):
                self.assertEqual(compose["refusal"], f"refused {stub.REFUSAL_DETAIL}")
                self.assertEqual(compose["composed"], [])
                self.assertEqual(compose["notice"], "")
                # the words and the seat survive the refusal
                self.assertEqual(compose["fieldAfter"], compose["typed"])
                self.assertEqual(compose["seatAfter"], stub.STRANGER_SEAT)
                # a refused command has no identity to replay: this is a fresh send
                self.assertEqual(compose["button"], "Send")
                self.assertNotIn(compose["typed"], compose["listedReloaded"])

    def test_the_compose_command_carried_a_listed_seat_and_no_claimed_identity(self) -> None:
        composes = self.record.composes
        # one accepted, one refused and one unconfirmed compose, at each width
        self.assertEqual(len(composes), len(_WIDTHS) * 3)
        keys = [command["idempotency_key"] for command in composes]
        self.assertEqual(len(set(keys)), len(composes))
        for command in composes:
            payload = cast("dict[str, Any]", command["payload"])
            with self.subTest(text=payload.get("text")):
                # no sender, and no thread: the server derives both
                self.assertEqual(tuple(sorted(payload)), _COMPOSE_FIELDS)
                self.assertIn(payload["to"], stub.ADDRESSABLE)
                self.assertRegex(cast("str", command["idempotency_key"]), r"^[0-9a-f-]{36}$")


if __name__ == "__main__":
    unittest.main()
