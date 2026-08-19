"""An authored identifier is minted once, and a second mint is a merge defect.

Three append-only registries hand out identifiers by hand: `docs/internal/SPEC.md` mints
`CT-<increment>-<nnn>` backlog rows, `docs/internal/DECISIONS.md` mints `## D<n>` headings, and
`packages/ctower-kernel/migrations/` mints four-digit migration numbers. Two branches that both take
the next free number append at the same tail, so git resolves them as adjacent inserts with no
conflict marker; on 2026-08-17 and 2026-08-18 three such merges landed a duplicate
(PR #527 versus #519, #527 versus #516, #519 versus #516) and every gate stayed green. The
migration leg landed the same way — PR #506 and PR #530 both minted `0076` — and needed
`fix(migrations): take 0077 for the inbox severity migration and re-attest` to repair it. Readers
caught all four; nothing mechanical did.

The distinction this gate has to carry is that a *reference* is not a mint. `CT-I1-009` through
`CT-I1-013` are each written twice in the shipped backlog table — once in the first cell of the row
that defines them, and once in the dependency cell of the row that follows — and that shape is
correct. Only the first cell of a row mints, only a heading mints a decision, and only a filename
mints a migration number; a citation in prose, a dependency cell, or a line inside a code fence
mints nothing.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from tools.checks import verify

if TYPE_CHECKING:
    from tools.checks import Finding, PolicyReport

_STABLE_ID_REFUSAL = "mint.duplicate-stable-id"
_DECISION_REFUSAL = "mint.duplicate-decision"
_MIGRATION_REFUSAL = "mint.duplicate-migration"
_REFUSALS = frozenset({_STABLE_ID_REFUSAL, _DECISION_REFUSAL, _MIGRATION_REFUSAL})

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).parent / "fixtures"
_CANONICAL_POLICY = _ROOT / "tools/checks/policy.toml"
_SPEC = "docs/internal/SPEC.md"
_DECISIONS = "docs/internal/DECISIONS.md"
_MIGRATIONS = "packages/ctower-kernel/migrations"


def _row(identifier: str, goal: str, dependency: str) -> str:
    return f"| {identifier} | {goal} | {dependency} |\n"


def _backlog(*rows: str) -> str:
    """One SPEC-shaped document carrying exactly the given backlog rows."""

    return (
        "# ctower — canonical system specification\n\n"
        "### I1 implementation backlog\n\n"
        "| Stable ID | Goal | Dependencies |\n"
        "|---|---|---|\n"
        f"{''.join(rows)}"
    )


def _line_of(document: str, row: str) -> int:
    return document.splitlines().index(row.rstrip("\n")) + 1


_CATALOG_GOAL = "Deliver one authenticated Knowledge catalog discovery read."
_ROLE_GOAL = "Deliver the authenticated role record as a derived read."
_REVIEW_GOAL = "Deliver the tracked review-record rescue."
_ROUTINE_ROW = _row("CT-I1-035", "Deliver Routine work items.", "CT-I1-027")


def _stable_id_collisions() -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    """The two real SPEC collisions, as the auto-merged trees actually carried them."""

    return (
        (
            "pr-519-catalog-versus-pr-527-role-record",
            "CT-I1-036",
            _row("CT-I1-036", _ROLE_GOAL, "CT-I1-013"),
            (
                _ROUTINE_ROW,
                _row("CT-I1-036", _CATALOG_GOAL, "CT-I1-030"),
                _row("CT-I1-036", _ROLE_GOAL, "CT-I1-013"),
            ),
        ),
        (
            "pr-519-catalog-versus-pr-516-review-records",
            "CT-I1-037",
            _row("CT-I1-037", _REVIEW_GOAL, "CT-I1-027"),
            (
                _row("CT-I1-037", _CATALOG_GOAL, "CT-I1-030"),
                _row("CT-I1-037", _REVIEW_GOAL, "CT-I1-027"),
            ),
        ),
    )


def _dependency_chain() -> tuple[str, ...]:
    """The shipped `CT-I1-009..013` rows: every identifier written twice, none minted twice."""

    return (
        _row("CT-I1-009", "Implement immutable Ticket Project identity.", "CT-I1-008"),
        _row("CT-I1-010", "Configure one tenant with three Projects.", "CT-I1-009"),
        _row("CT-I1-011", "Admit the reviewed manibo backlog one item at a time.", "CT-I1-010"),
        _row("CT-I1-012", "Publish the project-scoped typed event feed.", "CT-I1-011"),
        _row("CT-I1-013", "Reuse the provider-agnostic OIDC modules.", "CT-I1-012"),
    )


_DECISIONS_TITLE = "# ctower — locked decisions & working assumptions\n\n"
_D68_ROLE_FACTS = "## D68 — Workflow stage participants resolve from authenticated role facts\n"
_D68_REVIEW_RECORDS = "## D68 — Tracked review records are one verdict per exact head\n"
_SETEXT_REVIEW_RECORDS = _D68_REVIEW_RECORDS.removeprefix("## ")
_SETEXT_LEVEL_TWO = "-" * 62 + "\n"
_SETEXT_LEVEL_ONE = "=" * 62 + "\n"

_DECISION_COLLISION = (
    f"{_DECISIONS_TITLE}"
    f"{_D68_ROLE_FACTS}\nStage participants resolve from role facts.\n\n"
    f"{_D68_REVIEW_RECORDS}\nA review record is one verdict per exact head.\n"
)

_QUOTED_IDENTIFIERS = (
    f"{_DECISIONS_TITLE}"
    f"{_D68_ROLE_FACTS}\nThis entry supersedes D68's earlier draft and reuses CT-I1-036.\n\n"
    "```markdown\n"
    "## D68 — an example heading, not a mint\n"
    "| CT-I1-036 | an example row, not a mint | CT-I1-013 |\n"
    "```\n\n"
    "<!--\n## D68 — a commented heading, not a mint\n-->\n"
)

_SPAWN_MIGRATION = "0076_spawn_records.sql"
_INBOX_MIGRATION_COLLIDING = "0076_inbox_message_severity.sql"
_INBOX_MIGRATION_RENUMBERED = "0077_inbox_message_severity.sql"


class MintedIdentityTests(unittest.TestCase):
    """Every authored registry refuses a second mint and admits every reference."""

    def test_both_real_stable_id_collisions_refuse_the_second_mint(self) -> None:
        for label, identifier, duplicate, rows in _stable_id_collisions():
            with self.subTest(label=label):
                document = _backlog(*rows)
                with _repository() as root:
                    _write(root, _SPEC, document)

                    report = verify(root, "full")

                self.assertFalse(report.ok, report.findings)
                self.assertEqual(
                    [(item.rule_id, item.path, item.line) for item in _refusals(report)],
                    [(_STABLE_ID_REFUSAL, _SPEC, _line_of(document, duplicate))],
                    report.findings,
                )
                self.assertIn(identifier, _refusals(report)[0].message)

    def test_the_shipped_dependency_double_listing_is_admitted(self) -> None:
        with _repository() as root:
            _write(root, _SPEC, _backlog(*_dependency_chain()))

            report = verify(root, "full")

        self.assertEqual(_refusals(report), ())
        self.assertTrue(report.ok, report.findings)

    def test_one_collision_beside_the_dependency_chain_refuses_only_itself(self) -> None:
        _, _, duplicate, rows = _stable_id_collisions()[0]
        document = _backlog(*_dependency_chain(), *rows)
        with _repository() as root:
            _write(root, _SPEC, document)

            report = verify(root, "full")

        self.assertEqual(
            [(item.rule_id, item.path, item.line) for item in _refusals(report)],
            [(_STABLE_ID_REFUSAL, _SPEC, _line_of(document, duplicate))],
            report.findings,
        )

    def test_the_real_decision_collision_refuses_the_second_mint(self) -> None:
        with _repository() as root:
            _write(root, _DECISIONS, _DECISION_COLLISION)

            report = verify(root, "full")

        self.assertFalse(report.ok, report.findings)
        self.assertEqual(
            [(item.rule_id, item.path, item.line) for item in _refusals(report)],
            [(_DECISION_REFUSAL, _DECISIONS, _line_of(_DECISION_COLLISION, _D68_REVIEW_RECORDS))],
            report.findings,
        )

    def test_citations_code_fences_and_comments_mint_nothing(self) -> None:
        with _repository() as root:
            _write(root, _DECISIONS, _QUOTED_IDENTIFIERS)
            _write(root, _SPEC, _backlog(_row("CT-I1-036", _ROLE_GOAL, "CT-I1-013")))

            report = verify(root, "full")

        self.assertEqual(_refusals(report), ())
        self.assertTrue(report.ok, report.findings)

    def test_the_real_migration_collision_refuses_the_second_mint(self) -> None:
        with _repository() as root:
            _write(root, f"{_MIGRATIONS}/{_SPAWN_MIGRATION}", "-- spawn records\n")
            _write(root, f"{_MIGRATIONS}/{_INBOX_MIGRATION_COLLIDING}", "-- inbox severity\n")

            report = verify(root, "full")

        self.assertFalse(report.ok, report.findings)
        self.assertEqual(
            [(item.rule_id, item.path) for item in _refusals(report)],
            [(_MIGRATION_REFUSAL, f"{_MIGRATIONS}/{_SPAWN_MIGRATION}")],
            report.findings,
        )
        self.assertIn(_INBOX_MIGRATION_COLLIDING, _refusals(report)[0].message)

    def test_the_renumbering_that_repaired_the_migration_collision_is_admitted(self) -> None:
        with _repository() as root:
            _write(root, f"{_MIGRATIONS}/{_SPAWN_MIGRATION}", "-- spawn records\n")
            _write(root, f"{_MIGRATIONS}/{_INBOX_MIGRATION_RENUMBERED}", "-- inbox severity\n")
            _write(root, f"{_MIGRATIONS}/manifest.json", "{}\n")

            report = verify(root, "full")

        self.assertEqual(_refusals(report), ())
        self.assertTrue(report.ok, report.findings)

    def test_the_authored_registries_mint_every_identifier_once(self) -> None:
        with _repository() as root:
            for relative in (_SPEC, _DECISIONS):
                _write(root, relative, (_ROOT / relative).read_text(encoding="utf-8"))
            for migration in sorted((_ROOT / _MIGRATIONS).glob("*.sql")):
                _write(root, f"{_MIGRATIONS}/{migration.name}", "")

            report = verify(root, "full")

        self.assertEqual(_refusals(report), ())

    def test_a_second_mint_is_not_waivable(self) -> None:
        with _repository(policy_source=_CANONICAL_POLICY) as root:
            self._write_collision(root)
            self._write_valid_exception(root)

            self._assert_non_waivable_report(root)

    def test_non_waivable_regression_detects_canonical_policy_removal(self) -> None:
        with _repository(policy_source=_CANONICAL_POLICY) as root:
            self._write_collision(root)
            self._write_valid_exception(root)

            policy = root / "tools/checks/policy.toml"
            text = policy.read_text(encoding="utf-8")
            entry = f'  "{_STABLE_ID_REFUSAL}",\n'
            self.assertEqual(text.count(entry), 1)
            policy.write_text(text.replace(entry, "", 1), encoding="utf-8")

            with self.assertRaises(AssertionError):
                self._assert_non_waivable_report(root)

    @staticmethod
    def _write_collision(root: Path) -> None:
        _write(root, _SPEC, _backlog(*_stable_id_collisions()[0][3]))

    @staticmethod
    def _write_valid_exception(root: Path) -> None:
        today = datetime.now(UTC).date()
        exception = {
            "schema": "ctower.repository-exceptions/v1",
            "exceptions": [
                {
                    "id": "CT-TEST-536",
                    "rule": _STABLE_ID_REFUSAL,
                    "path": _SPEC,
                    "temporary_limit": 1,
                    "owner": "test-owner",
                    "reason": "prove a second mint cannot be waived",
                    "ticket": "CT-TEST-536",
                    "approver": "independent-reviewer",
                    "created_on": today.isoformat(),
                    "expires_on": (today + timedelta(days=7)).isoformat(),
                }
            ],
        }
        (root / "tools/checks/exceptions.yaml").write_text(json.dumps(exception), encoding="utf-8")

    def _assert_non_waivable_report(self, root: Path) -> None:
        report = verify(root, "full")

        self.assertFalse(report.ok, report.findings)
        self.assertTrue(
            any(
                item.rule_id == _STABLE_ID_REFUSAL and item.path == _SPEC for item in report.errors
            ),
            report.findings,
        )
        self.assertFalse(
            any(
                item.rule_id == _STABLE_ID_REFUSAL and item.path == _SPEC
                for item in report.warnings
            ),
            report.findings,
        )


class RenderedMintShapeTests(unittest.TestCase):
    """A mint is whatever CommonMark renders as one, never whatever starts at column zero.

    GitHub renders a table row indented up to three spaces as a row, an ATX heading indented up
    to three spaces as a heading, and an underlined line carrying no `#` at all as a heading.
    Each shape hands out the identifier a reader sees, so each one has to be a mint here; a
    fourth space turns all of them into an indented code block, which quotes rather than mints.
    """

    def test_an_indented_backlog_row_refuses_the_second_mint(self) -> None:
        duplicate = "  " + _row("CT-I1-036", _ROLE_GOAL, "CT-I1-013")
        document = _backlog(_row("CT-I1-036", _CATALOG_GOAL, "CT-I1-030"), duplicate)
        with _repository() as root:
            _write(root, _SPEC, document)

            report = verify(root, "full")

        self.assertEqual(
            [(item.rule_id, item.path, item.line) for item in _refusals(report)],
            [(_STABLE_ID_REFUSAL, _SPEC, _line_of(document, duplicate))],
            report.findings,
        )

    def test_an_indented_decision_heading_refuses_the_second_mint(self) -> None:
        self._assert_decision_collision_refuses("  " + _D68_REVIEW_RECORDS)

    def test_a_setext_decision_heading_refuses_the_second_mint(self) -> None:
        self._assert_decision_collision_refuses(_SETEXT_REVIEW_RECORDS + _SETEXT_LEVEL_TWO)

    def test_a_setext_level_one_decision_heading_refuses_the_second_mint(self) -> None:
        self._assert_decision_collision_refuses(_SETEXT_REVIEW_RECORDS + _SETEXT_LEVEL_ONE)

    def test_a_four_space_indent_quotes_the_line_and_mints_nothing(self) -> None:
        document = (
            f"{_DECISIONS_TITLE}{_D68_ROLE_FACTS}\nStage participants resolve from role facts.\n\n"
            f"    {_D68_REVIEW_RECORDS}"
        )
        with _repository() as root:
            _write(root, _DECISIONS, document)
            _write(
                root,
                _SPEC,
                _backlog(
                    _row("CT-I1-036", _CATALOG_GOAL, "CT-I1-030"),
                    "    " + _row("CT-I1-036", _ROLE_GOAL, "CT-I1-013"),
                ),
            )

            report = verify(root, "full")

        self.assertEqual(_refusals(report), ())
        self.assertTrue(report.ok, report.findings)

    def test_a_quoted_heading_mints_nothing(self) -> None:
        """A `>` block quotes someone else's heading, so it declares nothing here."""

        document = (
            f"{_DECISIONS_TITLE}{_D68_ROLE_FACTS}\nStage participants resolve from role facts.\n\n"
            f"> {_D68_REVIEW_RECORDS}"
        )
        with _repository() as root:
            _write(root, _DECISIONS, document)

            report = verify(root, "full")

        self.assertEqual(_refusals(report), ())
        self.assertTrue(report.ok, report.findings)

    def _assert_decision_collision_refuses(self, duplicate: str) -> None:
        document = (
            f"{_DECISIONS_TITLE}{_D68_ROLE_FACTS}\nStage participants resolve from role facts.\n\n"
            f"{duplicate}\nA review record is one verdict per exact head.\n"
        )
        with _repository() as root:
            _write(root, _DECISIONS, document)

            report = verify(root, "full")

        self.assertEqual(
            [(item.rule_id, item.path, item.line) for item in _refusals(report)],
            [(_DECISION_REFUSAL, _DECISIONS, _line_of(document, duplicate.splitlines()[0]))],
            report.findings,
        )


@contextmanager
def _repository(policy_source: Path | None = None) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        shutil.copytree(_FIXTURES / "positive", root, dirs_exist_ok=True)
        if policy_source is not None:
            shutil.copyfile(policy_source, root / "tools/checks/policy.toml")
        yield root


def _refusals(report: PolicyReport) -> tuple[Finding, ...]:
    return tuple(item for item in report.findings if item.rule_id in _REFUSALS)


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
