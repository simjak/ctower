"""Exit-status integrity for the gate recipes that build scratch files.

`pytest-cov` decides `--cov-fail-under` on `round(total, report precision)` but prints its
verdict on the raw total, so at this repository's precision 0 every total in
`[threshold - 0.5, threshold)` prints `FAIL ... not reached` and still exits 0. A gate that
trusts that exit status reports success while printing its own failure. These tests hold
every coverage gate to a verdict that cannot disagree with its exit status, hold every
scratch recipe to propagating an inner failure, and hold the intended-tree secret scan to
refusing an empty or partial corpus instead of reporting a clean scan of nothing.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

__all__ = ()

_JUSTFILE = Path(__file__).parents[2] / "justfile"
_COVERAGE_RECIPES = ("compatibility-coverage", "product-coverage", "verify")
_SCRATCH_RECIPES = (
    "compatibility-coverage",
    "product-coverage",
    "docs-check",
    "codegen-check",
    "secrets-intended-tree",
    "verify",
)
_INNER_FAILURE_STATUS = 42
_REQUIRED_COVERAGE = 90.0


def _executable(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(f"{name} is required by this test")
    return resolved


def _run(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed shell, command text authored in this repository
        (_executable("bash"), "-euo", "pipefail", "-c", command),
        cwd=cwd,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )


def _justfile_variable(name: str) -> str:
    prefix = f"{name} := "
    for line in _JUSTFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip().removeprefix('"').removesuffix('"')
    raise AssertionError(f"justfile defines no {name} variable")


def _recipe_body(recipe: str) -> list[str]:
    lines = _JUSTFILE.read_text(encoding="utf-8").splitlines()
    declarations = [index for index, line in enumerate(lines) if line.startswith(f"{recipe}:")]
    if len(declarations) != 1:
        raise AssertionError(f"expected exactly one {recipe} recipe")
    body: list[str] = []
    for line in lines[declarations[0] + 1 :]:
        if line and not line.startswith((" ", "\t")):
            break
        if line.startswith(("    ", "\t")):
            body.append(line.strip())
    return body


def _scratch_line(recipe: str) -> str:
    scratch = [line for line in _recipe_body(recipe) if "mktemp" in line]
    if len(scratch) != 1:
        raise AssertionError(f"expected exactly one scratch line in {recipe}")
    return scratch[0].removeprefix("@")


def _initialize_repository(root: Path) -> None:
    subprocess.run(  # noqa: S603 - fixed executable, generated arguments
        (_executable("git"), "init", "--quiet"),
        cwd=root,
        capture_output=True,
        check=True,
    )


class CoverageVerdictTests(unittest.TestCase):
    def test_exact_verdict_refuses_totals_pytest_cov_rounds_up_to_the_threshold(self) -> None:
        gate = _justfile_variable("coverage_gate")
        cases = (
            (89.75, True),
            (89.999, True),
            (89.5, True),
            (_REQUIRED_COVERAGE, False),
            (90.6977, False),
        )
        with tempfile.TemporaryDirectory() as name:
            workspace = Path(name)
            report = workspace / "coverage.json"
            for total, refused in cases:
                with self.subTest(total=total):
                    report.write_text(
                        json.dumps({"totals": {"percent_covered": total}}), encoding="utf-8"
                    )
                    observed = self._run_gate(gate, report, workspace)

                    self.assertEqual(observed.returncode != 0, refused, observed)
                    self.assertIn(f"{total:.4f}%", observed.stdout + observed.stderr)

    def test_every_coverage_recipe_pairs_pytest_with_the_exact_verdict(self) -> None:
        for recipe in _COVERAGE_RECIPES:
            with self.subTest(recipe=recipe):
                line = _scratch_line(recipe)

                self.assertIn("--cov-fail-under=90", line)
                self.assertIn('--cov-report=json:"$report_file"', line)
                self.assertTrue(
                    line.endswith('{{python}} -c "{{coverage_gate}}" "$report_file" 90'), line
                )

    def _run_gate(
        self, gate: str, report: Path, workspace: Path
    ) -> subprocess.CompletedProcess[str]:
        command = " ".join(
            (
                shlex.quote(_executable("python3")),
                "-c",
                shlex.quote(gate),
                shlex.quote(str(report)),
                str(_REQUIRED_COVERAGE),
            )
        )
        return _run(command, workspace)


class ScratchRecipeExitStatusTests(unittest.TestCase):
    def test_every_scratch_recipe_fails_when_its_inner_command_fails(self) -> None:
        failing = " ".join(
            (
                shlex.quote(_executable("python3")),
                "-c",
                shlex.quote(f"raise SystemExit({_INNER_FAILURE_STATUS})"),
            )
        )
        for recipe in _SCRATCH_RECIPES:
            with self.subTest(recipe=recipe), tempfile.TemporaryDirectory() as name:
                workspace = Path(name)
                _initialize_repository(workspace)
                (workspace / "corpus.txt").write_text("corpus\n", encoding="utf-8")
                command = (
                    _scratch_line(recipe)
                    .replace("{{python}}", failing)
                    .replace("{{gitleaks}}", failing)
                )

                observed = _run(command, workspace)

                self.assertEqual(observed.returncode, _INNER_FAILURE_STATUS, observed)


class SecretScanCorpusTests(unittest.TestCase):
    def test_listing_is_materialized_through_a_status_checked_file(self) -> None:
        line = _scratch_line("secrets-intended-tree")

        self.assertNotIn("< <(git ls-files", line)
        self.assertIn('git ls-files --cached --others --exclude-standard -z > "$file_list"', line)

    def test_complete_corpus_scans_and_reports_its_own_size(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            workspace = Path(name)
            _initialize_repository(workspace)
            (workspace / "corpus.txt").write_text("corpus\n", encoding="utf-8")
            (workspace / ".gitleaks.toml").write_text("", encoding="utf-8")
            marker = workspace / "scanned.marker"

            observed = self._run_scan(workspace, marker, exit_status=0)

            self.assertEqual(observed.returncode, 0, observed)
            self.assertIn("secret scan corpus: listed=2 scanned=2", observed.stdout)
            self.assertTrue(marker.exists(), observed)

    def test_empty_corpus_refuses_instead_of_reporting_a_clean_scan(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            workspace = Path(name)
            _initialize_repository(workspace)
            marker = workspace / "scanned.marker"

            observed = self._run_scan(workspace, marker, exit_status=0)

            self.assertNotEqual(observed.returncode, 0, observed)
            self.assertIn("refusing to report a clean scan", observed.stderr)
            self.assertFalse(marker.exists(), "the scanner must not run on an empty corpus")

    def test_unlistable_tree_fails_instead_of_scanning_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            workspace = Path(name)
            marker = workspace / "scanned.marker"

            observed = self._run_scan(workspace, marker, exit_status=0)

            self.assertNotEqual(observed.returncode, 0, observed)
            self.assertFalse(marker.exists(), "the scanner must not run without a listing")

    def _run_scan(
        self, workspace: Path, marker: Path, *, exit_status: int
    ) -> subprocess.CompletedProcess[str]:
        scanner = " ".join(
            (
                shlex.quote(_executable("python3")),
                "-c",
                shlex.quote(
                    "import pathlib, sys;"
                    f" pathlib.Path({str(marker)!r}).write_text('scanned', encoding='utf-8');"
                    f" sys.exit({exit_status})"
                ),
            )
        )
        return _run(
            _scratch_line("secrets-intended-tree").replace("{{gitleaks}}", scanner), workspace
        )


if __name__ == "__main__":
    unittest.main()
