"""CLI adapter tests over the Repository Policy public Interface."""

from __future__ import annotations

import io
import json
import runpy
import shutil
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.checks.cli import main


class RepositoryPolicyCliTests(unittest.TestCase):
    fixtures = Path(__file__).parent / "fixtures"

    def test_text_and_json_policy_reports(self) -> None:
        root = self.fixtures / "positive"
        text_output = io.StringIO()
        with redirect_stdout(text_output):
            text_exit = main(["--root", str(root), "--profile", "full"])
        self.assertEqual(text_exit, 0)
        self.assertIn("repository-policy profile=full ok=true", text_output.getvalue())

        json_output = io.StringIO()
        with redirect_stdout(json_output):
            json_exit = main(["--root", str(root), "--profile", "full", "--json"])
        self.assertEqual(json_exit, 0)
        payload = json.loads(json_output.getvalue())
        self.assertTrue(payload["repository_policy"]["ok"])

    def test_missing_expected_manifest_sets_failure_exit(self) -> None:
        root = self.fixtures / "positive"
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--root", str(root), "--expected-suites"])
        self.assertEqual(exit_code, 1)
        self.assertIn("ERROR suite.manifest", output.getvalue())

    def test_module_entrypoint_returns_the_public_cli_status(self) -> None:
        root = self.fixtures / "positive"
        output = io.StringIO()
        argv = ["tools.checks", "--root", str(root), "--profile", "full"]
        with (
            patch.object(sys, "argv", argv),
            redirect_stdout(output),
            self.assertRaises(SystemExit) as raised,
        ):
            runpy.run_module("tools.checks", run_name="__main__")
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("repository-policy profile=full ok=true", output.getvalue())

    def test_execute_suites_uses_manifest_command_and_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(self.fixtures / "positive", root, dirs_exist_ok=True)
            test_path = root / "tests/current/test_current.py"
            test_path.parent.mkdir(parents=True)
            test_path.write_text("def test_current():\n    pass\n", encoding="utf-8")
            manifest_path = root / "tools/checks/expected-suites.toml"
            manifest_path.write_text(textwrap.dedent(self._manifest()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["--root", str(root), "--execute-suites", "--profile", "full", "--json"]
                )
        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["expected_suites"]["suites"][0]["disposition"], "passed")

    def _manifest(self) -> str:
        return """
            schema = "ctower.expected-suites/v1"
            manifest_version = 1
            active_phase = "CT-L0-007"
            phase_order = ["CT-L0-007"]

            [[suite]]
            id = "current"
            owner = "CT-L0-007"
            phase = "CT-L0-007"
            status = "required"
            path = "tests/current"
            patterns = ["test_*.py"]
            command = ["python3", "-c", "raise SystemExit(0)"]
            timeout_seconds = 30
        """


if __name__ == "__main__":
    unittest.main()
