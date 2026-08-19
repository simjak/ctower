"""Every citation the browser surface prints is a fact, and is checked like one.

Round-3 QA drove the live board and found nine panels across three screens all
reading *lands with #186*. #186 is "Ticket and board events reach the operator's
channel"; it covers a ticket brief, acceptance criteria, a work timeline,
evidence coverage, comments, labels and relations exactly as much as it covers
none of them. The panels' whole value is that they refuse to invent data and name
where the real thing is coming from, and that promise is worth nothing when the
pointer is wrong — a pointer that points everywhere points nowhere (#241).

These tests hold three lines:

* one issue number may not stand behind unrelated capabilities;
* a capability with nothing filed says so, rather than borrowing a number;
* no screen may mint a citation of its own, so every one passes the reviewed
  table in `read/futureSources.ts`.

The rail contract (#243) is checked here too: a nav label is a promise about
where a click lands, which is the same class of claim.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_FIXTURE = Path(__file__).with_name("declared_source_fixtures.ts")
_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui/src"
_REGISTRY = "apps/ctower-ui/src/read/futureSources.ts"
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_ISSUE = re.compile(r"#\d+")
# `#200`, or `#115 · D29` — an issue, optionally qualified by the decision or
# acceptance criterion that pins the fact. Nothing else is a citation.
_CITATION = re.compile(r"^#\d+(?: · (?:D\d+|AC-[A-Z]+-\d+))?$")
_OUTCOMES: dict[str, Any] = {}


def _outcomes() -> dict[str, Any]:
    if not _OUTCOMES:
        _OUTCOMES.update(ts.drive(_FIXTURE))
    return _OUTCOMES


def _sources() -> dict[str, dict[str, Any]]:
    return cast("dict[str, dict[str, Any]]", _outcomes()["sources"])


def _code(path: Path) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8")))


def _surface_files() -> tuple[Path, ...]:
    return tuple(sorted(path for path in _SURFACE.rglob("*") if path.suffix in (".ts", ".tsx")))


class DeclaredSourceTests(unittest.TestCase):
    """What the surface says when it has nothing to show."""

    def test_the_table_is_not_empty(self) -> None:
        self.assertGreater(len(_sources()), 8, "the declared-source table found almost nothing")

    def test_every_entry_declares_which_kind_of_absence_it_is(self) -> None:
        for name, source in _sources().items():
            with self.subTest(source=name):
                self.assertIn(source["absence"], ("capability", "silence"))
                self.assertNotEqual(source["what"].strip(), "")

    def test_no_two_capabilities_share_one_citation(self) -> None:
        cited: dict[str, list[str]] = {}
        for name, source in _sources().items():
            lands = source.get("lands")
            if isinstance(lands, str):
                cited.setdefault(lands, []).append(name)
        shared = {lands: names for lands, names in cited.items() if len(names) > 1}
        self.assertEqual(
            shared,
            {},
            "one work item is cited for several unrelated facts; that is the #241 defect, "
            "and it is how nine panels came to point at one issue that covered none of them",
        )

    def test_every_citation_is_shaped_like_a_work_item(self) -> None:
        for name, source in _sources().items():
            lands = source.get("lands")
            if isinstance(lands, str):
                with self.subTest(source=name):
                    self.assertRegex(lands, _CITATION)

    def test_every_citation_carries_the_sentence_that_justifies_it(self) -> None:
        for name, source in _sources().items():
            if source["absence"] != "capability":
                continue
            with self.subTest(source=name):
                if source["lands"] is None:
                    self.assertIsNone(
                        source["why"],
                        "an uncited capability carries a justification for a citation it "
                        "does not make",
                    )
                else:
                    why = source["why"]
                    self.assertIsInstance(why, str)
                    self.assertGreater(
                        len(cast("str", why)),
                        40,
                        "a citation without a sentence saying how that item covers this fact "
                        "cannot be checked by a reader, which is how #241 survived review",
                    )

    def test_the_feed_issue_is_cited_for_nothing(self) -> None:
        cited = [
            name
            for name, source in _sources().items()
            if isinstance(source.get("lands"), str) and "#186" in source["lands"]
        ]
        self.assertEqual(
            cited,
            [],
            "#186 is the operator-channel feed; it lands none of these facts",
        )

    def test_the_work_timeline_reads_the_record_rather_than_citing_a_future_one(self) -> None:
        """The record answers `/v1/tickets/{id}/sessions`, so nothing may cite a future one."""
        self.assertNotIn(
            "NO_WORK_SESSIONS",
            _sources(),
            "a per-session work fact is still declared as a missing capability; the record "
            "carries seat, duration, tokens and outcome, so a ticket holding none is a silence",
        )
        timeline = (_SURFACE / "surfaces/ticket/WorkTimeline.tsx").read_text(encoding="utf-8")
        self.assertIn(
            "Reading<readonly WorkSession[]>",
            timeline,
            "the work timeline takes no reading, so it cannot be showing the record",
        )

    def test_labels_cite_the_context_set_contract_and_the_decision_granting_it(self) -> None:
        self.assertEqual(_sources()["NO_LABELS"]["lands"], "#115 · D29")

    def test_a_capability_with_nothing_filed_says_so_instead_of_borrowing_a_number(self) -> None:
        uncited = [
            name
            for name, source in _sources().items()
            if source["absence"] == "capability" and source["lands"] is None
        ]
        self.assertNotEqual(
            uncited,
            [],
            "every capability now claims a work item; at least one of these had none filed, "
            "and inventing one would be the defect this table exists to prevent",
        )

    def test_a_record_that_simply_holds_none_cites_nothing(self) -> None:
        for name, source in _sources().items():
            if source["absence"] == "silence":
                with self.subTest(source=name):
                    self.assertNotIn(
                        "lands",
                        source,
                        "a fact the record does carry needs no roadmap pointer; it arrives "
                        "the moment someone appends one",
                    )


class CitationOwnershipTests(unittest.TestCase):
    """No screen mints a citation; the reviewed table is the only source."""

    def test_the_scan_finds_a_non_empty_denominator(self) -> None:
        found = _surface_files()
        self.assertGreater(len(found), 10, "the surface scan found almost nothing")
        self.assertIn(_REGISTRY, {path.relative_to(_ROOT).as_posix() for path in found})

    def test_no_module_outside_the_table_writes_an_issue_number_into_the_product(self) -> None:
        offenders = sorted(
            f"{path.relative_to(_ROOT).as_posix()}: {match}"
            for path in _surface_files()
            if path.relative_to(_ROOT).as_posix() != _REGISTRY
            for match in _ISSUE.findall(_code(path))
        )
        self.assertEqual(
            offenders,
            [],
            "an issue number reaches the operator from outside read/futureSources.ts; "
            "route it through the table so the claim is reviewed once and rendered with "
            "the sentence that justifies it",
        )


class RailContractTests(unittest.TestCase):
    """#243 — a nav label is a promise about where the click lands."""

    def test_the_rail_offers_every_built_screen_once(self) -> None:
        rail = cast("list[dict[str, Any]]", _outcomes()["rail"])
        hrefs = [item["href"] for item in rail]
        self.assertEqual(sorted(hrefs), sorted(set(hrefs)), "a destination appears twice")
        self.assertEqual(
            sorted(hrefs),
            [
                "/board",
                "/explorer",
                "/feed",
                "/files",
                "/inbox",
                "/metrics",
                "/portfolio",
                "/requests",
                "/team",
                "/ticket",
                "/workspace",
            ],
        )

    def test_the_single_ticket_route_is_not_labelled_as_a_collection(self) -> None:
        rail = cast("list[dict[str, Any]]", _outcomes()["rail"])
        label = next(item["label"] for item in rail if item["href"] == "/ticket")
        self.assertEqual(
            label,
            "Latest ticket",
            "this route opens one ticket, so a plural label promises a list it never shows",
        )

    def test_the_route_states_its_rule_instead_of_redirecting_away_from_it(self) -> None:
        page = _code(_SURFACE / "app/ticket/page.tsx")
        self.assertNotIn(
            "redirect(",
            page,
            "the route redirects, so the sentence explaining which ticket it opened renders "
            "only on the path where it did not open one",
        )

    def test_every_rail_label_matches_the_page_that_lights_it(self) -> None:
        chrome = _code(_SURFACE / "frame/Chrome.tsx")
        rail = cast("list[dict[str, Any]]", _outcomes()["rail"])
        labels = {item["label"] for item in rail}
        lit = set(re.findall(r'^\s*\w+: "([^"]+)",$', chrome, re.MULTILINE))
        self.assertEqual(
            lit - labels,
            set(),
            "a screen lights a rail item that does not exist, so its nav entry stays dark",
        )


