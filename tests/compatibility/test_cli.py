from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compatibility.support import MATRIX_PATH, report_payload
else:
    try:
        from .support import MATRIX_PATH, report_payload
    except ImportError:
        from support import MATRIX_PATH, report_payload

from tools.compatibility import CompatibilityError, load_matrix
from tools.compatibility import __main__ as cli


class CliBoundaryTests(unittest.TestCase):
    def test_invalid_inputs_fail_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_matrix = root / "matrix.json"
            invalid_matrix.write_text("{}", encoding="utf-8")
            report = self._write_report(root)
            output = root / "out.json"
            arguments = (
                "--matrix",
                str(invalid_matrix),
                "--report",
                str(report),
                "--output",
                str(output),
            )
            with self.assertRaises(CompatibilityError):
                cli.main(arguments)
            self.assertFalse(output.exists())

            report.write_text("{}", encoding="utf-8")
            arguments = (
                "--matrix",
                str(MATRIX_PATH),
                "--report",
                str(report),
                "--output",
                str(output),
            )
            with self.assertRaises(CompatibilityError):
                cli.main(arguments)
            self.assertFalse(output.exists())

    def test_removed_execution_flags_are_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            cli.main(("--allow-unconfined-host-diagnostic",))

    def test_cli_validates_and_publishes_closed_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self._write_report(root)
            output = root / "accepted.json"
            arguments = (
                "--matrix",
                str(MATRIX_PATH),
                "--report",
                str(report),
                "--output",
                str(output),
            )
            self.assertEqual(cli.main(arguments), 0)
            raw = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(raw["runs"]), 6)

    @staticmethod
    def _write_report(root: Path) -> Path:
        path = root / "report.json"
        path.write_text(json.dumps(report_payload(load_matrix(MATRIX_PATH))), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
