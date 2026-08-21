"""Repository contract for the retained ctower-ui empty shell."""

from __future__ import annotations

import unittest
from pathlib import Path


class UiEmptyShellTests(unittest.TestCase):
    root = Path(__file__).parents[2]
    app = root / "apps/ctower-ui"

    def test_setup_is_the_only_rendered_route_and_keeps_the_shell(self) -> None:
        app_routes = self.app / "src/app"
        routes = sorted(
            path.relative_to(app_routes).as_posix() for path in app_routes.rglob("page.tsx")
        )
        self.assertEqual(routes, ["setup/page.tsx"])

        for relative in (
            "README.md",
            "next.config.ts",
            "package.json",
            "tsconfig.json",
            "src/app/layout.tsx",
            "src/frame/Chrome.tsx",
            "src/frame/Sidebar.tsx",
            "src/frame/ThemeToggle.tsx",
        ):
            with self.subTest(path=relative):
                self.assertTrue((self.app / relative).is_file())

        layout = (self.app / "src/app/layout.tsx").read_text(encoding="utf-8")
        setup = (self.app / "src/app/setup/page.tsx").read_text(encoding="utf-8")
        chrome = (self.app / "src/frame/Chrome.tsx").read_text(encoding="utf-8")
        sidebar = (self.app / "src/frame/Sidebar.tsx").read_text(encoding="utf-8")

        rail = (self.app / "src/frame/rail.ts").read_text(encoding="utf-8")

        self.assertIn('"../../design-reference/app.css"', layout)
        self.assertIn("ThemeToggle", chrome)
        self.assertIn("href={item.href}", sidebar)
        self.assertIn('{ href: "/setup", label: "Setup" }', rail)
        self.assertIn("Company setup — feature 1, building", setup)

    def test_removed_product_modules_and_gate_wiring_are_absent(self) -> None:
        for relative in (
            "src/read",
            "src/mutate",
            "src/surfaces",
            "apps/ctower-web",
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