class ProjectBoardTests(unittest.TestCase):
    """Three project boards, and no fourth invented on the way."""

    def test_the_fleet_declares_exactly_the_operator_s_three_projects(self) -> None:
        keys = [project["key"] for project in _outcomes()["projects"]["configured"]]
        self.assertEqual(
            keys,
            ["manibo", "ctower", "bh-loop"],
            "the board offers a project set that is not the one the operator runs",
        )

    def test_every_project_key_is_one_the_record_can_be_asked_for(self) -> None:
        # the contract's own pattern for `project_key`
        pattern = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
        for project in _outcomes()["projects"]["configured"]:
            with self.subTest(project=project["key"]):
                self.assertRegex(project["key"], pattern)

    def test_the_metrics_scope_token_stays_what_the_vendored_stylesheet_keys_on(self) -> None:
        tokens = {p["key"]: p["scopeToken"] for p in _outcomes()["projects"]["configured"]}
        self.assertEqual(
            tokens["bh-loop"],
            "bhloop",
            "the record's project key was pushed into the vendored Metrics stylesheet, whose "
            "scope radios key on #s-bhloop and are re-vendored byte-for-byte",
        )

    def test_the_project_list_is_declared_once(self) -> None:
        # Metrics used to carry its own copy; it now derives from the same list
        merge_history = _code(_SURFACE / "read/sources/mergeHistory.ts")
        self.assertIn("configuredProjects()", merge_history)
        self.assertNotIn(
            '"/srv/projects/manibo"',
            merge_history,
            "a second project list was typed out; derive it from read/projects.ts",
        )

    def test_an_unconfigured_project_never_becomes_a_board(self) -> None:
        projects = _outcomes()["projects"]
        self.assertEqual(projects["selectedFromUnknown"], projects["default"])
        self.assertEqual(projects["selectedFromNothing"], projects["default"])
        self.assertEqual(projects["selectedFromKnown"], "manibo")

    def test_this_surface_opens_on_its_own_project(self) -> None:
        self.assertEqual(_outcomes()["projects"]["default"], "ctower")

    def test_every_record_read_is_scoped_by_project_key(self) -> None:
        adapter = _code(_SURFACE / "read/httpRecordAdapter.ts")
        self.assertIn("project_key=", adapter)
        self.assertNotIn(
            'read("/v1/board")',
            adapter,
            "the board is read unscoped, though project_key is a required parameter",
        )

    def test_a_scoped_board_does_not_contradict_its_project_filter(self) -> None:
        note = _SURFACE / "surfaces/board/ScopeNote.tsx"
        page = _code(_SURFACE / "app/board/page.tsx")
        self.assertFalse(note.exists(), "the obsolete false project-scope warning still exists")
        self.assertNotIn("ScopeNote", page)
        self.assertNotIn("these are not", page)

    def test_a_refusal_is_not_rendered_as_an_empty_board(self) -> None:
        declared = _code(_SURFACE / "frame/Declared.tsx")
        self.assertIn("REFUSED_STATUS", declared)
        self.assertIn(
            "failure.status",
            declared,
            "the refusal is told apart by matching prose in the reason rather than by the "
            "status the typed failure carries",
        )


