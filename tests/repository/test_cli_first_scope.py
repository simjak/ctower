"""CLI-first I1 registry and authority regression tests."""

from __future__ import annotations

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

    def test_the_dogfood_suite_activation_is_named_by_a_superseding_decision(self) -> None:
        """A required suite the canonical record disclaims is a contradiction.

        D40 clause 4 said the dogfood exception introduces no ``test-suite
        activation`` while the same candidate registered
        ``dogfood-inbox-promotion`` as a required suite that ``just verify``
        executes and counts. ``DECISIONS.md`` is append-only, so the repair is a
        superseding entry that names the activation and its limits — not an edit
        to D40, and not unregistering the verification the exception owes.
        """
        manifest = tomllib.loads(
            (self.root / "tools/checks/expected-suites.toml").read_text(encoding="utf-8")
        )
        suites = cast(list[dict[str, Any]], manifest["suite"])
        decisions = (self.root / "DECISIONS.md").read_text(encoding="utf-8")

        activated = sorted(
            suite["id"]
            for suite in suites
            if suite["id"].startswith("dogfood-") and suite["status"] == "required"
        )
        self.assertEqual(activated, ["dogfood-inbox-promotion"])
        for suite_id in activated:
            self.assertIn(f"`{suite_id}`", decisions)

        self.assertIn("## D41 — The dogfood exception activates one verification suite", decisions)
        self.assertIn(
            'This entry preserves D40 and supersedes only clause 4\'s "test-suite activation"',
            decisions,
        )
        self.assertIn("`browser-e2e` stays deferred to `CT-I2-005`", decisions)

    def test_d23_preserves_i1_semantics_and_defers_only_browser_realization(self) -> None:
        decisions = (self.root / "DECISIONS.md").read_text(encoding="utf-8")

        self.assertIn("## D23 — CLI-first I1 and deferred browser realization", decisions)
        self.assertIn(
            "Explicit durable intake intent/provenance and Workflow-owned risk remain", decisions
        )
        self.assertIn("`CT-I2-005` I2.4 browser sub-checkpoint", decisions)

    def test_current_guidance_keeps_browser_after_cli_first_cutover(self) -> None:
        current_guidance = {
            "README.md": (self.root / "README.md").read_text(encoding="utf-8"),
            "project status": (self.root / "docs/project-status.md").read_text(encoding="utf-8"),
            "coding standards": (self.root / "docs/contributing/CODING_STANDARDS.md").read_text(
                encoding="utf-8"
            ),
        }
        canonical_order = "Public API + protected CLI precede I1 source-of-truth cutover."
        browser_activation = (
            "Product browser implementation, browser evidence, and browser E2E first activate "
            "at CT-I2-005 / I2.4."
        )

        for name, guidance in current_guidance.items():
            with self.subTest(name=name):
                normalized_guidance = " ".join(guidance.split())
                self.assertIn(canonical_order, normalized_guidance)
                self.assertIn(browser_activation, normalized_guidance)
                self.assertIn("D40", normalized_guidance)

        self.assertNotIn(
            "Add the CLI and thin Board/Ticket UI, then cut ctower's own backlog over",
            current_guidance["README.md"],
        )
        self.assertNotIn(
            "CLI + thin UI -> source-of-truth cutover", current_guidance["project status"]
        )
        self.assertNotIn("browser E2E before CT-I1-008", current_guidance["coding standards"])


if __name__ == "__main__":
    unittest.main()
