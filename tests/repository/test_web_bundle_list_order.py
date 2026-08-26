"""The bundle-backed lists of ``apps/ctower-web`` keep the record's order.

T-021: the CompanyBundle export is normalized and deterministic (``SPEC.md``,
§ CompanyBundle — components stored sorted by kind, key, revision and digest,
the export replays that sequence), and every project-scoped read serves its
rows in the record's own order (the kernel's ``ORDER BY`` clauses). A client
that re-sorts such data overrules the record with a client-side rule no
authored document declares — and two surfaces reading one bundle then agree
only by coincidence. The defect class found on 2026-08-23: eleven call sites
sorted API-derived lists alphabetically or by a derived key, so one tower
could render its crews page alphabetized while its own Projects page rendered
the record's order.

This is the standing precedent of ``test_browser_network_chokepoint.py``:
assert a ``ctower-web`` source property from repository structure, fail-closed.
Each inventoried module must still exist (the denominator cannot shrink to a
vacuous pass by deleting a file), each named reader must be exported from its
module exactly once (a rename cannot silently escape), and no inventoried
reader body may contain an ordering construct. The negative controls prove the
detector can fail: a fixture reader carrying a re-sort is caught, and one
without one is not.

Extraction is brace-matching over Prettier-formatted source, which the web
gate pins: an ``export function`` opens at top level and its body closes on a
line holding a single ``}``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WEB_SRC = _ROOT / "apps" / "ctower-web" / "src"

# One entry per surface that presents a list built from the bundle export or
# another ordered read. Module path relative to apps/ctower-web/src → the
# exported reader functions whose output is that list. The rule is scoped to
# each named reader's own body: a re-sort one call deep (a module-private
# helper) evades it, and the docstring above says so rather than leaving a
# reader believing the module is sealed. ``tickets/history.ts`` was
# inventoried at review time and deleted by T-009 (#564): the audit read
# replaced the timeline history, so its entry moved with the surface.
_INVENTORY: dict[str, tuple[str, ...]] = {
    "tickets/projects.ts": ("workProjectsIn",),
    # T-024 (#…): the rail governs the project workspace, so the one place a
    # project document is joined to the key that addresses it moved out of the
    # board and into the shell. ``board/lanes.ts: projectsOf`` was inventoried
    # here and is gone with the board's own project chooser; its entry moved
    # with the surface rather than shrinking the denominator. The Projects
    # screen's own reader over the same join is inventoried beside it.
    "shell/ProjectSwitcher.tsx": ("projectChoices",),
    "projects/read.ts": ("projectsIn",),
    # T-025: the agents list and the rail's AGENTS section read one bundle
    # through one reader, so the rail and the page cannot disagree about who
    # works here or in what order.
    "agents/read.ts": ("agentsIn",),
    # T-029: the three-pane cockpit on the ``crews`` destination is deleted and
    # the Crews page is the roster it could not draw. Both of its bundle-backed
    # readers moved with the surface — ``cockpit/roster.ts: rosterOf`` and
    # ``cockpit/useSessions.ts: sessionsOfProject`` are these two entries —
    # rather than shrinking the denominator.
    "crews/roster.ts": ("rosterOf",),
    "workflows/compose.ts": ("projectKeys", "boundProjects"),
    "inbox/address.ts": ("routeTo", "seatsOffered"),
    "tickets/workflow.ts": ("workflowFrom",),
    "crews/useSessions.ts": ("sessionsOfProject",),
    # T-027: the tickets table became the frozen design's two readings of one
    # `getBoard` answer — the list you walk down and the six columns. Both are
    # inventoried, because either could re-rank the record on its own; the
    # ``tickets/TicketTable.tsx: TicketTable`` entry moved here with the
    # surface rather than shrinking the denominator.
    "tickets/TicketList.tsx": ("TicketList",),
    "tickets/TicketBoard.tsx": ("TicketBoard",),
    # The people and the projects the pop-up that raises a ticket offers are
    # bundle-backed lists like any other, and the record's order is the offer's.
    "tickets/who.ts": ("staffIn", "whereIn"),
}

# Any ordering construct inside an inventoried reader is a re-sort of recorded
# order: ``x.sort(...)``, ``toSorted``, lodash-style ``orderBy``, or any bare
# reference to those names. Comments are stripped first so prose can neither
# pass nor fail a reader.
_ORDERING = re.compile(r"\b(?:sort|toSorted|orderBy)\b")

_DECLARATION = r"^export\s+(?:async\s+)?function\s+{name}\s*\("
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

__all__: tuple[str, ...] = ()


def _stripped_source(path: Path) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8")))


def _function_body(source: str, name: str) -> str | None:
    """The text from the ``export function <name>`` line through its close."""
    match = re.search(_DECLARATION.format(name=name), source, re.MULTILINE)
    if match is None:
        return None
    start = match.start()
    open_brace = source.index("{", _parameters_close(source, match.end() - 1))
    depth = 0
    for position in range(open_brace, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start : position + 1]
    return None


def _parameters_close(source: str, open_paren: int) -> int:
    """The index of the ``)`` closing a declaration's parameter list.

    A component destructures its props, so the first ``{`` after the
    declaration opens a parameter pattern rather than the body. Balancing the
    parameter list first is what makes the body of such a reader scannable
    instead of silently empty. The scan assumes no ``)`` inside a parameter
    default's own call — true of every inventoried reader.
    """
    depth = 1
    position = open_paren
    while depth:
        position += 1
        if source[position] == "(":
            depth += 1
        elif source[position] == ")":
            depth -= 1
    return position


class WebBundleListOrderTests(unittest.TestCase):
    """Fail-closed guard: readers over bundle-backed lists never re-sort."""

    def test_the_inventory_names_files_that_still_exist(self) -> None:
        missing = [relative for relative in _INVENTORY if not (_WEB_SRC / relative).is_file()]
        self.assertEqual(
            missing,
            [],
            "an inventoried ctower-web module vanished; move its entry to wherever the "
            "surface went rather than letting the denominator shrink",
        )

    def test_every_inventoried_reader_exists_exactly_once_and_never_re_sorts(self) -> None:
        offenders: list[str] = []
        for relative, readers in _INVENTORY.items():
            source = _stripped_source(_WEB_SRC / relative)
            for name in readers:
                declarations = re.findall(
                    _DECLARATION.format(name=name), source, flags=re.MULTILINE
                )
                if not declarations:
                    offenders.append(f"{relative}: {name} is no longer exported")
                    continue
                if len(declarations) > 1:
                    offenders.append(f"{relative}: {name} is exported more than once")
                    continue
                body = _function_body(source, name)
                if body is None:
                    offenders.append(f"{relative}: {name} has no closable body")
                elif _ORDERING.search(body):
                    offenders.append(f"{relative}: {name} re-sorts recorded data")
        self.assertEqual(
            offenders,
            [],
            "a list built from the bundle export or another ordered read was re-sorted; "
            "the record's order is part of the answer (SPEC.md § CompanyBundle) and a "
            "client-side sort overrules it",
        )


class DetectorNegativeControlTests(unittest.TestCase):
    """A guard nobody has seen fail is not a guard."""

    def test_the_detector_catches_a_deliberate_regression(self) -> None:
        fixture = (
            "/** alphabetical */\n"
            "export function projectsOf(document): Project[] {\n"
            "  const found = collect(document);\n"
            "  return [...found].sort((a, b) => a.key.localeCompare(b.key));\n"
            "}\n"
        )
        body = _function_body(fixture, "projectsOf")
        self.assertIsNotNone(body)
        self.assertTrue(_ORDERING.search(body or ""))

    def test_a_clean_reader_passes_the_detector(self) -> None:
        fixture = (
            "// prose mentioning sort must not trip the scan\n"
            "export function workProjectsIn(document): readonly string[] {\n"
            "  const seen = new Set<string>();\n"
            "  const projects: string[] = [];\n"
            "  return projects;\n"
            "}\n"
        )
        body = _function_body(fixture, "workProjectsIn")
        self.assertIsNotNone(body)
        self.assertFalse(_ORDERING.search(body or ""))

    def test_a_missing_reader_fails_closed(self) -> None:
        self.assertIsNone(_function_body("export const elsewhere = 1;\n", "projectsOf"))

    def test_a_destructured_component_body_is_scanned(self) -> None:
        fixture = (
            "export function TicketTable({\n"
            "  cards,\n"
            "  onOpen,\n"
            "}: {\n"
            "  readonly cards: readonly BoardCard[];\n"
            "  readonly onOpen: (card: BoardCard) => void;\n"
            "}): ReactElement {\n"
            "  return <tbody>{[...cards].sort().map(render)}</tbody>;\n"
            "}\n"
        )
        body = _function_body(fixture, "TicketTable")
        self.assertIn("return <tbody>", body or "")
        self.assertTrue(_ORDERING.search(body or ""))


if __name__ == "__main__":
    unittest.main()
