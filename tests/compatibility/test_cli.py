from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compatibility.support import MATRIX_PATH, MatrixPort
else:
    try:
        from .support import MATRIX_PATH, MatrixPort
    except ImportError:
        from support import MATRIX_PATH, MatrixPort

from tools.compatibility import CompatibilityError
from tools.compatibility import __main__ as cli


class CliBoundaryTests(unittest.TestCase):
    def test_invalid_matrix_fails_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix = root / "matrix.json"
            matrix.write_text("{}", encoding="utf-8")
            arguments = ("--matrix", str(matrix), "--output", str(root / "out.json"))
            with self.assertRaises(CompatibilityError):
                cli.main(arguments, execution_port=MatrixPort())
            self.assertFalse((root / "out.json").exists())

    def test_partial_environment_is_not_publishable_l0_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            arguments = (
                "--matrix",
                str(MATRIX_PATH),
                "--output",
                str(output),
                "--environment",
                "macos-host",
            )
            with self.assertRaisesRegex(CompatibilityError, "requires macos-host"):
                cli.main(arguments, execution_port=MatrixPort())
            self.assertFalse(output.exists())

    def test_unknown_environment_is_rejected_by_argument_parser(self) -> None:
        arguments = (
            "--matrix",
            str(MATRIX_PATH),
            "--output",
            "out.json",
            "--environment",
            "unknown",
        )
        with self.assertRaises(SystemExit):
            cli.main(arguments, execution_port=MatrixPort())

    def test_full_cli_writes_schema_valid_six_leg_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            arguments = ("--matrix", str(MATRIX_PATH), "--output", str(output))
            self.assertEqual(cli.main(arguments, execution_port=MatrixPort()), 0)
            raw = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(raw["runs"]), 6)
