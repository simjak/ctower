"""Semantic regressions for the four read-layer defects round-3 QA drove live.

Each screen below showed the operator a number or a verdict its sources did not
support, and in every case the decision behind it is a pure function on values.
`surface_fixtures.ts` executes those functions against the values the live
sources produce; these tests assert on what they concluded.

Run against the tree as QA found it, every test in this file fails.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_FIXTURE = Path(__file__).with_name("surface_fixtures.ts")
_OUTCOMES: dict[str, Any] = {}


def _outcomes() -> dict[str, Any]:
    if not _OUTCOMES:
        _OUTCOMES.update(ts.drive(_FIXTURE))
    return _OUTCOMES


def _case(name: str) -> dict[str, Any]:
    case = _outcomes()[name]
    if not isinstance(case, dict):
        raise TypeError(f"surface case {name} is not an object")
    return cast("dict[str, Any]", case)


class ModuleCopyTests(unittest.TestCase):
    """The driver must run the shipped modules, not an edited stand-in."""

    def test_the_copy_changes_only_import_specifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            ts.materialize(tree)
            surface = ts.ROOT / ts.SURFACE
            copied = sorted(
                path for path in (tree / ts.SURFACE).rglob("*") if path.suffix in (".ts", ".tsx")
            )
            self.assertGreater(len(copied), 10, "the surface copy found almost nothing")
            for path in copied:
                original = surface / path.relative_to(tree / ts.SURFACE)
                self.assertEqual(
                    ts.without_specifiers(original.read_text(encoding="utf-8")),
                    ts.without_specifiers(path.read_text(encoding="utf-8")),
                    f"{path.name} was changed outside its import lines",
                )

    def test_every_relative_specifier_in_the_copy_names_a_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            ts.materialize(tree)
            dangling = [
                f"{path.name} -> {specifier}"
                for path in sorted((tree / ts.SURFACE).rglob("*.ts"))
                for specifier in ts.specifiers(path.read_text(encoding="utf-8"))
                if specifier.startswith(".") and not (path.parent / specifier).exists()
            ]
            self.assertEqual(dangling, [], "the rewritten copy points at files that do not exist")


class DiffBaseTests(unittest.TestCase):
    """#236 — a diff is only as honest as the base it is measured from."""

    def test_a_remote_tracking_trunk_beats_the_local_ref(self) -> None:
        for name in ("baseChoosesTheRemoteTrunk", "baseIgnoresProbeOrder"):
            with self.subTest(case=name):
                base = _case(name)
                self.assertEqual(
                    base["ref"],
                    {"known": "value", "value": "origin/main"},
                    "the surface measured against a local ref while the trunk was available",
                )
                self.assertEqual(base["head"], {"known": "value", "value": "3a5e87ce"})
                self.assertIn("origin/main", base["note"])

    def test_the_chosen_base_carries_its_own_commit(self) -> None:
        base = _case("baseChoosesTheRemoteTrunk")
        self.assertEqual(
            base["head"]["known"],
            "value",
            "the base was chosen without resolving it, so its age cannot be shown",
        )

    def test_a_local_only_checkout_is_used_and_labelled_as_possibly_behind(self) -> None:
        base = _case("baseFallsBackToLocalAndSaysSo")
        self.assertEqual(base["ref"], {"known": "value", "value": "main"})
        self.assertIn("local ref", base["note"])
        self.assertIn("behind", base["note"], "a stale base was used without saying so")

    def test_no_resolvable_base_is_unread_rather_than_a_clean_tree(self) -> None:
        for name in ("baseWithNothingResolvedIsUnread", "baseWithNoProbesIsUnread"):
            with self.subTest(case=name):
                base = _case(name)
                self.assertEqual(base["ref"]["known"], "unread")
                self.assertEqual(base["head"]["known"], "unread")


class CrewProjectTests(unittest.TestCase):
    """#237 — the roster already reads tmux; it may not ignore what tmux holds."""

    def test_a_session_tag_answers_when_the_crew_log_is_silent(self) -> None:
        self.assertEqual(
            _case("projectFromTheSessionTagWhenTheLogIsSilent"),
            {"known": "value", "value": "ctower"},
            "a crew with a tagged session was filed under 'project not recorded'",
        )

    def test_the_crew_log_wins_when_it_recorded_a_project(self) -> None:
        self.assertEqual(
            _case("projectFromTheLogWhenItRecordedOne"),
            {"known": "value", "value": "manibo"},
        )

    def test_a_tag_answers_even_when_the_crew_log_could_not_be_read(self) -> None:
        self.assertEqual(
            _case("projectFromTheTagWhenTheLogIsUnreadable"),
            {"known": "value", "value": "bh-loop"},
        )

    def test_neither_source_recording_one_stays_not_recorded(self) -> None:
        for name in ("projectNotRecordedWhenNeitherHasOne", "projectNotRecordedForAnEmptyTag"):
            with self.subTest(case=name):
                case = _case(name)
                self.assertEqual(case["known"], "none")
                self.assertEqual(case["why"], "not recorded")

    def test_an_unreadable_log_with_no_tag_stays_unread_not_empty(self) -> None:
        self.assertEqual(
            _case("projectStaysUnreadWhenNothingAnswered")["known"],
            "unread",
            "a failed read was rendered as a recorded absence",
        )

    def test_a_missing_log_file_is_an_answer_not_a_failure(self) -> None:
        self.assertEqual(_case("projectNotRecordedWhenThereIsNoLogFile")["known"], "none")


