"""Repository contract for the removed browser applications, and the one that replaced them.

#545 emptied the web slot and this file held the line while it was empty. The
slot is now filled by `apps/ctower-web`, so the assertions that said "nothing is
here" say "this is what is here" instead. Everything #545 retired stays retired:
the phase-1 runtime, its dogfood suite, playwright, and every claim in the
current documents that pointed at them.
"""

from __future__ import annotations

import unittest
from pathlib import Path

_CURRENT_DOCUMENTS = (
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
_RETIRED_CLAIMS = (
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


class UiTeardownTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_the_phase_one_runtime_is_gone_and_the_rebuilt_web_app_is_here(self) -> None:
        for relative in (
            "apps/ctower-ui/README.md",
            "apps/ctower-ui/next.config.ts",
            "apps/ctower-ui/package.json",
            "apps/ctower-ui/tsconfig.json",
            "apps/ctower-ui/src",
        ):
            with self.subTest(removed=relative):
                self.assertFalse((self.root / relative).exists())

        # The slot #545 left empty is the rebuild's, and it is occupied.
        for relative in (
            "apps/ctower-web/README.md",
            "apps/ctower-web/DESIGN.md",
            "apps/ctower-web/package.json",
            "apps/ctower-web/src",
            "apps/ctower-web/tsconfig.json",
        ):
            with self.subTest(rebuilt=relative):
                self.assertTrue((self.root / relative).exists())

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

    def test_the_phase_one_gate_wiring_stays_absent(self) -> None:
        for relative in ("tests/dogfood", "playwright.config.ts", "tools/checks/playwright.py"):
            with self.subTest(path=relative):
                self.assertFalse((self.root / relative).exists())

        # The browser-boundary gate came back with the app that claims it. It is
        # narrowed to `apps/ctower-web` and asserts that app's own rules; the
        # phase-1 read-layer rules it used to carry went with the phase-1 tree.
        chokepoint = self.root / "tests/repository/test_browser_network_chokepoint.py"
        self.assertTrue(chokepoint.is_file())
        self.assertIn("apps/ctower-web/src/api/bounded.ts", chokepoint.read_text(encoding="utf-8"))

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

        package = (self.root / "package.json").read_text(encoding="utf-8")
        for removed_marker in (
            "apps/ctower-ui/",
            "playwright.config.ts",
            "tools/checks/playwright.py",
            "@ctower/ui",
        ):
            with self.subTest(package_marker=removed_marker):
                self.assertNotIn(removed_marker, package)

        lockfile = (self.root / "pnpm-lock.yaml").read_text(encoding="utf-8")
        for removed_marker in ("apps/ctower-ui:", "next@16.3.0", "playwright@1.61.1"):
            with self.subTest(lock_marker=removed_marker):
                self.assertNotIn(removed_marker, lockfile)
        self.assertIn("apps/ctower-web:", lockfile)

    def test_current_contract_has_no_retired_dogfood_claims(self) -> None:
        for relative in ("docs/internal/operations/browser-quickstart.md",):
            with self.subTest(obsolete_document=relative):
                self.assertFalse((self.root / relative).exists())
        current_text = {
            relative: (self.root / relative).read_text(encoding="utf-8")
            for relative in _CURRENT_DOCUMENTS
        }

        for relative, text in current_text.items():
            for claim in _RETIRED_CLAIMS:
                with self.subTest(document=relative, claim=claim):
                    self.assertNotIn(claim, text)

        self.assertIn("former `ctower-ui` runtime", current_text["ARCHITECTURE.md"])
        self.assertIn("D75 retires", current_text["docs/internal/project-status.md"])

    def test_current_root_configuration_has_no_retired_dogfood_claims(self) -> None:
        current_config = {
            ".gitignore": (".next/", "next-env.d.ts", "playwright-report/", "test-results/"),
            "package.json": (
                "apps/ctower-ui/",
                "playwright.config.ts",
                "tools/checks/playwright.py",
                "@ctower/ui",
            ),
            "pnpm-lock.yaml": ("apps/ctower-ui:", "next@16.3.0", "playwright@1.61.1"),
            "tools/checks/expected-suites.toml": (
                "dogfood-inbox-controls",
                "locked-five",
                "surface-affordances",
            ),
            "tools/checks/policy.toml": (
                'name = "dogfood-tests"',
                'name = "phase-1-ui"',
                '"**/.next/**"',
            ),
        }
        for relative, markers in current_config.items():
            text = (self.root / relative).read_text(encoding="utf-8")
            for marker in markers:
                with self.subTest(config=relative, marker=marker):
                    self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
