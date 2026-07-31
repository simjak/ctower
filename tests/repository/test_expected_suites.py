"""Behavioral tests through the expected-suite public Interface."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import textwrap
import time
import tomllib
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tools.checks import SuiteDisposition, verify_expected_suites
from tools.checks._impl.evidence_manifest import (
    derive_denominator_keys,
    verify_evidence_manifest,
)
from tools.checks.owned_processes import (
    TerminationOutcome,
    TerminationResult,
    owned_process_ids,
    terminate_owned_processes,
)

__all__ = ()

_EXPECTED_SUITE_OWNER_ENV = "CTOWER_VERIFY_SUITE_OWNER"


class ExpectedSuitesTests(unittest.TestCase):
    def test_current_suite_is_required_and_future_suite_is_not_yet_required(self) -> None:
        with self._repository() as root:
            self._write_test(
                root, "tests/current/test_current.py", "def test_current():\n    pass\n"
            )
            self._write_manifest(root, self._two_suite_manifest())
            report = verify_expected_suites(root)

        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(
            [item.disposition for item in report.suites],
            [SuiteDisposition.REQUIRED, SuiteDisposition.NOT_YET_REQUIRED],
        )
        self.assertIn("not counted as passing", report.suites[1].message)

    def test_missing_current_suite_fails_closed(self) -> None:
        with self._repository() as root:
            self._write_manifest(root, self._one_suite_manifest())
            report = verify_expected_suites(root)

        self.assertFalse(report.ok)
        self.assertIn("missing", report.failures[0].message)

    def test_suite_without_a_test_definition_is_empty(self) -> None:
        with self._repository() as root:
            self._write_test(root, "tests/current/test_placeholder.py", "VALUE = 1\n")
            self._write_manifest(root, self._one_suite_manifest())
            report = verify_expected_suites(root)

        self.assertFalse(report.ok)
        self.assertIn("no executable test definitions", report.failures[0].message)

    def test_unexpected_skip_in_current_suite_fails(self) -> None:
        source = """
            import unittest

            class CurrentTests(unittest.TestCase):
                @unittest.skip("not implemented")
                def test_current(self):
                    pass
        """
        with self._repository() as root:
            self._write_test(root, "tests/current/test_current.py", textwrap.dedent(source))
            self._write_manifest(root, self._one_suite_manifest())
            report = verify_expected_suites(root)

        self.assertFalse(report.ok)
        self.assertIn("unexpected skip", report.failures[0].message)

    def test_required_command_passes_or_fails_with_its_real_exit_code(self) -> None:
        with self.subTest("pass"):
            with self._repository() as root:
                self._write_test(
                    root, "tests/current/test_current.py", "def test_current():\n    pass\n"
                )
                self._write_manifest(root, self._one_suite_manifest(command_exit=0))
                report = verify_expected_suites(root, execute=True)
            self.assertTrue(report.ok, report.to_dict())
            self.assertEqual(report.suites[0].disposition, SuiteDisposition.PASSED)

        with self.subTest("fail"):
            with self._repository() as root:
                self._write_test(
                    root, "tests/current/test_current.py", "def test_current():\n    pass\n"
                )
                self._write_manifest(root, self._one_suite_manifest(command_exit=7))
                report = verify_expected_suites(root, execute=True)
            self.assertFalse(report.ok)
            self.assertIn("exit code 7", report.failures[0].message)

    def test_portable_python_token_uses_invoking_interpreter_without_changing_report(self) -> None:
        with self._repository() as root:
            self._write_test(
                root, "tests/current/test_current.py", "def test_current():\n    pass\n"
            )
            self._write_manifest(
                root,
                self._suite_table(
                    suite_id="current",
                    phase="CT-L0-007",
                    status="required",
                    path="tests/current",
                    command=(
                        '["{python}", "-c", "from pathlib import Path; '
                        "import sys; Path('suite-ran').write_text(sys.executable, "
                        "encoding='utf-8')\"]"
                    ),
                ),
            )
            report = verify_expected_suites(root, execute=True)
            marker = (root / "suite-ran").read_text(encoding="utf-8")

        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(marker, sys.executable)
        self.assertEqual(
            report.suites[0].command,
            (
                "{python}",
                "-c",
                "from pathlib import Path; import sys; "
                "Path('suite-ran').write_text(sys.executable, encoding='utf-8')",
            ),
        )

    def test_command_not_found_and_timeout_fail_closed(self) -> None:
        cases = {
            "missing": ('["ctower-command-that-does-not-exist"]', 30, "cannot execute"),
            "timeout": (
                '["{python}", "-c", "import time; time.sleep(2)"]',
                1,
                "timed out",
            ),
        }
        for label, (command, timeout, expected) in cases.items():
            with self.subTest(label):
                with self._repository() as root:
                    self._write_test(
                        root, "tests/current/test_current.py", "def test_current():\n    pass\n"
                    )
                    manifest = self._suite_table(
                        suite_id="current",
                        phase="CT-L0-007",
                        status="required",
                        path="tests/current",
                        command=command,
                        timeout=timeout,
                    )
                    self._write_manifest(root, manifest)
                    report = verify_expected_suites(root, execute=True)
                self.assertFalse(report.ok)
                self.assertIn(expected, report.failures[0].message)

    def test_unknown_owned_process_cleanup_fails_loudly_by_name(self) -> None:
        cleanup = TerminationResult(
            outcome=TerminationOutcome.UNKNOWN,
            scanned=1,
            readable=0,
            unreadable_pids=(123,),
            candidate_unreadable_pids=(123,),
            owned_pids=(),
        )
        with self._repository() as root:
            self._write_test(
                root, "tests/current/test_current.py", "def test_current():\n    pass\n"
            )
            self._write_manifest(root, self._one_suite_manifest(command_exit=0))
            with mock.patch(
                "tools.checks._impl.suites.terminate_owned_processes",
                new=mock.AsyncMock(return_value=cleanup),
            ):
                report = verify_expected_suites(root, execute=True)

        message = report.failures[0].message
        self.assertFalse(report.ok)
        self.assertIn("UNKNOWN", message)
        self.assertIn("candidate unreadable pids: 123", message)
        self.assertIn("scanned 1, readable 0, unreadable 1", message)

    def test_leader_exit_and_timeout_cannot_leave_a_descendant_alive(self) -> None:
        child = (
            "import os,signal,time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"Path('descendant.owner').write_text("
            f"os.environ[{_EXPECTED_SUITE_OWNER_ENV!r}], encoding='utf-8'); "
            "print('r', flush=True); time.sleep(60)"
        )
        prefix = (
            "import subprocess,sys,time; from pathlib import Path; "
            f"child=subprocess.Popen([sys.executable, '-c', {child!r}], "
            "stdout=subprocess.PIPE, text=True); "
            "child.stdout.read(1); "
        )
        for label, suffix, timeout, expected_ok in (
            ("leader exit", "", 30, True),
            ("leader timeout", "time.sleep(60)", 1, False),
        ):
            with self.subTest(label=label):
                self._assert_owned_descendant_absent(
                    prefix + suffix, timeout, expected_ok=expected_ok
                )

    def _assert_owned_descendant_absent(
        self, leader: str, timeout: int, *, expected_ok: bool
    ) -> None:
        command = json.dumps(["{python}", "-c", leader])
        owner = ""
        with self._repository() as root:
            self._write_test(
                root, "tests/current/test_current.py", "def test_current():\n    pass\n"
            )
            self._write_manifest(
                root,
                self._suite_table(
                    suite_id="current",
                    phase="CT-L0-007",
                    status="required",
                    path="tests/current",
                    command=command,
                    timeout=timeout,
                ),
            )
            try:
                report = verify_expected_suites(root, execute=True)
                owner = (root / "descendant.owner").read_text(encoding="utf-8")
                deadline = time.monotonic() + 1.0
                while (
                    owned_process_ids(_EXPECTED_SUITE_OWNER_ENV, owner)
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                self.assertEqual(report.ok, expected_ok, report.to_dict())
                self.assertFalse(
                    owned_process_ids(_EXPECTED_SUITE_OWNER_ENV, owner),
                    "suite descendant survived leader completion",
                )
            finally:
                if owner:
                    asyncio.run(
                        terminate_owned_processes(
                            _EXPECTED_SUITE_OWNER_ENV,
                            owner,
                            term_grace_seconds=0,
                            kill_grace_seconds=1,
                        )
                    )

    def test_manifest_header_and_suite_field_errors_fail_closed(self) -> None:
        valid = textwrap.dedent(self._header()) + self._one_suite_manifest()
        cases = {
            "schema": valid.replace("ctower.expected-suites/v1", "wrong/v1"),
            "version": valid.replace("manifest_version = 1", "manifest_version = 0"),
            "active": valid.replace('active_phase = "CT-L0-007"', 'active_phase = "CT-I9-999"'),
            "duplicate phase": valid.replace(
                '["CT-L0-007", "CT-I1-008"]', '["CT-L0-007", "CT-L0-007"]'
            ),
            "invalid phase": valid.replace("CT-I1-008", "not-a-backlog-id"),
            "missing suites": textwrap.dedent(self._header()),
            "scalar": valid.replace('id = "current"', "id = 7"),
            "suite key": valid.replace('id = "current"', 'id = "INVALID"'),
            "owner": valid.replace('owner = "CT-L0-007"', 'owner = "invalid"'),
            "status": valid.replace('status = "required"', 'status = "optional"'),
            "patterns": valid.replace('patterns = ["test_*.py"]', "patterns = []"),
            "path": valid.replace('path = "tests/current"', 'path = "../outside"'),
            "timeout": valid.replace("timeout_seconds = 30", "timeout_seconds = 0"),
        }
        for label, manifest in cases.items():
            with self.subTest(label):
                with self._repository() as root:
                    (root / "tools/checks/expected-suites.toml").write_text(
                        manifest, encoding="utf-8"
                    )
                    report = verify_expected_suites(root)
                self.assertFalse(report.ok)
                self.assertTrue(report.manifest_errors)

    def test_phase_outside_order_and_malformed_test_files_fail(self) -> None:
        with self.subTest("phase outside order"):
            with self._repository() as root:
                manifest = self._suite_table(
                    suite_id="other",
                    phase="CT-I2-010",
                    status="deferred",
                    path="tests/other",
                )
                self._write_manifest(root, manifest)
                report = verify_expected_suites(root)
            self.assertIn("absent", report.failures[0].message)

        malformed = {
            "no match": ("tests/current/helper.py", "VALUE = 1\n", "matches no test files"),
            "empty": ("tests/current/test_empty.py", "", "is empty"),
            "syntax": ("tests/current/test_bad.py", "def test_bad(:\n", "invalid Python"),
        }
        for label, (relative, source, expected) in malformed.items():
            with self.subTest(label):
                with self._repository() as root:
                    self._write_test(root, relative, source)
                    self._write_manifest(root, self._one_suite_manifest())
                    report = verify_expected_suites(root)
                self.assertFalse(report.ok)
                self.assertIn(expected, report.failures[0].message)

    def test_invalid_manifest_and_status_phase_conflict_fail(self) -> None:
        with self.subTest("duplicate suite ID"):
            with self._repository() as root:
                manifest = self._one_suite_manifest() + self._suite_table(
                    suite_id="current", phase="CT-L0-007", status="required", path="tests/other"
                )
                self._write_manifest(root, manifest)
                report = verify_expected_suites(root)
            self.assertFalse(report.ok)
            self.assertIn("unique", report.manifest_errors[0])

        with self.subTest("later phase declared current"):
            with self._repository() as root:
                self._write_manifest(
                    root,
                    self._suite_table(
                        suite_id="future",
                        phase="CT-I1-008",
                        status="required",
                        path="tests/future",
                    ),
                )
                report = verify_expected_suites(root)
            self.assertFalse(report.ok)
            self.assertIn("conflicts", report.failures[0].message)

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "tools/checks").mkdir(parents=True)
            yield root

    def _write_manifest(self, root: Path, suites: str) -> None:
        (root / "tools/checks/expected-suites.toml").write_text(
            textwrap.dedent(self._header()) + suites,
            encoding="utf-8",
        )

    def _header(self) -> str:
        return """
            schema = "ctower.expected-suites/v1"
            manifest_version = 1
            active_phase = "CT-L0-007"
            phase_order = ["CT-L0-007", "CT-I1-008"]
        """

    def _write_test(self, root: Path, relative: str, source: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def _one_suite_manifest(self, *, command_exit: int | None = None) -> str:
        return self._suite_table(
            suite_id="current",
            phase="CT-L0-007",
            status="required",
            path="tests/current",
            command_exit=command_exit,
        )

    def _two_suite_manifest(self) -> str:
        return self._one_suite_manifest() + self._suite_table(
            suite_id="future", phase="CT-I1-008", status="deferred", path="tests/future"
        )

    def _suite_table(
        self,
        *,
        suite_id: str,
        phase: str,
        status: str,
        path: str,
        command_exit: int | None = None,
        command: str | None = None,
        timeout: int = 30,
    ) -> str:
        command_value = command or (
            f'["{{python}}", "-c", "raise SystemExit({command_exit})"]'
            if command_exit is not None
            else f'["{{python}}", "-m", "unittest", "discover", "-s", "{path}", "-v"]'
        )
        return textwrap.dedent(
            f"""

            [[suite]]
            id = "{suite_id}"
            owner = "{phase}"
            phase = "{phase}"
            status = "{status}"
            path = "{path}"
            patterns = ["test_*.py"]
            command = {command_value}
            timeout_seconds = {timeout}
            """
        )


class PortableCommandValidationTests(unittest.TestCase):
    def test_only_exact_python_token_in_executable_position_is_supported(self) -> None:
        cases = {
            "misplaced": '["echo", "{python}"]',
            "embedded": '["/opt/{python}/bin/python"]',
            "unsupported": '["{node}", "--version"]',
        }
        for label, command in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                manifest_path = root / "tools/checks/expected-suites.toml"
                manifest_path.parent.mkdir(parents=True)
                manifest_path.write_text(
                    textwrap.dedent(
                        f"""
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
                        command = {command}
                        timeout_seconds = 30
                        """
                    ),
                    encoding="utf-8",
                )
                report = verify_expected_suites(root)

            self.assertFalse(report.ok)
            self.assertTrue(report.manifest_errors)
            self.assertIn("token", report.manifest_errors[0])


class CommittedManifestGuardTests(unittest.TestCase):
    """Validate the REAL committed expected-suites.toml — not a synthetic fixture.

    These tests ensure the I1 acceptance suite remains deferred (NOT_YET_REQUIRED)
    until S11, that no empty placeholder passes vacuously, and that the
    evidence-manifest generator output has zero drift with the expected-suite
    config.
    """

    _ROOT = Path(__file__).parents[2]
    _MANIFEST_PATH = _ROOT / "tools/checks/expected-suites.toml"
    _FIXTURE_PATH = _ROOT / "tests/contracts/evidence/fixtures/i1-complete-manifest.json"

    def test_committed_manifest_loads_without_configuration_errors(self) -> None:
        report = verify_expected_suites(self._ROOT)
        self.assertFalse(report.manifest_errors, report.manifest_errors)

    def test_increment_1_acceptance_suite_is_deferred_not_required(self) -> None:
        """The final I1 acceptance suite must be NOT_YET_REQUIRED — never
        required, never silently skipped, and never an empty placeholder that
        passes vacuously."""

        report = verify_expected_suites(self._ROOT)
        suite = self._find_suite(report, "increment-1-acceptance")
        self.assertIsNotNone(
            suite,
            "increment-1-acceptance suite must exist in the committed manifest",
        )
        assert suite is not None  # for type-checkers
        self.assertEqual(
            suite.disposition,
            SuiteDisposition.NOT_YET_REQUIRED,
            f"increment-1-acceptance must be deferred, got {suite.disposition}",
        )
        self.assertIn("not counted as passing", suite.message)

    def test_increment_1_acceptance_is_not_counted_as_passing(self) -> None:
        """A deferred suite must never have disposition PASSED — that would
        mean an empty placeholder slipped through."""

        report = verify_expected_suites(self._ROOT)
        suite = self._find_suite(report, "increment-1-acceptance")
        self.assertIsNotNone(
            suite,
            "increment-1-acceptance suite must exist in the committed manifest",
        )
        assert suite is not None  # for type-checkers
        self.assertNotEqual(
            suite.disposition,
            SuiteDisposition.PASSED,
            "deferred suite must never be counted as passing",
        )

    def test_deferred_suite_has_real_test_files_not_empty(self) -> None:
        """The deferred suite's path must contain real test files — an empty
        directory would let the suite pass vacuously when eventually required."""

        data = tomllib.loads(self._MANIFEST_PATH.read_text(encoding="utf-8"))
        suite_entry = next(s for s in data["suite"] if s["id"] == "increment-1-acceptance")
        suite_path = self._ROOT / suite_entry["path"]
        self.assertTrue(
            suite_path.is_dir(),
            f"deferred suite path {suite_entry['path']} must exist",
        )
        test_files = [
            p
            for pattern in suite_entry["patterns"]
            for p in suite_path.rglob(pattern)
            if p.is_file()
        ]
        self.assertTrue(
            test_files,
            "deferred suite must reference real test files, not an empty placeholder",
        )

    def test_deferred_suite_phase_is_after_active_phase(self) -> None:
        """The I1 acceptance suite's phase must be after the active phase in
        phase_order — that is what makes it deferred (NOT_YET_REQUIRED)."""

        data = tomllib.loads(self._MANIFEST_PATH.read_text(encoding="utf-8"))
        active_phase = data["active_phase"]
        phase_order = data["phase_order"]
        suite_entry = next(s for s in data["suite"] if s["id"] == "increment-1-acceptance")
        suite_phase = suite_entry["phase"]
        active_index = phase_order.index(active_phase)
        suite_index = phase_order.index(suite_phase)
        self.assertGreater(
            suite_index,
            active_index,
            f"increment-1-acceptance phase {suite_phase} must be after active phase {active_phase}",
        )
        self.assertEqual(
            suite_entry["status"],
            "deferred",
            "increment-1-acceptance status must be 'deferred'",
        )

    def test_evidence_manifest_has_zero_drift_with_expected_suites(self) -> None:
        """The committed evidence manifest fixture's deferred_capabilities must
        exactly match the denominator derived from the capability registry and
        the deferred expected-suite IDs — zero drift."""

        errors = verify_evidence_manifest(self._ROOT, self._FIXTURE_PATH)
        self.assertEqual(
            errors,
            (),
            f"evidence manifest has drift from expected-suite config: {errors}",
        )

    def test_deferred_suite_ids_match_expected_suites_toml(self) -> None:
        """The denominator's deferred-suite set must exactly match the suites
        with status='deferred' in the committed expected-suites.toml."""

        registry_keys = derive_denominator_keys(self._ROOT)
        data = tomllib.loads(self._MANIFEST_PATH.read_text(encoding="utf-8"))
        toml_deferred = frozenset(s["id"] for s in data["suite"] if s.get("status") == "deferred")
        # Every deferred suite in the TOML must appear in the denominator
        toml_only = toml_deferred - registry_keys
        self.assertFalse(
            toml_only,
            f"deferred suites in TOML but not in denominator: {sorted(toml_only)}",
        )

    def _find_suite(self, report, suite_id: str):
        for suite in report.suites:
            if suite.suite_id == suite_id:
                return suite
        return None


if __name__ == "__main__":
    unittest.main()
