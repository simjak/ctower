"""Playwright gate behavior through its package-script command boundary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from typing import cast
from unittest.mock import patch

from tools.checks.playwright import main as playwright_main


class PlaywrightGateTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_gate_routes_all_artifacts_outside_checkout_and_cleans_them(self) -> None:
        package = cast(
            dict[str, object], json.loads((self.root / "package.json").read_text(encoding="utf-8"))
        )
        scripts = cast(dict[str, str], package["scripts"])
        script = scripts["test:e2e"]
        self.assertEqual(script, "python3 -B -m tools.checks.playwright")

        for expected_exit in (0, 23):
            with self.subTest(expected_exit=expected_exit):
                self._assert_copied_checkout_is_unchanged(expected_exit)

    def test_public_main_propagates_status_without_checkout_mutation(self) -> None:
        for expected_exit in (0, 23):
            with (
                self.subTest(expected_exit=expected_exit),
                tempfile.TemporaryDirectory() as checkout_name,
                tempfile.TemporaryDirectory() as bin_name,
            ):
                checkout = Path(checkout_name)
                fake_pnpm = Path(bin_name) / "pnpm"
                fake_pnpm.write_text(self._fake_pnpm(), encoding="utf-8")
                fake_pnpm.chmod(0o755)
                environment = os.environ.copy()
                environment["PATH"] = f"{bin_name}{os.pathsep}{environment['PATH']}"
                environment["FAKE_PLAYWRIGHT_EXIT"] = str(expected_exit)
                environment["FAKE_PLAYWRIGHT_QUIET"] = "1"
                before = self._snapshot(checkout)

                with chdir(checkout), patch.dict(os.environ, environment, clear=True):
                    observed = playwright_main()

                self.assertEqual(observed, expected_exit)
                self.assertEqual(self._snapshot(checkout), before)

    def test_real_zero_test_invocation_fails(self) -> None:
        with chdir(self.root):
            result = playwright_main()

        self.assertNotEqual(result, 0)

    def test_public_main_rejects_overrides_and_missing_pnpm(self) -> None:
        with self.assertRaises(ValueError):
            playwright_main(("override",))
        with tempfile.TemporaryDirectory() as checkout_name:
            checkout = Path(checkout_name)
            environment = os.environ.copy()
            environment["PATH"] = ""
            with (
                chdir(checkout),
                patch.dict(os.environ, environment, clear=True),
                self.assertRaises(RuntimeError),
            ):
                playwright_main()

    def _assert_copied_checkout_is_unchanged(self, expected_exit: int) -> None:
        with (
            tempfile.TemporaryDirectory() as checkout_name,
            tempfile.TemporaryDirectory() as bin_name,
        ):
            checkout = Path(checkout_name)
            self._copy_module(checkout)
            fake_pnpm = Path(bin_name) / "pnpm"
            fake_pnpm.write_text(self._fake_pnpm(), encoding="utf-8")
            fake_pnpm.chmod(0o755)
            (checkout / ".gitignore").write_text(
                "playwright-report/\ntest-results/\ntools/**/__pycache__/\nignored-tmp/\n",
                encoding="utf-8",
            )
            checkout_temp = checkout / "ignored-tmp"
            checkout_temp.mkdir()
            before = self._snapshot(checkout)
            environment = os.environ.copy()
            environment["PATH"] = f"{bin_name}{os.pathsep}{environment['PATH']}"
            environment.pop("PYTHONPATH", None)
            environment["TMPDIR"] = str(checkout_temp)
            environment["FAKE_PLAYWRIGHT_EXIT"] = str(expected_exit)

            result = subprocess.run(
                (sys.executable, "-B", "-m", "tools.checks.playwright"),
                cwd=checkout,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            after = self._snapshot(checkout)

        self.assertEqual(result.returncode, expected_exit, result)
        self.assertEqual(after, before)
        artifact_paths = tuple(Path(line) for line in result.stdout.splitlines() if line)
        self.assertEqual(len(artifact_paths), 2, result.stdout)
        self.assertTrue(all(not path.is_relative_to(checkout) for path in artifact_paths))
        self.assertTrue(all(not path.exists() for path in artifact_paths))

    def _copy_module(self, checkout: Path) -> None:
        module_root = checkout / "tools/checks"
        module_root.mkdir(parents=True)
        (checkout / "tools/__init__.py").write_text("", encoding="utf-8")
        (module_root / "__init__.py").write_text("", encoding="utf-8")
        shutil.copyfile(self.root / "tools/checks/playwright.py", module_root / "playwright.py")

    def _snapshot(self, root: Path) -> dict[str, tuple[str, bytes]]:
        return {
            path.relative_to(root).as_posix(): self._snapshot_entry(path)
            for path in sorted(root.rglob("*"))
        }

    def _snapshot_entry(self, path: Path) -> tuple[str, bytes]:
        if path.is_symlink():
            return "symlink", path.readlink().as_posix().encode()
        if path.is_file():
            return "file", path.read_bytes()
        return "directory", b""

    def _fake_pnpm(self) -> str:
        return """#!/bin/sh
set -eu
test "$1" = "exec"
test "$2" = "playwright"
test "$3" = "test"
test "$4" = "--output"
test "$5" = "$PLAYWRIGHT_OUTPUT_DIR"
case "$PLAYWRIGHT_HTML_OUTPUT_DIR/" in "$PWD/"*) exit 91 ;; esac
case "$PLAYWRIGHT_OUTPUT_DIR/" in "$PWD/"*) exit 92 ;; esac
mkdir -p "$PLAYWRIGHT_HTML_OUTPUT_DIR" "$PLAYWRIGHT_OUTPUT_DIR"
printf 'report\n' > "$PLAYWRIGHT_HTML_OUTPUT_DIR/index.html"
printf 'result\n' > "$PLAYWRIGHT_OUTPUT_DIR/.last-run.json"
if test "${FAKE_PLAYWRIGHT_QUIET:-0}" != "1"; then
    printf '%s\n%s\n' "$PLAYWRIGHT_HTML_OUTPUT_DIR" "$PLAYWRIGHT_OUTPUT_DIR"
fi
exit "$FAKE_PLAYWRIGHT_EXIT"
"""


if __name__ == "__main__":
    unittest.main()
