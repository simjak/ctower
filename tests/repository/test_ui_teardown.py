"""Repository contract for the removed browser applications."""

from __future__ import annotations

import unittest
from pathlib import Path


class UiTeardownTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_runtime_apps_are_removed_but_fresh_web_slot_remains(self) -> None:
        for relative in (
            "apps/ctower-ui/README.md",
            "apps/ctower-ui/next.config.ts",
            "apps/ctower-ui/package.json",
            "apps/ctower-ui/tsconfig.json",
            "apps/ctower-ui/src",
        ):
            with self.subTest(path=relative):
                self.assertFalse((self.root / relative).exists())

        for relative in (
            "apps/ctower-web/README.md",
            "apps/ctower-web/package.json",
            "apps/ctower-web/src/architecture.ts",
            "apps/ctower-web/tsconfig.json",
        ):
            with self.subTest(path=relative):
                self.assertTrue((self.root / relative).is_file())

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

        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        for removed_artifact in (".next/", "next-env.d.ts", "playwright-report/", "test-results/"):
            with self.subTest(ignored_artifact=removed_artifact):
                self.assertNotIn(removed_artifact, gitignore)

        policy = (self.root / "tools/checks/policy.toml").read_text(encoding="utf-8")
        self.assertNotIn('name = "dogfood-tests"', policy)
        self.assertNotIn('name = "phase-1-ui"', policy)
        self.assertIn('name = "web"', policy)
        self.assertNotIn('"**/.next/**"', policy)

    def test_current_contract_has_no_retired_dogfood_claims(self) -> None:
        current_documents = (
            "ARCHITECTURE.md",
            "docs/internal/SPEC.md",
            "docs/internal/IMPLEMENTATION-ROADMAP.md",
            "docs/internal/project-status.md",
            "docs/internal/security/console-phase1-verification.md",
            "docs/internal/security/console-q3-typing-cso.md",
            "docs/internal/specs/operator-requests.md",
            "docs/concepts/board.md",
            "docs/concepts/chat.md",
            "docs/concepts/tickets.md",
            "docs/internal/concepts/seats-and-crews.md",
            "docs/internal/concepts/terminal-read.md",
        )
        for relative in ("docs/internal/operations/browser-quickstart.md",):
            with self.subTest(obsolete_document=relative):
                self.assertFalse((self.root / relative).exists())
        current_text = {
            relative: (self.root / relative).read_text(encoding="utf-8")
            for relative in current_documents
        }

        retired_claims = (
            "D41, D42, D44 and D45 alone permit",
            "D44 and D45 permit exactly one separate",
            "D41 permits exactly one separate",
            "D41/D42/D44/D45 is not a product route",
            "private UI send box each resolve",
            "project-seat CLI and the private UI send-box idiom are the only ordinary",
            "Seat CLI and UI send-box capture send",
            "local browser controls are a server-mediated development surface",
            "Open `/board` on the shadow instance.",
            "Open `/inbox`. Select a thread. Type in the send box",
            "On the local shadow browser, open `/board`",
            "Open `/team` in the local shadow browser",
            "Open `/team/<seat>` to see one terminal tab",
            "dogfood-inbox-controls",
            "apps/ctower-ui",
        )
        for relative, text in current_text.items():
            for claim in retired_claims:
                with self.subTest(document=relative, claim=claim):
                    self.assertNotIn(claim, text)

        self.assertIn("former `ctower-ui` runtime", current_text["ARCHITECTURE.md"])
        self.assertIn("D75 retires", current_text["docs/internal/project-status.md"])


if __name__ == "__main__":
    unittest.main()
