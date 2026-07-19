from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.compatibility import probe


def completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["probe"], returncode, stdout, stderr)


class ProbeTests(unittest.TestCase):
    def test_observation_runtime_dependencies_and_hashes(self) -> None:
        success = probe._observe("ok", lambda: {"value": True})
        failure = probe._observe("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(success["status"], "passed")
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(probe._runtime(sys.version.split()[0])["gil_enabled"], True)
        with (
            patch.object(sys, "_is_gil_enabled", None),
            patch("tools.compatibility.probe.sysconfig.get_config_var", return_value=1),
        ):
            self.assertFalse(probe._gil_enabled())
        with (
            patch("tools.compatibility.probe.platform.python_version", return_value="0.0.0"),
            self.assertRaisesRegex(RuntimeError, "expected Python"),
        ):
            probe._runtime("1.2.3")
        with patch("tools.compatibility.probe.importlib.metadata.version", return_value="1"):
            self.assertEqual(probe._dependencies(("demo==1",)), {"direct_versions": {"demo": "1"}})
            with self.assertRaisesRegex(RuntimeError, "mismatches"):
                probe._dependencies(("demo==2",))
        self.assertEqual(len(probe._json_sha256({"a": 1})), 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "value"
            path.write_bytes(b"ctower")
            self.assertEqual(len(probe._file_sha256(path)), 64)

    def test_json_subprobe_and_wrappers(self) -> None:
        with patch("tools.compatibility.probe._run", return_value=completed(stdout='{"ok": true}')):
            self.assertEqual(probe._python_json("ignored"), {"ok": True})
        for result, message in (
            (completed(1, stderr="failed"), "failed"),
            (completed(stdout="{"), "malformed"),
            (completed(stdout="[]"), "JSON object"),
        ):
            with (
                patch("tools.compatibility.probe._run", return_value=result),
                self.assertRaisesRegex(RuntimeError, message),
            ):
                probe._python_json("ignored")
        with patch("tools.compatibility.probe._python_json", return_value={"ok": True}) as run:
            for operation in (
                probe._pydantic,
                probe._fastapi,
                probe._psycopg,
                probe._opentelemetry,
                probe._jsonschema,
            ):
                self.assertEqual(operation(), {"ok": True})
            self.assertEqual(run.call_count, 5)

    def test_tool_and_typechecker_observations(self) -> None:
        with patch("tools.compatibility.probe._run", return_value=completed()):
            self.assertEqual(probe._ruff(), {"exit_code": 0})
        with (
            patch("tools.compatibility.probe._run", return_value=completed(1, stderr="bad")),
            self.assertRaisesRegex(RuntimeError, "Ruff failed"),
        ):
            probe._ruff()

        valid = completed()
        invalid = completed(1, stdout="Unexpected keyword argument")
        with patch("tools.compatibility.probe._run", side_effect=[valid, invalid]):
            self.assertTrue(probe._mypy()["extra_field_rejected"])
        with (
            patch("tools.compatibility.probe._run", side_effect=[completed(1), invalid]),
            self.assertRaisesRegex(RuntimeError, "valid Pydantic"),
        ):
            probe._mypy()
        with (
            patch("tools.compatibility.probe._run", side_effect=[valid, completed()]),
            self.assertRaisesRegex(RuntimeError, "did not reject"),
        ):
            probe._mypy()

    def test_wheel_observation_success_and_failures(self) -> None:
        def successful(command: list[str]) -> subprocess.CompletedProcess[str]:
            if "build" in command:
                root = Path(command[-1])
                (root / "dist").mkdir()
                (root / "dist" / "ctower.whl").write_bytes(b"wheel")
            stdout = "ctower-wheel-ok\n" if "ctower_compat_wheel" in command[-1] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with patch("tools.compatibility.probe._run", side_effect=successful):
            self.assertTrue(probe._wheel()["imported"])

        with (
            patch("tools.compatibility.probe._run", return_value=completed(1, stderr="build")),
            self.assertRaisesRegex(RuntimeError, "wheel build"),
        ):
            probe._wheel()

    def test_main_writes_pass_and_fail_reports(self) -> None:
        operations = (
            "_runtime",
            "_dependencies",
            "_pydantic",
            "_fastapi",
            "_psycopg",
            "_opentelemetry",
            "_ruff",
            "_mypy",
            "_jsonschema",
            "_wheel",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            arguments = [
                "probe",
                "--version",
                "3.14.6",
                "--requirements",
                "[]",
                "--output",
                str(output),
            ]
            patches = [patch.object(probe, name, return_value={}) for name in operations]
            entered = [item.start() for item in patches]
            del entered
            try:
                with patch.object(sys, "argv", arguments):
                    self.assertEqual(probe.main(), 0)
            finally:
                for item in reversed(patches):
                    item.stop()
            self.assertEqual(json.loads(output.read_text())["status"], "passed")

    def test_real_process_boundary(self) -> None:
        result = probe._spawn([sys.executable, "-c", "print('ok')"], {"PATH": "/usr/bin:/bin"})
        self.assertEqual(result.stdout.strip(), "ok")
        self.assertEqual(probe._command_details(result), {"exit_code": 0})