class SessionPayloadTests(unittest.TestCase):
    """A legal null in one row must not cost every row its panel."""

    def test_every_nullable_session_field_reads_as_its_own_absence(self) -> None:
        session = _case("sessionWithEveryNullableNulled")
        self.assertIsNone(session["outcome"])
        self.assertIsNone(session["closedAt"])
        self.assertIsNone(session["durationSeconds"])
        self.assertIsNone(session["evidenceRef"])
        # tokens is the nullable *object*: an absence, not a refusal
        self.assertEqual(session["inputTokens"], 0)
        self.assertEqual(session["outputTokens"], 0)
        self.assertEqual(session["totalTokens"], 0)
        # the row still carries everything the record did state
        self.assertEqual(session["crewName"], "designer-r2988-ctower-ui")
        self.assertEqual(session["state"], "working")

    def test_recorded_usage_is_read_field_by_field(self) -> None:
        session = _case("sessionWithRecordedTokens")
        self.assertEqual(session["inputTokens"], 1200)
        self.assertEqual(session["outputTokens"], 340)
        self.assertEqual(session["totalTokens"], 1540)
        self.assertEqual(session["outcome"], "delivered")
        self.assertEqual(session["durationSeconds"], 3600)

    def test_one_unrecorded_usage_does_not_blank_the_rows_beside_it(self) -> None:
        rows = _outcomes()["sessionsMixedNullAndRecorded"]
        self.assertEqual(
            [row["totalTokens"] for row in rows],
            [0, 11],
            "a session with no recorded usage took the recorded one down with it, which is "
            "how one legal row blanked both session panels",
        )

    def test_a_malformed_usage_object_is_still_refused(self) -> None:
        self.assertTrue(
            _outcomes()["malformedTokensRefused"],
            "the null branch was widened into a catch-all, so a malformed usage object now "
            "defaults to zeroes instead of refusing",
        )


class ChatStreamTests(unittest.TestCase):
    """#242 — the chat view is the readable one, or the toggle is decorative."""

    def test_status_lines_do_not_become_turns(self) -> None:
        turns = _outcomes()["chatTurns"]
        self.assertEqual(
            _outcomes()["chatTurnCount"],
            2,
            "the session's own spinner ticks were promoted to bubbles of their own",
        )
        self.assertEqual(_outcomes()["chatStatusLineCount"], 3)
        for turn in turns:
            self.assertNotEqual(turn["body"], [], "a turn was rendered with no content in it")

    def test_status_lines_attach_to_the_turn_they_interrupt(self) -> None:
        turns = _outcomes()["chatTurns"]
        self.assertEqual(len(turns[0]["notes"]), 2)
        self.assertEqual(len(turns[1]["notes"]), 1)

    def test_a_status_line_before_any_turn_still_makes_no_bubble(self) -> None:
        turns = _outcomes()["chatLeadingStatus"]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["notes"], ["✻ Churned for 4s"])

    def test_a_tool_block_is_still_collected_as_a_tool(self) -> None:
        turns = _outcomes()["chatTurns"]
        self.assertEqual(turns[1]["tools"], ["Ran 1 shell command"])

    def test_the_panes_left_padding_is_removed_and_only_that(self) -> None:
        self.assertEqual(
            _outcomes()["unindentStripsOnlyTheSharedPadding"],
            ["a line", "    an indented quote", "another line"],
        )
        self.assertEqual(
            _outcomes()["unindentLeavesAnUnpaddedBodyAlone"],
            ["a line", "  a quote"],
        )

    def test_a_turn_body_is_one_line_per_paragraph(self) -> None:
        turns = _outcomes()["chatTurns"]
        for turn in turns:
            for line in turn["body"]:
                self.assertFalse(line.startswith(" "), "the pane's padding survived into a bubble")
        self.assertEqual(
            len(turns[0]["body"]),
            1,
            "a paragraph the session wrapped over two lines reached the bubble as two lines, "
            "so the terminal's column re-wraps inside a 370px bubble (#242)",
        )
        self.assertIn("A generated file", turns[0]["body"][0])
        self.assertIn("inventory under docs", turns[0]["body"][0])

    def test_the_rejoin_only_continues_a_line_that_reached_the_wrap_column(self) -> None:
        self.assertEqual(len(_outcomes()["rejoinsAWrappedLine"]), 1)
        self.assertEqual(
            _outcomes()["leavesAShortLineAlone"],
            ["a short line.", "a new paragraph."],
            "a paragraph that simply ended was glued to the next one",
        )
        self.assertEqual(len(_outcomes()["rejoinKeepsABlankLineAsABreak"]), 3)

    def test_a_stream_that_reports_no_width_is_left_as_captured(self) -> None:
        self.assertEqual(
            len(_outcomes()["rejoinsNothingWithoutAWidth"]),
            2,
            "lines were rejoined against a wrap column nobody reported",
        )


