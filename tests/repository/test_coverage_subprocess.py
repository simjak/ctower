"""Executable proof that the repository coverage gate measures Python children."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from coverage import Coverage

_ROOT = Path(__file__).parents[2]
_MEASURED_MODULE = _ROOT / "tools/checks/playwright.py"


def _unique_line_number(path: Path, snippet: str) -> int:
    matches = [
        line_number
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if snippet in line
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {snippet!r} line in {path}, found {matches}")
    return matches[0]


class CoverageSubprocessTests(unittest.TestCase):
    def test_canonical_coverage_run_measures_child_only_project_code(self) -> None:
        coverage = Coverage.current()
        if coverage is None:
            self._assert_focused_canonical_run()
            return
        assert coverage is not None
        child_only_line = _unique_line_number(_MEASURED_MODULE, "return candidate")
        measured_before = coverage.get_data().lines(str(_MEASURED_MODULE.resolve())) or []
        self.assertNotIn(child_only_line, measured_before)

        result = subprocess.run(
            (
                sys.executable,
                "-c",
                "from pathlib import Path; "
                "from tools.checks.playwright import _external_temporary_parent; "
                "result = _external_temporary_parent(Path.cwd()); "
                "assert result != Path.cwd()",
            ),
            cwd=_ROOT,
            env=os.environ.copy(),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        coverage.combine(strict=True)
        measured_after = coverage.get_data().lines(str(_MEASURED_MODULE.resolve())) or []
        self.assertIn(child_only_line, measured_after)

    def _assert_focused_canonical_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ctower-coverage-") as temporary_name:
            environment = os.environ.copy()
            environment["COVERAGE_FILE"] = str(Path(temporary_name) / "coverage")
            result = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "--cov=tools.checks",
                    "--cov-branch",
                    "--cov-report=",
                    "--cov-fail-under=0",
                    "tests/repository/test_coverage_subprocess.py",
                ),
                cwd=_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
