"""Acyclic ownership graph proof through the Repository Policy Interface."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.checks import verify


class ArchitectureCycleTests(unittest.TestCase):
    fixtures = Path(__file__).parent / "fixtures"

    def test_declared_dependency_cycle_fails_policy_loading(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(self.fixtures / "positive", root, dirs_exist_ok=True)
            policy_path = root / "tools/checks/policy.toml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    'name = "fixture-app"\npaths = ["app/**"]\nallowed_dependencies = []',
                    'name = "fixture-app"\npaths = ["app/**"]\n'
                    'allowed_dependencies = ["fixture-consumer"]',
                ),
                encoding="utf-8",
            )

            report = verify(root, "fast")

        self.assertFalse(report.ok)
        self.assertEqual({item.rule_id for item in report.errors}, {"policy.invalid"})
        self.assertIn("ownership dependency cycle", report.errors[0].message)


if __name__ == "__main__":
    unittest.main()
