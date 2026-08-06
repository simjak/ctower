"""The 0-of-0 board guard — two empties, neither rendered blank.

The P0 (operator-found 2026-08-04 ~08:00Z): during a runtime swap the API
restarted and answered `watermark 0 of 0` with zero cards for a window, and the
served board RENDERED that empty answer as an empty board while cards sat safe
at a higher watermark. That is the honesty-defect class this surface already
guards, one level deeper. But there are TWO ways a scoped board answers 0 of 0,
and both rendered blank before this guard:

* restart/fresh — the portfolio's watermark is ALSO 0 (or unreadable): the API
  is restarting/rebuilding or the instance is genuinely fresh. Renders the
  refusal block.
* true-empty-project — the portfolio holds a nonzero watermark, so THIS
  project's import chain simply has not run (the operator's `?project=manibo`
  today). Renders its own named block with a link to the portfolio view.

The discriminator is the portfolio (unscoped) watermark read in the same
render. The decision is a pure function on values (`boardEmptyKind` in
`apps/ctower-ui/src/read/boardProjection.ts`), driven here by
`surface_fixtures.ts` so a regression fails without the guard; a second group
asserts the page is wired to both named blocks; a third locks the SSR-caching
rule (no record-reading route may cache an answer across renders, or a refusal
is served stale).

Run against a tree without the guard, the fixture drives a function that does
not exist and this file fails.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_FIXTURE = Path(__file__).with_name("surface_fixtures.ts")
_ROOT = Path(__file__).resolve().parents[2]
_APP = _ROOT / "apps/ctower-ui/src/app"
_BOARD_PAGE = _APP / "board/page.tsx"
_REFUSAL_BLOCK = _ROOT / "apps/ctower-ui/src/surfaces/board/ZeroOfZeroRefusal.tsx"
_TRUE_EMPTY_BLOCK = _ROOT / "apps/ctower-ui/src/surfaces/board/TrueEmptyProject.tsx"
_LANE_CARD = _ROOT / "apps/ctower-ui/src/surfaces/board/LaneCard.tsx"

_OUTCOMES: dict[str, Any] = {}


def _outcomes() -> dict[str, Any]:
    if not _OUTCOMES:
        _OUTCOMES.update(ts.drive(_FIXTURE))
    return _OUTCOMES


def _kind(name: str) -> str:
    case = _outcomes()[name]
    if not isinstance(case, str):
        raise TypeError(f"watermark-zero case {name} is not a string kind")
    return case


class WatermarkZeroDecisionTests(unittest.TestCase):
    """The pure guard: 0-of-0 is never normal; the two empties are told apart."""

    def test_a_zero_of_zero_with_a_zero_portfolio_is_the_restart_case(self) -> None:
        self.assertEqual(
            _kind("zeroOfZeroPortfolioZeroIsRestartFresh"),
            "restart-fresh",
            "portfolio also 0 with a 0-of-0 scoped answer was not treated as the "
            "restart/fresh refusal — an empty answer rendered as truth hides work",
        )

    def test_a_zero_of_zero_with_a_nonzero_portfolio_is_a_true_empty_project(self) -> None:
        self.assertEqual(
            _kind("zeroOfZeroPortfolioNonzeroIsTrueEmptyProject"),
            "true-empty-project",
            "the operator's `?project=manibo` (scoped 0-of-0 while the portfolio holds "
            "records) was not named as a not-yet-imported project",
        )

    def test_a_zero_of_zero_with_an_unreachable_portfolio_is_refused(self) -> None:
        self.assertEqual(
            _kind("zeroOfZeroPortfolioUnreachableIsRestartFresh"),
            "restart-fresh",
            "an unreadable portfolio folded into 'true-empty'; without the portfolio "
            "answer the honest conservative block is the refusal",
        )

    def test_a_nonzero_watermark_empty_project_renders_normally(self) -> None:
        self.assertEqual(
            _kind("nonzeroWatermarkEmptyProjectRendersNormally"),
            "normal",
            "a genuinely empty PROJECT under a nonzero portfolio watermark was dragged "
            "into an empty-case block — it must render its normal honest empty state",
        )

    def test_a_zero_watermark_with_cards_renders_normally(self) -> None:
        self.assertEqual(
            _kind("zeroWatermarkWithCardsRendersNormally"),
            "normal",
            "a board with cards was sent to an empty-case block",
        )

    def test_a_nonzero_watermark_with_cards_renders_normally(self) -> None:
        self.assertEqual(
            _kind("nonzeroWatermarkWithCardsRendersNormally"),
            "normal",
            "a normal board was sent to an empty-case block — NO behaviour change for "
            "any watermark > 0",
        )


class WatermarkZeroWiringTests(unittest.TestCase):
    """The page calls the guard and renders a named block for each empty case."""

    def test_the_board_page_invokes_the_guard(self) -> None:
        source = _BOARD_PAGE.read_text(encoding="utf-8")
        self.assertIn(
            "boardEmptyKind(",
            source,
            "the board page stopped calling the guard, so a 0-of-0 answer renders "
            "as an empty board again",
        )

    def test_the_board_page_renders_both_named_blocks(self) -> None:
        source = _BOARD_PAGE.read_text(encoding="utf-8")
        self.assertIn("ZeroOfZeroRefusal", source, "the restart/fresh block is not rendered")
        self.assertIn("TrueEmptyProject", source, "the true-empty-project block is not rendered")

    def test_the_board_page_reads_the_portfolio_watermark_in_the_same_render(self) -> None:
        source = _BOARD_PAGE.read_text(encoding="utf-8")
        self.assertIn(
            "portfolioWatermarkFor",
            source,
            "the page no longer routes the portfolio watermark through the read "
            "layer; a surface must not inspect a Reading's state to get it",
        )
        self.assertIn(
            "defaultProjectKey()",
            source,
            "the page never reads the portfolio, so the two empty cases cannot be told apart",
        )
        self.assertIn(
            "portfolioWatermark",
            source,
            "the portfolio watermark is not passed to the empty-case decision",
        )

    def test_the_restart_block_states_both_honest_possibilities_and_a_reload(self) -> None:
        source = _REFUSAL_BLOCK.read_text(encoding="utf-8")
        self.assertIn("refusing to render", source, "the block does not say it refused")
        self.assertIn("restarting", source, "the API-restarting possibility is missing")
        self.assertIn("fresh instance", source, "the fresh-instance possibility is missing")
        self.assertIn("reload", source, "the block gives the operator no way to re-check")

    def test_the_true_empty_block_names_the_import_chain_and_the_portfolio_view(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertIn("import", source, "the block does not say the import chain fills it")
        self.assertIn("portfolio view", source, "the block does not point at the portfolio")
        self.assertIn('href="/board"', source, "the block has no link to the unscoped board")

    def test_the_board_page_reads_the_portfolio_entries_in_the_same_render(self) -> None:
        source = _BOARD_PAGE.read_text(encoding="utf-8")
        self.assertIn(
            "portfolioEntriesFor",
            source,
            "the true-empty-project block has no cross-project entries to render below the banner",
        )
        self.assertIn(
            "portfolioEntries",
            source,
            "the portfolio's own entries are not passed to the true-empty-project block",
        )


class PortfolioViewPromiseTests(unittest.TestCase):
    """gh#319 direction-a — the promised view now actually renders.

    Round-5 QA (#319) found this block's copy claiming "the portfolio view
    below shows every imported card across projects" while nothing rendered
    below the banner. #323 (branch fix/318-319-ui-fixes, open when this lane
    built and merged to main before it) took the honest-fallback direction and
    re-worded that sentence to describe the link the block actually rendered.
    This lane takes the other honest direction #319 itself names as preferred:
    gh#115 landed a tenant fact per card (D29's five-member context set), so
    the promised view is now a trivial unfiltered render. `main`'s wording is
    kept — this class pins that the portfolio promise its copy carries is made
    true by a real render, never merely pointed at.
    """

    def test_the_block_keeps_its_portfolio_promise_by_rendering_it(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertIn(
            "Every imported card across projects is visible",
            source,
            "the block dropped the portfolio promise from its copy instead of keeping it",
        )
        self.assertIn(
            "<h2>Portfolio</h2>",
            source,
            "the block's copy promises a portfolio view its own render never carries",
        )

    def test_the_block_renders_a_real_panel_below_the_banner(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertIn(
            'className="panel"',
            source,
            "the promised portfolio view still has no panel of its own below the banner",
        )

    def test_the_panel_renders_every_portfolio_entry_it_is_given(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertIn(
            "portfolioEntries.map",
            source,
            "the panel does not render the portfolio's own entries — a promise kept "
            "by a hardcoded or truncated list is the same lie as an empty one",
        )

    def test_the_panel_shows_each_card_s_tenant_fact(self) -> None:
        source = _LANE_CARD.read_text(encoding="utf-8")
        self.assertIn(
            "context.tenant",
            source,
            "the cross-project view does not show the tenant fact #115 added — "
            "without it the list is an undifferentiated pile, not a cross-project view",
        )


class TrueEmptyProjectPromiseTests(unittest.TestCase):
    """gh#319 — an empty-state's copy may only promise what its own DOM carries.

    Round-5 QA found this block's copy claiming "the portfolio view below
    shows every imported card across projects" while nothing rendered below
    the banner: the block's only portfolio-view element is the link at its
    foot, not an embedded view. gh#115's project-fact work (which would make
    an embedded portfolio view a trivial unfiltered render) had no PR open at
    the time of this fix, so the honest fallback applies: the copy now
    describes the link it actually renders, never a view the DOM does not
    carry.
    """

    def test_the_block_no_longer_claims_a_view_renders_below_the_banner(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertNotIn(
            "The portfolio view below shows every imported card",
            source,
            "the block still promises an embedded portfolio view its own render never "
            "carries below the banner",
        )

    def test_the_block_renders_no_second_panel_below_the_banner(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertEqual(
            source.count('className="slot"'),
            1,
            "a second panel appeared below the banner; if it is the promised portfolio "
            "view the copy should say it renders, not that it is linked",
        )

    def test_the_only_portfolio_view_element_is_the_link_the_copy_names(self) -> None:
        source = _TRUE_EMPTY_BLOCK.read_text(encoding="utf-8")
        self.assertIn(
            "linked below",
            source,
            "the copy no longer names the link as what is below it",
        )
        self.assertIn(
            '<a href="/board">the portfolio view (all cards)</a>',
            source,
            "the link the copy points at is not the block's only portfolio-view element",
        )


class RecordRouteCachingTests(unittest.TestCase):
    """No record-reading route may cache an answer across renders.

    A board page caching a 0-of-0 answer would serve the refusal (or an empty
    board) stale long after the instance recovered — a cached refusal is as
    stale as a cached board. Every record-reading route is force-dynamic.
    """

    def test_the_board_route_is_not_ssr_cached(self) -> None:
        self.assertIn(
            'dynamic = "force-dynamic"',
            _BOARD_PAGE.read_text(encoding="utf-8"),
            "the board route is SSR-cached across answers, so a refusal or empty board "
            "is served stale",
        )

    def test_every_record_reading_route_is_not_ssr_cached(self) -> None:
        routes = (
            "board/page.tsx",
            "ticket/page.tsx",
            "ticket/[ticketId]/page.tsx",
        )
        stale = [
            route
            for route in routes
            if 'dynamic = "force-dynamic"' not in (_APP / route).read_text(encoding="utf-8")
        ]
        self.assertEqual(
            stale,
            [],
            "a record-reading route is SSR-cached; a refusal served stale is the same "
            "lie as an empty board served stale",
        )


if __name__ == "__main__":
    unittest.main()
