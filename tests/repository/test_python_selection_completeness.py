"""Repository contract: every Python path in the intended tree is selected by a gate.

T-014 — the fleet gate rule one layer down: `just python-check` names its Python
paths BY HAND, three times (ruff format, ruff check, mypy), and suite execution is
selected by `tools/checks/expected-suites.toml`. A file absent from every selector
ships lint-free, type-free, and unexecuted while the release gate reports the same
SUCCESS it reports for gated code — "a check that stops looking reports identically
to one that looked".

This test derives the intended tree from `git ls-files` (never a hand list) and
asserts:

1. every tracked ``*.py`` outside the documented exclusions (``generated/`` is
   mypy-only by design, ``tests/repository/fixtures`` holds deliberate broken
   sources) is selected by at least one of: a ruff-format path, a ruff-check
   path, a mypy path, or a suite whose ``patterns`` claim it;
2. every tracked ``test_*.py`` living under some suite's ``path`` is claimed by
   that suite's ``patterns`` — a directory LOOKING gated while its explicit file
   enumeration silently omits a module is the same defect one level deeper.
"""

from __future__ import annotations

import fnmatch
import subprocess
import tomllib
import unittest
from pathlib import Path
from typing import cast

_DOCUMENTED_EXCLUSIONS = ("generated/", "tests/repository/fixtures/")


class PythonSelectionCompletenessTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_every_tracked_python_path_is_selected_by_some_gate(self) -> None:
        lint_paths = self._lint_selection_paths()
        unselected: list[str] = []
        for path in self._tracked_python_files():
            if path.startswith(_DOCUMENTED_EXCLUSIONS):
                continue
            if self._lint_selects(path, lint_paths) or self._suite_claims(path):
                continue
            unselected.append(path)
        self.assertEqual(
            unselected,
            [],
            "tracked Python paths selected by NO gate (lint/format/mypy/suite):\n  "
            + "\n  ".join(unselected),
        )

    def test_every_suite_path_test_module_is_claimed_by_that_suites_patterns(self) -> None:
        orphans: list[str] = []
        for path in self._tracked_python_files():
            name = Path(path).name
            if not name.startswith("test_"):
                continue
            if not self._suite_claims(path):
                orphans.append(path)
        self.assertEqual(
            orphans,
            [],
            "test modules matched by NO suite patterns:\n  " + "\n  ".join(orphans),
        )

    def _tracked_python_files(self) -> list[str]:
        completed = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "--", "*.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        return sorted(line for line in completed.stdout.splitlines() if line)

    def _lint_selection_paths(self) -> set[str]:
        """Path arguments named by the three python-check lines, derived from justfile."""
        justfile = (self.root / "justfile").read_text(encoding="utf-8")
        lines = justfile.splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith("python-check:")]
        assert len(starts) == 1, "expected exactly one python-check recipe"
        paths: set[str] = set()
        commands = (
            "{{python}} -m ruff format",
            "{{python}} -m ruff check",
            "{{python}} -m mypy",
        )
        for line in lines[starts[0] + 1 :]:
            if line and not line.startswith((" ", "\t")):
                break
            stripped = line.strip()
            if not any(stripped.startswith(command) for command in commands):
                continue
            for token in stripped.split()[3:]:
                if token.startswith("-") or "=" in token:
                    continue
                paths.add(token.rstrip("/"))
        return paths

    def _lint_selects(self, path: str, lint_paths: set[str]) -> bool:
        """A selection argument covers a path when it is the path or an ancestor dir."""
        parts = path.split("/")
        return any(
            "/".join(parts[:i]) in lint_paths for i in range(1, len(parts) + 1)
        )

    def _suites(self) -> list[dict[str, object]]:
        with (self.root / "tools/checks/expected-suites.toml").open("rb") as handle:
            return cast(list[dict[str, object]], tomllib.load(handle)["suite"])

    def _suite_claims(self, path: str) -> bool:
        for suite in self._suites():
            prefix = cast(str, suite["path"]).rstrip("/") + "/"
            if not path.startswith(prefix):
                continue
            patterns = cast(list[str], suite["patterns"])
            if any(fnmatch.fnmatch(Path(path).name, pattern) for pattern in patterns):
                return True
        return False


if __name__ == "__main__":
    unittest.main()
