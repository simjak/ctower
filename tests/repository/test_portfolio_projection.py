"""The director's portfolio: every rendered number recounted independently.

gh#354 asks for one URL that aggregates the three projects — tickets by lane
per project, open escalations, and unread seat comms — instead of three board
tabs and a shell sweep over git, gh and tmux. The whole value of that screen is
that its numbers are true; a plausible count looks exactly like a correct one,
and a wrong one on a portfolio view is believed precisely because nobody wants
to re-derive it by hand.

So this suite does re-derive it. `portfolio_fixtures.ts` drives the real
`read/portfolioProjection.ts` over fixed card payloads and emits *both* the
projection's output and the payloads it was given; every assertion below
recounts those payloads here, in Python, and requires the two to agree. A fold
that dropped a lane, counted by index instead of by name, folded an unreachable
board in as a zero, or attributed unread mail to a project no card linked it to
fails without anyone having to predict which mistake it would make.

Three claims get their own classes because each is a place where the honest
answer and the convenient one differ:

* a board that did not answer contributes nothing and says so — it is never a
  zero row, and the totals say how many of how many boards answered;
* a measured zero and an unaddressable principal are different states, because
  "the seats are quiet" and "this reader is not a seat" are opposite claims;
* the column axis the screen renders is the same lane set the projection emits,
  so a lane cannot stop being a column while its cards still reach a total.

Run against a tree without the projection, the fixture imports a module that
does not exist and this file fails.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_FIXTURE = Path(__file__).with_name("portfolio_fixtures.ts")
_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui/src"
_PAGE = _SURFACE / "app/portfolio/page.tsx"
_PROJECTS = ("manibo", "ctower", "bh-loop")
_OUTCOMES: dict[str, Any] = {}


def _outcomes() -> dict[str, Any]:
    if not _OUTCOMES:
        _OUTCOMES.update(ts.drive(_FIXTURE))
    return _OUTCOMES


def _portfolio(name: str = "portfolio") -> dict[str, Any]:
    return cast("dict[str, Any]", _outcomes()[name])


def _payload() -> dict[str, Any]:
    return cast("dict[str, Any]", _outcomes()["payload"])


def _cards(project: str) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _payload()[project])


def _row(portfolio: dict[str, Any], project: str) -> dict[str, Any]:
    found = next(row for row in portfolio["projects"] if row["key"] == project)
    return cast("dict[str, Any]", found)


def _lane_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    """Recount one project's lanes from the payload, not from the projection."""
    counted: dict[str, int] = {}
    for card in cards:
        lane = cast("str", card["lane"])
        counted[lane] = counted.get(lane, 0) + 1
    return counted


def _projected_lanes(counts: dict[str, Any]) -> dict[str, int]:
    return {lane["lane"]: lane["count"] for lane in counts["lanes"]}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class LaneAxisTests(unittest.TestCase):
    """The columns the screen draws are the lanes the projection emits."""

    def test_the_projection_emits_one_entry_per_recorded_lane(self) -> None:
        lanes = cast("list[str]", _outcomes()["laneAxis"])
        for project in _PROJECTS:
            with self.subTest(project=project):
                counts = _row(_portfolio(), project)["counts"]
                self.assertEqual(
                    [lane["lane"] for lane in counts["value"]["lanes"]],
                    lanes,
                    "a lane the record defines is missing from a project's row, so its cards "
                    "reach the row total without ever appearing in a column",
                )

    def test_the_board_columns_cover_exactly_those_lanes(self) -> None:
        self.assertEqual(
            _outcomes()["laneColumns"],
            _outcomes()["laneAxis"],
            "the Board's column contract and the record's lane set have diverged; a lane with "
            "no column silently stops being visible while still being counted",
        )

    def test_every_column_carries_a_title_a_reader_can_read(self) -> None:
        for title in cast("list[str]", _outcomes()["laneColumnTitles"]):
            with self.subTest(title=title):
                self.assertNotEqual(title.strip(), "")
                self.assertNotIn("_", title, "a raw lane key reached the column header")