class BoardContextRenderingTests(unittest.TestCase):
    def test_the_phone_lane_jump_contains_its_own_horizontal_scroll(self) -> None:
        stylesheet = (_ROOT / "apps/ctower-ui/design-reference/app.css").read_text(encoding="utf-8")
        stagejump = re.search(r"\.stagejump\s*\{([^}]+)\}", stylesheet, re.DOTALL)
        self.assertIsNotNone(stagejump, "the lane-jump row has no shared style rule")
        assert stagejump is not None
        rule = stagejump.group(1)
        self.assertIn("overflow-x: auto", rule)
        self.assertIn("max-width: 100%", rule)
        self.assertIn("min-width: 0", rule)

    def test_the_board_card_consumes_each_projected_context_member(self) -> None:
        card = _code(_SURFACE / "surfaces/board/LaneCard.tsx")
        self.assertIn("boardCardContextFor(card)", card)
        for member in ("tenant", "changes", "labels", "humanWaiting", "deliverySurface"):
            with self.subTest(member=member):
                self.assertIn(
                    f"context.{member}",
                    card,
                    f"the card projection carries {member}, but the component drops it",
                )


class IssueLinkTests(unittest.TestCase):
    """A link the operator clicks is a claim about where the work lives."""

    def test_a_recorded_issue_source_resolves_to_its_own_repository(self) -> None:
        github = _outcomes()["issues"]["resolvedGithub"]
        self.assertEqual(github["url"], "https://github.com/simjak/ctower/issues/236")
        self.assertEqual(github["label"], "simjak/ctower#236")
        self.assertEqual(github["repository"], "simjak/ctower")
        gitlab = _outcomes()["issues"]["resolvedGitlab"]
        self.assertEqual(gitlab["url"], "https://gitlab.com/group/proj/-/issues/7")

    def test_none_of_the_kinds_this_instance_holds_resolves_to_a_link(self) -> None:
        issues = _outcomes()["issues"]
        for name in ("missionControlRequest", "dogfoodGap", "operatorSpec", "fixture"):
            with self.subTest(kind=name):
                self.assertIsNone(
                    issues[name],
                    "a source kind that is not an issue tracker produced a link; the operator "
                    "would click it and land somewhere nothing recorded",
                )

    def test_a_ref_that_carries_no_repository_is_refused(self) -> None:
        issues = _outcomes()["issues"]
        for name in ("bareNumber", "refWithoutRepository", "looksLikeARepo"):
            with self.subTest(ref=name):
                self.assertIsNone(
                    issues[name],
                    "a repository was supplied for a ref that did not carry one, which is the "
                    "name-inference INV-66 forbids",
                )

    def test_the_surface_can_say_which_half_is_missing(self) -> None:
        names = _outcomes()["issues"]["namesTracker"]
        self.assertTrue(names["githubIssue"])
        self.assertFalse(names["dogfoodGap"])
        self.assertFalse(names["missionControlRequest"])

    def test_no_screen_composes_an_issue_url_of_its_own(self) -> None:
        offenders = sorted(
            path.relative_to(_ROOT).as_posix()
            for path in _surface_files()
            if path.relative_to(_ROOT).as_posix() != "apps/ctower-ui/src/read/issueRef.ts"
            and ("github.com" in _code(path) or "gitlab.com" in _code(path))
        )
        self.assertEqual(
            offenders,
            [],
            "a screen builds an issue URL itself; route it through read/issueRef.ts, which "
            "refuses a ref that does not carry its own repository",
        )


if __name__ == "__main__":
    unittest.main()
