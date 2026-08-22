"""CLI-first I1 registry and authority regression tests."""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path
from typing import Any, cast

__all__ = ()


class CliFirstScopeTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_browser_suite_is_deferred_to_i2_4_not_i1_5(self) -> None:
        manifest = tomllib.loads(
            (self.root / "tools/checks/expected-suites.toml").read_text(encoding="utf-8")
        )
        phase_order = cast(list[str], manifest["phase_order"])
        suites = cast(list[dict[str, Any]], manifest["suite"])
        browser_suite = next(item for item in suites if item["id"] == "browser-e2e")

        self.assertNotIn("CT-I1-005", phase_order)
        self.assertIn("CT-I2-005", phase_order)
        self.assertEqual(browser_suite["owner"], "CT-I2-005")
        self.assertEqual(browser_suite["phase"], "CT-I2-005")
        self.assertEqual(browser_suite["status"], "deferred")

    def test_d23_preserves_i1_semantics_and_defers_only_browser_realization(self) -> None:
        decisions = (self.root / "docs/internal/DECISIONS.md").read_text(encoding="utf-8")

        self.assertIn("## D23 — CLI-first I1 and deferred browser realization", decisions)
        self.assertIn(
            "Explicit durable intake intent/provenance and Workflow-owned risk remain", decisions
        )
        self.assertIn("`CT-I2-005` I2.4 browser sub-checkpoint", decisions)

    def test_current_guidance_keeps_browser_after_cli_first_cutover(self) -> None:
        current_guidance = (self.root / "docs/internal/project-status.md").read_text(
            encoding="utf-8"
        )
        canonical_order = "Public API + protected CLI precede I1 source-of-truth cutover."
        browser_activation = (
            "Product browser implementation, browser evidence, and browser E2E first activate "
            "at CT-I2-005 / I2.4."
        )

        normalized_guidance = " ".join(current_guidance.split())
        self.assertIn(canonical_order, normalized_guidance)
        self.assertIn(browser_activation, normalized_guidance)
        self.assertIn("D75", normalized_guidance)

        self.assertNotIn("CLI + thin UI -> source-of-truth cutover", current_guidance)

    def test_public_guidance_states_the_boundary_without_internal_references(self) -> None:
        public_pages = [self.root / "README.md", self.root / "CONTRIBUTING.md"]
        public_pages.extend(
            path
            for path in (self.root / "docs").rglob("*.md")
            if "internal" not in path.relative_to(self.root / "docs").parts
        )
        forbidden = re.compile(
            r"\b(?:R\d{3,}|D\d{1,3}|CT-[A-Z0-9-]+|AC-[A-Z0-9-]+)\b"
            r"|Mission Control|coordination/|docs/internal/|\.task\.md"
            r"|github\.com/simjak/ctower/(?:issues|pull)/\d+",
            re.IGNORECASE,
        )

        for path in public_pages:
            with self.subTest(path=path.relative_to(self.root)):
                source = path.read_text(encoding="utf-8")
                self.assertIsNone(forbidden.search(source))

        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "There is no published package, hosted service, or production deployment.", readme
        )
        self.assertIn("Browser surfaces are development-only and unsupported.", readme)


if __name__ == "__main__":
    unittest.main()
