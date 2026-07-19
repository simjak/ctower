from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from tools.compatibility import CompatibilityError, execute_matrix, execution, load_matrix
from tools.compatibility.contract import CompatibilityMatrix

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "contracts" / "compatibility" / "ct-l0-007-matrix.json"


def minimal_probe(version: str, matrix: CompatibilityMatrix) -> dict[str, object]:
    observations = [
        {
            "id": observation,
            "status": "passed",
            "duration_ms": 1,
            "details": {"gil_enabled": True} if observation == "runtime" else {},
        }
        for observation in matrix.required_observations
    ]
    return {
        "version": version,
        "status": "passed",
        "interpreter": {"version": version, "free_threaded": False},
        "observations": observations,
    }


class FakeBoundary:
    def __init__(self, *, image_json: str | None = None, probe_json: str | None = None) -> None:
        self.matrix = load_matrix(MATRIX_PATH)
        self.mount: Path | None = None
        self.image_json = image_json
        self.probe_json = probe_json
        self.commands: list[list[str]] = []

    def __call__(
        self, command: list[str], environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        del environment
        self.commands.append(command)
        self._remember_mount(command)
        return self._response(command)

    def _remember_mount(self, command: list[str]) -> None:
        if "create" in command and "--mount" in command:
            mount = command[command.index("--mount") + 1]
            source = mount.split("source=", 1)[1].split(",target=", 1)[0]
            self.mount = Path(source)

    def _response(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        if "image" in command and "inspect" in command:
            output = self.image_json or json.dumps(
                [{"Id": "sha256:image", "Architecture": "arm64", "Os": "linux"}]
            )
            return subprocess.CompletedProcess(command, 0, output, "")
        if "freeze" in command:
            return subprocess.CompletedProcess(command, 0, "demo==1\nalpha==2\n", "")
        self._write_probe(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    def _write_probe(self, command: list[str]) -> None:
        if "--output" not in command:
            return
        version = command[command.index("--version") + 1]
        output_text = self.probe_json or json.dumps(minimal_probe(version, self.matrix))
        output = command[command.index("--output") + 1]
        if output == "/fixture/result.json":
            if self.mount is None:
                raise AssertionError("container probe ran before its fixture mount was recorded")
            destination = self.mount / "result.json"
        else:
            destination = Path(output)
        destination.write_text(output_text, encoding="utf-8")


class ExecutionTests(unittest.TestCase):
    def test_public_execution_runs_host_and_container_through_boundary(self) -> None:
        matrix = load_matrix(MATRIX_PATH)
        boundary = FakeBoundary()
        with (
            patch(
                "tools.compatibility.execution.shutil.which",
                side_effect=lambda name: f"/bin/{name}",
            ),
            patch("tools.compatibility.execution._spawn", side_effect=boundary),
        ):
            report = execute_matrix(matrix)

        runs = cast(list[object], report["runs"])
        self.assertEqual(len(runs), 6)
        encoded = json.dumps(report)
        self.assertNotIn(tempfile.gettempdir(), encoded)
        self.assertIn("$BOOTSTRAP_UV", encoded)
        self.assertIn("$CTOWER_CONTAINER", encoded)
        self.assertTrue(any(command[1:3] == ["rm", "-f"] for command in boundary.commands))

    def test_host_only_does_not_require_docker(self) -> None:
        matrix = load_matrix(MATRIX_PATH)
        boundary = FakeBoundary()
        with (
            patch(
                "tools.compatibility.execution.shutil.which",
                side_effect=lambda name: "/bin/uv" if name == "uv" else None,
            ),
            patch("tools.compatibility.execution._spawn", side_effect=boundary),
        ):
            report = execute_matrix(matrix, environments=("macos-host",))
        runs = cast(list[object], report["runs"])
        self.assertEqual(len(runs), 3)

    def test_missing_required_tool_fails_closed(self) -> None:
        matrix = load_matrix(MATRIX_PATH)
        with (
            patch("tools.compatibility.execution.shutil.which", return_value=None),
            self.assertRaisesRegex(CompatibilityError, "uv is required"),
        ):
            execute_matrix(matrix, environments=("macos-host",))

    def test_command_failure_and_malformed_outputs_fail_closed(self) -> None:
        matrix = load_matrix(MATRIX_PATH)

        def failed(
            command: list[str], environment: dict[str, str]
        ) -> subprocess.CompletedProcess[str]:
            del environment
            return subprocess.CompletedProcess(command, 7, "", "failure")

        with (
            patch("tools.compatibility.execution.shutil.which", return_value="/bin/tool"),
            patch("tools.compatibility.execution._spawn", side_effect=failed),
            self.assertRaisesRegex(CompatibilityError, "command failed"),
        ):
            execute_matrix(matrix, environments=("macos-host",))

        for boundary, message in (
            (FakeBoundary(image_json="{}"), "image inspection"),
            (FakeBoundary(probe_json="[]"), "probe report must be an object"),
            (FakeBoundary(probe_json="{"), "malformed probe report"),
        ):
            with (
                patch("tools.compatibility.execution.shutil.which", return_value="/bin/tool"),
                patch("tools.compatibility.execution._spawn", side_effect=boundary),
                self.assertRaisesRegex(CompatibilityError, message),
            ):
                execute_matrix(matrix, environments=("linux-container",))

    def test_resolution_and_interpreter_shape_fail_closed(self) -> None:
        matrix = load_matrix(MATRIX_PATH)
        for probe, message in (
            ({"version": "3.12.13", "interpreter": {}, "observations": []}, "dependency"),
            (
                {
                    "version": "3.12.13",
                    "interpreter": [],
                    "observations": [
                        {"id": "dependency_resolution", "status": "passed", "details": {}}
                    ],
                },
                "interpreter",
            ),
        ):
            boundary = FakeBoundary(probe_json=json.dumps(probe))
            with (
                patch("tools.compatibility.execution.shutil.which", return_value="/bin/tool"),
                patch("tools.compatibility.execution._spawn", side_effect=boundary),
                self.assertRaisesRegex(CompatibilityError, message),
            ):
                execute_matrix(matrix, environments=("linux-container",))

    def test_real_spawn_and_replacement_helpers(self) -> None:
        result = execution._spawn(["/usr/bin/env", "printf", "ok"], {"PATH": "/usr/bin:/bin"})
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(
            execution._replace("/long/root/file", [("/long/root", "$ROOT")]), "$ROOT/file"
        )
