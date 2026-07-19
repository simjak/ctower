from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from compatibility.support import ProbeFixturePort, telemetry
else:
    try:
        from .support import ProbeFixturePort, telemetry
    except ImportError:
        from support import ProbeFixturePort, telemetry

from tools.compatibility import CompatibilityError, probe
from tools.compatibility.probe import collect_probe

_SECRETS = {
    "AWS_ACCESS_KEY_ID": "synthetic-access-key",
    "AWS_SECRET_ACCESS_KEY": "synthetic-secret-key",
    "GH_TOKEN": "synthetic-github-token",
    "SSH_AUTH_SOCK": "/synthetic/agent.sock",
    "PIP_INDEX_URL": "https://credential@example.invalid/simple",
}


class ContainedProbeTests(unittest.TestCase):
    def test_complete_probe_uses_typed_models_and_minimal_environments(self) -> None:
        port = ProbeFixturePort()
        context = telemetry()
        with tempfile.TemporaryDirectory() as directory:
            contained = {"HOME": directory, "TMPDIR": directory, **_SECRETS}
            with patch.dict(os.environ, contained, clear=False):
                report = collect_probe("3.12.13", context, execution_port=port)

        self.assertEqual(report.status, "passed")
        self.assertEqual(
            [item.id for item in report.observations],
            [
                "runtime",
                "dependency_resolution",
                "pydantic",
                "fastapi",
                "psycopg",
                "opentelemetry",
                "ruff",
                "mypy_pydantic_plugin",
                "jsonschema",
                "wheel",
            ],
        )
        self.assertGreaterEqual(len(port.calls), 12)
        for request in port.calls:
            with self.subTest(argv=request.argv):
                environment = request.environment_dict()
                self.assertEqual(environment["HOME"], directory)
                self.assertEqual(environment["TMPDIR"], directory)
                self.assertTrue(set(environment).isdisjoint(_SECRETS))
                self.assertEqual(
                    json.loads(environment["CTOWER_TELEMETRY_CONTEXT"]),
                    context.model_dump(mode="json", by_alias=True),
                )

    def test_subprocess_failure_timeout_and_malformed_evidence_fail_closed(self) -> None:
        context = telemetry()
        with tempfile.TemporaryDirectory() as directory:
            environment = {"HOME": directory, "TMPDIR": directory}
            port = ProbeFixturePort()
            port.fail_source = "ruff"
            with (
                patch.dict(os.environ, environment, clear=False),
                self.assertRaisesRegex(CompatibilityError, "probe subprocess failed"),
            ):
                collect_probe("3.12.13", context, execution_port=port)

            port = ProbeFixturePort()
            port.timeout_source = "ruff"
            with (
                patch.dict(os.environ, environment, clear=False),
                self.assertRaisesRegex(CompatibilityError, "probe subprocess failed"),
            ):
                collect_probe("3.12.13", context, execution_port=port)

            port = ProbeFixturePort()
            port.output_overrides["FastAPI"] = "{}"
            with (
                patch.dict(os.environ, environment, clear=False),
                self.assertRaisesRegex(CompatibilityError, "malformed evidence"),
            ):
                collect_probe("3.12.13", context, execution_port=port)

            port = ProbeFixturePort()
            port.truncate_source = "FastAPI"
            with (
                patch.dict(os.environ, environment, clear=False),
                self.assertRaisesRegex(CompatibilityError, "incomplete output"),
            ):
                collect_probe("3.12.13", context, execution_port=port)

    def test_mypy_and_wheel_behavior_are_proven_not_assumed(self) -> None:
        context = telemetry()
        with tempfile.TemporaryDirectory() as directory:
            environment = {"HOME": directory, "TMPDIR": directory}
            port = ProbeFixturePort()
            port.mypy_invalid_returncode = 0
            with (
                patch.dict(os.environ, environment, clear=False),
                self.assertRaisesRegex(CompatibilityError, "mypy plugin"),
            ):
                collect_probe("3.12.13", context, execution_port=port)

            port = ProbeFixturePort()
            port.import_marker = "wrong\n"
            with (
                patch.dict(os.environ, environment, clear=False),
                self.assertRaisesRegex(CompatibilityError, "wrong marker"),
            ):
                collect_probe("3.12.13", context, execution_port=port)

    def test_probe_requires_contained_home_and_tmpdir(self) -> None:
        port = ProbeFixturePort()
        environment = {
            name: value for name, value in os.environ.items() if name not in {"HOME", "TMPDIR"}
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            self.assertRaisesRegex(CompatibilityError, "contained HOME and TMPDIR"),
        ):
            collect_probe("3.12.13", telemetry(), execution_port=port)

    def test_runtime_and_dependency_identity_are_port_owned(self) -> None:
        port = ProbeFixturePort(version="3.13.14")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"HOME": directory, "TMPDIR": directory}, clear=False),
        ):
            report = collect_probe("3.13.14", telemetry(), execution_port=port)
        self.assertEqual(report.interpreter.version, "3.13.14")
        dependency = report.observations[1]
        self.assertEqual(dependency.id, "dependency_resolution")


class ProbeCliFailureTests(unittest.TestCase):
    def test_missing_telemetry_is_a_typed_failure(self) -> None:
        arguments = (
            "--version",
            "3.12.13",
            "--output",
            "unused.json",
        )
        environment = {
            name: value for name, value in os.environ.items() if name != "CTOWER_TELEMETRY_CONTEXT"
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            self.assertRaisesRegex(CompatibilityError, "missing telemetry"),
        ):
            probe.main(arguments, execution_port=ProbeFixturePort())

    def test_probe_cli_writes_typed_evidence(self) -> None:
        context = telemetry()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe.json"
            environment = {
                "HOME": directory,
                "TMPDIR": directory,
                "CTOWER_TELEMETRY_CONTEXT": json.dumps(
                    context.model_dump(mode="json", by_alias=True)
                ),
            }
            arguments = ("--version", "3.12.13", "--output", str(output))
            with patch.dict(os.environ, environment, clear=False):
                self.assertEqual(
                    probe.main(arguments, execution_port=ProbeFixturePort()),
                    0,
                )
            raw = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(raw["telemetry"], context.model_dump(mode="json", by_alias=True))

    def test_probe_cli_rejects_malformed_telemetry(self) -> None:
        arguments = ("--version", "3.12.13", "--output", "unused.json")
        with (
            patch.dict(os.environ, {"CTOWER_TELEMETRY_CONTEXT": "{}"}, clear=False),
            self.assertRaisesRegex(CompatibilityError, "telemetry is malformed"),
        ):
            probe.main(arguments, execution_port=ProbeFixturePort())