class RenderedCountEqualityTests(unittest.TestCase):
    """Every count on the screen equals an independent recount of the payload."""

    def test_each_project_lane_count_equals_the_recount(self) -> None:
        for project in _PROJECTS:
            expected = _lane_counts(_cards(project))
            projected = _projected_lanes(_row(_portfolio(), project)["counts"]["value"])
            with self.subTest(project=project):
                self.assertEqual(
                    {lane: count for lane, count in projected.items() if count > 0},
                    expected,
                    "a project's lane counts do not match a recount of its own cards",
                )

    def test_each_project_ticket_total_equals_its_card_count(self) -> None:
        for project in _PROJECTS:
            with self.subTest(project=project):
                self.assertEqual(
                    _row(_portfolio(), project)["counts"]["value"]["tickets"],
                    len(_cards(project)),
                    "a project row's ticket total is not the number of cards its board answered",
                )

    def test_the_portfolio_lane_totals_equal_the_sum_over_every_project(self) -> None:
        expected: dict[str, int] = {}
        for project in _PROJECTS:
            for lane, count in _lane_counts(_cards(project)).items():
                expected[lane] = expected.get(lane, 0) + count
        projected = {lane["lane"]: lane["count"] for lane in _portfolio()["laneTotals"]}
        self.assertEqual(
            {lane: count for lane, count in projected.items() if count > 0},
            expected,
            "the portfolio row does not sum the rows above it",
        )

    def test_the_portfolio_ticket_total_equals_every_card(self) -> None:
        self.assertEqual(
            _portfolio()["tickets"],
            sum(len(_cards(project)) for project in _PROJECTS),
            "the headline ticket count is not the number of cards the boards answered",
        )

    def test_the_lane_totals_sum_to_the_ticket_total(self) -> None:
        self.assertEqual(
            sum(lane["count"] for lane in _portfolio()["laneTotals"]),
            _portfolio()["tickets"],
            "the matrix does not add up to its own row total, so at least one card is in a "
            "lane the matrix does not draw",
        )

    def test_the_recorded_stage_count_equals_the_cards_that_carry_one(self) -> None:
        self.assertEqual(
            _portfolio()["staged"],
            sum(1 for project in _PROJECTS for card in _cards(project) if card["staged"]),
            "the line explaining why the axis is lane rather than stage miscounts the cards "
            "that do carry a recorded stage",
        )


class EscalationTests(unittest.TestCase):
    """Open escalations are the record's waiting cards, all of them."""

    def test_every_waiting_card_becomes_exactly_one_escalation(self) -> None:
        expected = sum(1 for project in _PROJECTS for card in _cards(project) if card["waiting"])
        self.assertGreater(expected, 0, "the fixture stopped exercising the escalation path")
        self.assertEqual(
            len(_portfolio()["escalations"]),
            expected,
            "the escalation list is not the set of cards the record says a human is waiting on",
        )

    def test_no_card_that_is_not_waiting_becomes_an_escalation(self) -> None:
        waiting_lanes: list[str] = [
            cast("str", card["lane"])
            for project in _PROJECTS
            for card in _cards(project)
            if card["waiting"]
        ]
        self.assertEqual(
            sorted(cast("str", item["lane"]) for item in _portfolio()["escalations"]),
            sorted(waiting_lanes),
            "an escalation was projected from a card the record does not hold a finding for",
        )

    def test_each_escalation_names_the_finding_rather_than_a_severity(self) -> None:
        for escalation in _portfolio()["escalations"]:
            with self.subTest(ticket=escalation["ticketId"]):
                self.assertNotEqual(escalation["kindKey"], "")
                self.assertNotEqual(escalation["reasonCode"], "")
                self.assertNotEqual(escalation["findingId"], "")
                self.assertIn(escalation["projectKey"], _PROJECTS)

    def test_the_escalations_are_the_projects_own_rows_concatenated(self) -> None:
        per_row = [
            item["findingId"]
            for project in _PROJECTS
            for item in _row(_portfolio(), project)["escalations"]
        ]
        self.assertEqual(
            sorted(per_row),
            sorted(item["findingId"] for item in _portfolio()["escalations"]),
            "the page-level list and the per-project lists disagree, so one of the two is "
            "showing the operator a set the other says does not exist",
        )


