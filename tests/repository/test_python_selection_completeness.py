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
   enumeration silently omits a module is the same defect one level deeper;
3. every ``--exclude`` on a ``python-check`` line is DELIBERATE: named in
   ``_DELIBERATE_LINT_EXCLUSIONS`` below with an owner-held reason. An exclusion
   the guard merely tolerates silently is T-032's hole — the next ``--exclude``
   of a path no other line names would ship unseen while every gate reports
   SUCCESS, so the guard parses the exclusions instead of counting their
   arguments as selected paths.
"""

from __future__ import annotations

import fnmatch
import subprocess
import tomllib
import unittest
from pathlib import Path
from typing import cast

_DOCUMENTED_EXCLUSIONS = ("generated/", "tests/repository/fixtures/")

# Deliberate, owner-held `--exclude` arguments on the python-check lines.
# Every exclusion the justfile carries MUST be named here with its reason, and
# every name here MUST still be live on a python-check line — an exclusion is
# never selected-by-accident and never outlives its reason silently.
_DELIBERATE_LINT_EXCLUSIONS = {
    "tests/acceptance/increment-1/conftest.py": (
        "two conftest modules share this basename and mypy's module discovery "
        "cannot disambiguate them without MYPYPATH/explicit-package-bases "
        "rework (T-032); the file stays format- and lint-checked by both ruff "
        "lines."
    ),
}


class PythonSelectionCompletenessTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_every_lint_exclusion_is_deliberate(self) -> None:
        _, exclusions = self._lint_selection()
        unrecorded = sorted(exclusions - set(_DELIBERATE_LINT_EXCLUSIONS))
        self.assertEqual(
            unrecorded,
            [],
            "--exclude arguments on python-check lines that NO deliberate "
            "exception records (add the path to _DELIBERATE_LINT_EXCLUSIONS "
            "with a reason, or drop the exclusion):\n  " + "\n  ".join(unrecorded),
        )
        stale = sorted(set(_DELIBERATE_LINT_EXCLUSIONS) - exclusions)
        self.assertEqual(
            stale,
            [],
            "_DELIBERATE_LINT_EXCLUSIONS names paths no python-check line "
            "excludes anymore (drop the stale entries):\n  " + "\n  ".join(stale),
        )

    def test_every_tracked_python_path_is_selected_by_some_gate(self) -> None:
        lint_lines, _ = self._lint_selection()
        unselected: list[str] = []
        for path in self._tracked_python_files():
            if path.startswith(_DOCUMENTED_EXCLUSIONS):
                continue
            if any(self._line_selects(path, line) for line in lint_lines):
                continue
            if self._suite_claims(path):
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
        completed = subprocess.run(  # noqa: S603 - fixed repository introspection command
            ["/usr/bin/git", "-C", str(self.root), "ls-files", "--", "*.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        return sorted(line for line in completed.stdout.splitlines() if line)

    def _lint_selection(self) -> tuple[list[dict[str, set[str]]], set[str]]:
        """Per-line path selections and the union of --exclude arguments.

        Derived from the justfile's three python-check commands. A ``--exclude``
        argument is returned as an EXCLUSION, never as a selected path: the
        guard's notion of "selected" matches the command's (T-032).
        """
        justfile = (self.root / "justfile").read_text(encoding="utf-8")
        lines = justfile.splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith("python-check:")]
        assert len(starts) == 1, "expected exactly one python-check recipe"
        selections: list[dict[str, set[str]]] = []
        exclusions: set[str] = set()
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
            paths: set[str] = set()
            line_exclusions: set[str] = set()
            tokens = stripped.split()[3:]
            index = 0
            while index < len(tokens):
                token = tokens[index]
                index += 1
                if token.startswith("--exclude"):
                    value = token.removeprefix("--exclude=")
                    if value == token and index < len(tokens):
                        value = tokens[index]
                        index += 1
                    line_exclusions.add(value.rstrip("/"))
                    exclusions.add(value.rstrip("/"))
                    continue
                if token.startswith("-") or "=" in token:
                    continue
                paths.add(token.rstrip("/"))
            selections.append({"paths": paths, "excludes": line_exclusions})
        return selections, exclusions

    def _line_selects(self, path: str, line: dict[str, set[str]]) -> bool:
        """A line selects a path when it names the path or an ancestor dir and
        does not exclude the path or one of its ancestors."""
        parts = path.split("/")
        prefixes = {"/".join(parts[:i]) for i in range(1, len(parts) + 1)}
        if prefixes & line["excludes"]:
            return False
        return bool(prefixes & line["paths"])

    def _suites(self) -> list[dict[str, object]]:
        with (self.root / "tools/checks/expected-suites.toml").open("rb") as handle:
            return cast(list[dict[str, object]], tomllib.load(handle)["suite"])

    def _suite_claims(self, path: str) -> bool:
        for suite in self._suites():
            prefix = cast(str, suite["path"]).rstrip("/") + "/"
            command_named = any(
                str(argument) == path for argument in cast(list[str], suite.get("command", []))
            )
            if not (path.startswith(prefix) or command_named):
                continue
            patterns = cast(list[str], suite["patterns"])
            if any(fnmatch.fnmatch(Path(path).name, pattern) for pattern in patterns):
                return True
        return False


if __name__ == "__main__":
    unittest.main()
