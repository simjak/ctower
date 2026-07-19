from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.compatibility import __main__ as cli
from tools.compatibility.contract import CompatibilityMatrix


class CliTests(unittest.TestCase):
    def test_cli_defaults_to_full_matrix_and_writes_report(self) -> None:
        matrix = CompatibilityMatrix("m", "1", (), (), (), (), "sha256:test")
        report: dict[str, object] = {"runs": []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            arguments = ["compat", "--matrix", "input.json", "--output", str(output)]
            with (
                patch.object(sys, "argv", arguments),
                patch.object(cli, "load_matrix", return_value=matrix),
                patch.object(cli, "execute_matrix", return_value=report) as execute,
                patch.object(cli, "write_report") as write,
            ):
                self.assertEqual(cli.main(), 0)
        execute.assert_called_once_with(matrix, environments=("macos-host", "linux-container"))
        write.assert_called_once_with(output, report)

    def test_cli_accepts_explicit_environment(self) -> None:
        matrix = CompatibilityMatrix("m", "1", (), (), (), (), "sha256:test")
        arguments = [
            "compat",
            "--matrix",
            "input.json",
            "--output",
            "out.json",
            "--environment",
            "macos-host",
        ]
        with (
            patch.object(sys, "argv", arguments),
            patch.object(cli, "load_matrix", return_value=matrix),
            patch.object(cli, "execute_matrix", return_value={}) as execute,
            patch.object(cli, "write_report"),
        ):
            self.assertEqual(cli.main(), 0)
        execute.assert_called_once_with(matrix, environments=("macos-host",))