class UnreadCommsTests(unittest.TestCase):
    """A thread belongs to a project only where a card says it does."""

    def test_each_project_unread_counts_only_threads_its_cards_link(self) -> None:
        threads = {
            cast("str", thread["threadId"]): cast("int", thread["unreadCount"])
            for thread in _payload()["inbox"]["threads"]
        }
        for project in _PROJECTS:
            linked = {
                thread for card in _cards(project) for thread in cast("list[str]", card["threads"])
            }
            with self.subTest(project=project):
                self.assertEqual(
                    _row(_portfolio(), project)["unread"]["value"],
                    sum(threads[thread] for thread in linked),
                    "a project's unread count is not the unread mail on the threads its own "
                    "cards name",
                )

    def test_unread_on_threads_no_card_links_is_counted_apart(self) -> None:
        linked = {
            thread
            for project in _PROJECTS
            for card in _cards(project)
            for thread in cast("list[str]", card["threads"])
        }
        expected = sum(
            cast("int", thread["unreadCount"])
            for thread in _payload()["inbox"]["threads"]
            if thread["threadId"] not in linked
        )
        self.assertGreater(expected, 0, "the fixture stopped exercising the unlinked path")
        self.assertEqual(
            _portfolio()["comms"]["value"]["unlinkedUnread"],
            expected,
            "mail on a thread no board card links was dropped or spread across projects",
        )

    def test_the_per_project_and_unlinked_counts_reconcile_with_the_total(self) -> None:
        comms = _portfolio()["comms"]["value"]
        per_project = sum(
            cast("int", _row(_portfolio(), project)["unread"]["value"]) for project in _PROJECTS
        )
        self.assertEqual(
            per_project + cast("int", comms["unlinkedUnread"]),
            comms["totalUnread"],
            "the numbers the panel prints do not add up to the projection's own total, so a "
            "reader checking the page against itself would find it wrong",
        )

    def test_each_thread_names_the_projects_whose_cards_link_it(self) -> None:
        by_thread = {
            cast("str", thread["threadId"]): sorted(cast("list[str]", thread["projects"]))
            for thread in _portfolio()["comms"]["value"]["threads"]
        }
        for thread_id, projects in by_thread.items():
            expected = sorted(
                project
                for project in _PROJECTS
                if any(thread_id in card["threads"] for card in _cards(project))
            )
            with self.subTest(thread=thread_id):
                self.assertEqual(projects, expected)


class UnreachableBoardTests(unittest.TestCase):
    """A board that did not answer is never rendered as a project with no work."""

    def test_the_failed_project_row_carries_the_read_failure_not_a_zero(self) -> None:
        counts = _row(_portfolio("oneBoardUnreachable"), "manibo")["counts"]
        self.assertEqual(
            counts["known"],
            "unread",
            "an unreachable board became a counted row; six zeroes across the lanes is the "
            "claim that this project holds no work",
        )
        self.assertIn("503", counts["reason"])

    def test_the_totals_exclude_the_project_that_did_not_answer(self) -> None:
        degraded = _portfolio("oneBoardUnreachable")
        self.assertEqual(
            degraded["tickets"],
            len(_cards("ctower")) + len(_cards("bh-loop")),
            "the ticket total counted a board that never answered",
        )
        self.assertEqual(degraded["answered"], 2)
        self.assertEqual(degraded["considered"], 3)
        self.assertIsNotNone(degraded["reason"])

    def test_the_failed_project_takes_no_unread_attribution(self) -> None:
        unread = _row(_portfolio("oneBoardUnreachable"), "manibo")["unread"]
        self.assertEqual(
            unread["known"],
            "unread",
            "a project whose cards were never read was given an unread count anyway; without "
            "its cards there is nothing to attribute a thread by",
        )

    def test_reaching_no_board_at_all_is_still_a_rendered_answer(self) -> None:
        empty = _portfolio("noBoardAnswered")
        self.assertEqual(empty["answered"], 0)
        self.assertEqual(empty["considered"], 3)
        self.assertEqual(empty["tickets"], 0)
        self.assertEqual(empty["escalations"], [])
        self.assertEqual(
            [row["counts"]["known"] for row in empty["projects"]],
            ["unread", "unread", "unread"],
            "with nothing reached, the page must say so on every row rather than render an "
            "empty portfolio",
        )

    def test_an_unreachable_inbox_is_not_an_empty_inbox(self) -> None:
        comms = _portfolio("inboxUnreachable")["comms"]
        self.assertEqual(comms["known"], "unread")
        self.assertIn("401", comms["reason"])
        for row in _portfolio("inboxUnreachable")["projects"]:
            with self.subTest(project=row["key"]):
                self.assertEqual(row["unread"]["known"], "unread")


