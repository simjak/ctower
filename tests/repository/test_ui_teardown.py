"""Repository contract for the removed browser applications."""

from __future__ import annotations

import unittest
from pathlib import Path


class UiTeardownTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_runtime_apps_are_removed_while_mockups_and_web_slot_remain(self) -> None:
        for relative in (
            "apps/ctower-ui/README.md",
            "apps/ctower-ui/next.config.ts",
            "apps/ctower-ui/package.json",
            "apps/ctower-ui/tsconfig.json",
            "apps/ctower-ui/src",
            "apps/ctower-web/README.md",
            "apps/ctower-web/package.json",
            "apps/ctower-web/src",
            "apps/ctower-web/tsconfig.json",
        ):
            with self.subTest(path=relative):
                self.assertFalse((self.root / relative).exists())

        self.assertTrue((self.root / "apps/ctower-ui/design-reference/README.md").is_file())
        retained_files = [
            path.relative_to(self.root).as_posix()
            for path in (self.root / "apps/ctower-ui").rglob("*")
            if path.is_file()
        ]
        self.assertTrue(retained_files)
        self.assertTrue(
            all(path.startswith("apps/ctower-ui/design-reference/") for path in retained_files),
            retained_files,
        )

        workspace = (self.root / "pnpm-workspace.yaml").read_text(encoding="utf-8")
        self.assertNotIn("apps/ctower-ui", workspace)
        self.assertIn("apps/ctower-web", workspace)

        package = (self.root / "package.json").read_text(encoding="utf-8")
        self.assertNotIn("@ctower/ui", package)

    def test_removed_browser_gate_wiring_is_absent(self) -> None:
        for relative in (
            "tests/dogfood",
            "playwright.config.ts",
            "tools/checks/playwright.py",
        ):
            with self.subTest(path=relative):
                self.assertFalse((self.root / relative).exists())

        expected_suites = (self.root / "tools/checks/expected-suites.toml").read_text(
            encoding="utf-8"
        )
        for removed_suite in ("dogfood-inbox-controls", "locked-five", "surface-affordances"):
            with self.subTest(suite=removed_suite):
                self.assertNotIn(removed_suite, expected_suites)


if __name__ == "__main__":
    unittest.main()