class RefusalStatusTests(unittest.TestCase):
    """An empty board and a board you are not allowed to see must never match."""

    def test_a_refusal_carries_its_status_through_the_retry_loop(self) -> None:
        self.assertEqual(
            _case("refusalKeepsItsStatus")["status"],
            401,
            "the status was dropped folding a built failure back into a classification, so a "
            "401 reaches the screen as a generic 'the record was not reached' block and the "
            "operator cannot tell a refusal from an outage",
        )

    def test_a_failure_with_no_status_does_not_acquire_one(self) -> None:
        self.assertNotIn("status", _case("failureWithNoStatusStaysWithout"))


class BoardCardContextTests(unittest.TestCase):
    """#337 — the five API-present context members must reach the card."""

    def test_the_qa_fixture_keeps_all_five_context_members_visible(self) -> None:
        context = _case("boardCardContextSet")
        self.assertEqual(context["tenant"]["value"], "Ctower")
        self.assertEqual(
            context["changes"][0]["value"],
            "simjak/ctower #326 · https://github.com/simjak/ctower/pull/326",
        )
        self.assertEqual(context["labels"][0]["value"], "Visual gate")
        self.assertEqual(
            context["humanWaiting"]["value"],
            "needs_visual_qa · vision_path_deferred",
        )
        self.assertEqual(context["deliverySurface"]["value"], "no qualifying checkpoint")

    def test_empty_or_unavailable_members_are_explicit_instead_of_omitted(self) -> None:
        context = _case("boardCardExplicitEmptyContextSet")
        self.assertEqual(context["tenant"]["value"], "STATE_UNKNOWN · tenant.display_name")
        self.assertEqual(context["changes"], [{"value": "none recorded"}])
        self.assertEqual(context["labels"], [{"value": "none applied"}])
        self.assertEqual(context["humanWaiting"]["value"], "not waiting")
        self.assertEqual(context["deliverySurface"]["value"], "no qualifying checkpoint")


class TicketBarTests(unittest.TestCase):
    """The cockpit's ticket bar states two facts, and neither may be guessed.

    The bar summarises a ticket's work in one line, so it has to choose which
    of several sessions that line stands for, and it has to say where the
    workflow has the ticket. Both are claims about the record, and the failure
    mode of each is the same one this whole surface is built against: showing
    an answer where there is none.
    """

    def test_the_newest_start_is_the_session_the_line_stands_for(self) -> None:
        newest = _case("newestSessionIsTheLatestStart")
        self.assertEqual(newest["state"], "present")
        self.assertEqual(newest["value"]["session"]["sessionId"], "third")
        self.assertEqual(
            newest["value"]["total"],
            3,
            "the line stands in front of three sessions and must say so, rather than "
            "letting one row read as the whole of this ticket's work",
        )

    def test_a_ticket_holding_no_session_is_an_answered_absence(self) -> None:
        absent = _case("noSessionIsAnAnsweredAbsence")
        self.assertEqual(absent["state"], "absent")
        self.assertEqual(
            absent["source"]["absence"],
            "silence",
            "the record answers this read, so a ticket with no session is a measurement "
            "and not a capability anyone is waiting on",
        )

    def test_an_unparseable_start_stamp_does_not_win_the_ordering(self) -> None:
        newest = _case("unparseableStartDoesNotWinTheOrdering")
        self.assertEqual(
            newest["value"]["session"]["sessionId"],
            "dated",
            "a timestamp that does not parse is not an early one, and must not order "
            "a row ahead of one the record dated",
        )

    def test_with_nothing_to_order_by_the_records_own_order_stands(self) -> None:
        newest = _case("nothingToOrderByKeepsTheRecordsOrder")
        self.assertEqual(newest["value"]["session"]["sessionId"], "one")
        self.assertEqual(newest["value"]["total"], 2)

    def test_a_stage_the_board_serves_is_shown_as_the_served_fact(self) -> None:
        """The board projection folds `workflow.changed`; the card carries the result."""
        stage = _case("servedStageIsPresent")
        self.assertEqual(stage["state"], "present")
        self.assertEqual(stage["value"], "implement")

    def test_a_card_carrying_no_stage_is_the_record_holding_none(self) -> None:
        stage = _case("unstagedCardIsAbsent")
        self.assertEqual(stage["state"], "absent")
        self.assertEqual(stage["source"]["absence"], "silence")

    def test_a_board_read_that_did_not_land_says_nothing_about_the_stage(self) -> None:
        stage = _case("unreadBoardStaysUnreadRatherThanUnstaged")
        self.assertEqual(
            stage["state"],
            "unavailable",
            "a refused board read must not arrive at the bar as a ticket with no stage; "
            "those are opposite claims and only one of them is about this ticket",
        )
        self.assertEqual(stage["failure"]["status"], 403)


if __name__ == "__main__":
    unittest.main()