class AddressabilityTests(unittest.TestCase):
    """Zero unread means two different things, and the page says which."""

    def test_a_principal_with_no_seat_row_is_marked_unaddressable(self) -> None:
        comms = _portfolio("unaddressablePrincipal")["comms"]["value"]
        self.assertFalse(
            comms["addressable"],
            "the projection named this principal unaddressable and the fold kept it as an "
            "ordinary empty inbox; nothing can be delivered to it at all",
        )
        self.assertIsNotNone(comms["unaddressableWhy"])
        self.assertIn("seat", cast("str", comms["unaddressableWhy"]))
        self.assertEqual(comms["totalUnread"], 0)

    def test_a_real_seat_with_no_mail_is_not_marked_unaddressable(self) -> None:
        comms = _portfolio("addressablePrincipalWithNoMail")["comms"]["value"]
        self.assertTrue(comms["addressable"])
        self.assertIsNone(
            comms["unaddressableWhy"],
            "a seat that simply holds no mail was given the cannot-be-addressed explanation",
        )


class ScreenWiringTests(unittest.TestCase):
    """The route exists, reads through the adapter, and is not cached."""

    def test_the_route_is_built(self) -> None:
        self.assertTrue(_PAGE.is_file(), "the portfolio route the issue asks for does not exist")

    def test_the_route_reads_through_the_adapter_seam(self) -> None:
        source = _source(_PAGE)
        self.assertIn(
            "recordAdapter.portfolio()",
            source,
            "the page builds its own reads instead of asking the adapter, so the source cannot "
            "be swapped in one file",
        )

    def test_the_route_is_not_ssr_cached(self) -> None:
        self.assertIn(
            'dynamic = "force-dynamic"',
            _source(_PAGE),
            "a record-reading route is SSR-cached; a stale portfolio is a portfolio that lies "
            "about what is waiting on a human",
        )

    def test_the_route_renders_all_three_answers_the_issue_asks_for(self) -> None:
        source = _source(_PAGE)
        for component in ("ProjectLanes", "Escalations", "SeatComms"):
            with self.subTest(component=component):
                self.assertIn(component, source)

    def test_the_project_rows_are_the_configured_list_and_not_a_second_one(self) -> None:
        composer = _source(_SURFACE / "read/portfolio.ts")
        self.assertIn(
            "configuredProjects()",
            composer,
            "the portfolio names its own projects, so a project that registers later would "
            "need a view change the issue says it must not need",
        )
        for project in _PROJECTS:
            with self.subTest(project=project):
                self.assertNotIn(f'"{project}"', _source(_PAGE))

    def test_a_fourth_project_needs_no_view_change(self) -> None:
        self.assertEqual(
            _outcomes()["fourthProjectNeedsNoViewChange"],
            ["manibo", "ctower", "bh-loop", "new-project"],
            "the fold does not simply render the projects it is handed",
        )

    def test_the_surface_carries_no_mutation_affordance(self) -> None:
        for path in [*sorted((_SURFACE / "surfaces/portfolio").rglob("*.tsx")), _PAGE]:
            with self.subTest(module=path.name):
                source = _source(path)
                self.assertNotIn("<form", source)
                self.assertNotIn("<button", source)
                self.assertNotIn("method=", source)


if __name__ == "__main__":
    unittest.main()
