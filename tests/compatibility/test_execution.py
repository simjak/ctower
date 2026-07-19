from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

from pydantic import ValidationError

if TYPE_CHECKING:
    from compatibility.support import CONTAINER_ID, MATRIX_PATH, MatrixPort, env_names
else:
    try:
        from .support import CONTAINER_ID, MATRIX_PATH, MatrixPort, env_names
    except ImportError:
        from support import CONTAINER_ID, MATRIX_PATH, MatrixPort, env_names

from tools.compatibility import (
    CompatibilityError,
    LocalExecutionPort,
    execute_matrix,
    load_matrix,
)
from tools.compatibility.contract import EnvironmentVariable, ProcessRequest

_SYNTHETIC_SECRETS = {
    "AWS_SECRET_ACCESS_KEY": "synthetic-aws-secret",
    "GH_TOKEN": "synthetic-github-token",
    "SSH_AUTH_SOCK": "/synthetic/ssh-agent.sock",
    "PIP_INDEX_URL": "https://secret@example.invalid/simple",
    "UV_INDEX_URL": "https://secret@example.invalid/simple",
}


class MatrixExecutionTests(unittest.TestCase):
    def test_complete_matrix_is_typed_contained_and_telemetry_continuous(self) -> None:
        port = MatrixPort()
        with patch.dict(os.environ, _SYNTHETIC_SECRETS, clear=False):
            report = execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

        self.assertEqual(
            [(run.version, run.environment) for run in report.runs],
            [
                ("3.12.13", "macos-host"),
                ("3.12.13", "linux-container"),
                ("3.13.14", "macos-host"),
                ("3.13.14", "linux-container"),
                ("3.14.6", "macos-host"),
                ("3.14.6", "linux-container"),
            ],
        )
        self.assertTrue(all(run.telemetry == report.telemetry for run in report.runs))
        untrusted = {
            "python-install",
            "venv-create",
            "package-install",
            "compatibility-probe",
            "docker-package-install",
            "docker-probe",
        }
        for request in port.calls:
            with self.subTest(operation=request.operation):
                self.assertTrue(env_names(request.environment).isdisjoint(_SYNTHETIC_SECRETS))
                self.assertFalse(
                    any(value in " ".join(request.argv) for value in _SYNTHETIC_SECRETS.values())
                )
                if request.operation in untrusted and request.operation.startswith("docker-"):
                    self.assertIn("-i", request.argv)
                if request.operation in untrusted and not request.operation.startswith("docker-"):
                    self.assertNotIn(os.environ["HOME"], request.environment_dict().get("HOME", ""))
        cleanup = [request for request in port.calls if request.operation == "docker-cleanup"]
        self.assertEqual(len(cleanup), 3)
        self.assertTrue(all(request.argv[-1] == CONTAINER_ID for request in cleanup))
        installs = [request for request in port.calls if request.operation == "python-install"]
        self.assertTrue(all("macos-aarch64-none" in request.argv[-1] for request in installs))
        for run in report.runs[::2]:
            flattened_commands = " ".join(
                argument for command in run.resolution.commands for argument in command
            )
            self.assertIn("$BOOTSTRAP_UV", flattened_commands)
            self.assertIn("$PINNED_UV", flattened_commands)
            self.assertNotIn("/usr/local/bin/uv", flattened_commands)

    def test_host_identity_fails_before_any_process(self) -> None:
        port = MatrixPort()
        port.host = port.host.model_copy(update={"system": "Linux"})
        with self.assertRaisesRegex(CompatibilityError, "Darwin"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)
        self.assertEqual(port.calls, [])

        port = MatrixPort()
        port.host = port.host.model_copy(update={"machine": "ppc64"})
        with self.assertRaisesRegex(CompatibilityError, "unsupported macOS"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)
        self.assertEqual(port.calls, [])

    def test_missing_absolute_tools_fail_before_processes(self) -> None:
        class MissingToolPort(MatrixPort):
            def resolve_tool(self, name: str) -> str | None:
                del name
                return None

        port = MissingToolPort()
        with self.assertRaisesRegex(CompatibilityError, "uv is required"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)
        self.assertEqual(port.calls, [])

    def test_failed_create_never_deletes_unproven_name(self) -> None:
        port = MatrixPort()
        port.fail_operation = "docker-create"
        with self.assertRaisesRegex(CompatibilityError, "docker-create failed"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)
        self.assertNotIn("docker-cleanup", [request.operation for request in port.calls])

    def test_cleanup_failure_and_timeout_are_terminal_with_exact_identity(self) -> None:
        for mode in ("failed", "timeout"):
            port = MatrixPort()
            port.cleanup_mode = mode
            with (
                self.subTest(mode=mode),
                self.assertRaisesRegex(CompatibilityError, f"cleanup failed for {CONTAINER_ID}"),
            ):
                execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

    def test_created_container_must_bind_to_pinned_image_and_architecture(self) -> None:
        port = MatrixPort()
        port.container_image_id = "sha256:" + ("d" * 64)
        with self.assertRaisesRegex(CompatibilityError, "created container image"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

        port = MatrixPort()
        port.image_architecture = "amd64"
        with self.assertRaises((CompatibilityError, ValidationError)):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

    def test_malformed_probe_and_command_failure_fail_closed(self) -> None:
        port = MatrixPort()
        port.malformed_probe = '{"version":"3.12.13","extra":true}'
        with self.assertRaisesRegex(CompatibilityError, "probe result"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

        port = MatrixPort()
        port.fail_operation = "package-install"
        with self.assertRaisesRegex(CompatibilityError, "package-install failed"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

    def test_malformed_or_unowned_container_evidence_fails_closed(self) -> None:
        port = MatrixPort()
        port.create_stdout = "not-a-container-id\n"
        with self.assertRaisesRegex(CompatibilityError, "malformed container identity"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)
        self.assertNotIn("docker-cleanup", [request.operation for request in port.calls])

        port = MatrixPort()
        port.image_inspection_override = "{}"
        with self.assertRaisesRegex(CompatibilityError, "image inspection was malformed"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)
        self.assertIn("docker-cleanup", [request.operation for request in port.calls])

        port = MatrixPort()
        port.container_inspection_override = "{}"
        with self.assertRaisesRegex(CompatibilityError, "container inspection was malformed"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

        port = MatrixPort()
        port.owner_label_override = "d" * 32
        with self.assertRaisesRegex(CompatibilityError, "ownership identity"):
            execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)

    def test_probe_semantic_identity_failures_cross_schema_before_model(self) -> None:
        def wrong_interpreter(payload: dict[str, object]) -> None:
            cast(dict[str, Any], payload["interpreter"])["version"] = "3.13.14"

        def wrong_dependencies(payload: dict[str, object]) -> None:
            observations = cast(list[dict[str, Any]], payload["observations"])
            observations[1]["details"]["direct_versions"][0]["version"] = "9.9.9"

        def wrong_runtime_observation(payload: dict[str, object]) -> None:
            observations = cast(list[dict[str, Any]], payload["observations"])
            details = dict(cast(dict[str, Any], observations[0]["details"]))
            details["executable_sha256"] = "f" * 64
            observations[0]["details"] = details

        for mutation in (wrong_interpreter, wrong_dependencies, wrong_runtime_observation):
            port = MatrixPort()
            port.probe_mutator = mutation
            with self.subTest(mutation=mutation.__name__), self.assertRaises(CompatibilityError):
                execute_matrix(load_matrix(MATRIX_PATH), execution_port=port)


class LocalProcessBoundaryTests(unittest.TestCase):
    def test_timeout_terminates_and_sigterm_resistance_escalates(self) -> None:
        port = LocalExecutionPort()
        terminated = port.run(_request("import time; time.sleep(10)", timeout_ms=50))
        self.assertTrue(terminated.timed_out)
        self.assertIn(terminated.termination, {"terminated", "killed"})

        resistant = port.run(
            _request(
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(10)",
                timeout_ms=200,
            )
        )
        self.assertTrue(resistant.timed_out)
        self.assertEqual(resistant.termination, "killed")

    def test_output_is_bounded_and_start_failure_is_typed(self) -> None:
        port = LocalExecutionPort()
        output = port.run(_request("print('x' * 5000)", output_limit_bytes=1024))
        self.assertTrue(output.stdout_truncated)
        self.assertLessEqual(len(output.stdout.encode()), 1024)

        request = ProcessRequest(
            operation="probe-subprocess",
            argv=("/does/not/exist",),
            environment=(),
            timeout_ms=50,
            terminate_grace_ms=20,
            output_limit_bytes=1024,
        )
        with self.assertRaisesRegex(CompatibilityError, "unable to start"):
            port.run(request)

    def test_process_request_rejects_relative_executables_and_duplicate_environment(self) -> None:
        with self.assertRaises(ValidationError):
            ProcessRequest(
                operation="probe-subprocess",
                argv=("python",),
                environment=(),
                timeout_ms=50,
                terminate_grace_ms=20,
                output_limit_bytes=1024,
            )
        repeated = (
            EnvironmentVariable(name="PATH", value="/bin"),
            EnvironmentVariable(name="PATH", value="/usr/bin"),
        )
        with self.assertRaises(ValidationError):
            ProcessRequest(
                operation="probe-subprocess",
                argv=(sys.executable,),
                environment=repeated,
                timeout_ms=50,
                terminate_grace_ms=20,
                output_limit_bytes=1024,
            )

    def test_local_metadata_adapter_is_explicit(self) -> None:
        port = LocalExecutionPort()
        self.assertIsNotNone(port.resolve_tool("python"))
        self.assertEqual(port.distribution_version("pydantic"), "2.13.4")
        with self.assertRaisesRegex(CompatibilityError, "expected Python"):
            port.runtime_details("3.12.13")
        self.assertIn(port.host_identity().system, {"Darwin", "Linux"})


def _request(
    source: str, *, timeout_ms: int = 1_000, output_limit_bytes: int = 2048
) -> ProcessRequest:
    with tempfile.TemporaryDirectory() as directory:
        home = str(Path(directory))
    return ProcessRequest(
        operation="probe-subprocess",
        argv=(sys.executable, "-c", source),
        environment=(
            EnvironmentVariable(name="HOME", value=home),
            EnvironmentVariable(name="PATH", value="/usr/bin:/bin"),
        ),
        timeout_ms=timeout_ms,
        terminate_grace_ms=50,
        output_limit_bytes=output_limit_bytes,
    )
