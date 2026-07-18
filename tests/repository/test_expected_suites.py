"""Behavioral tests through the expected-suite public Interface."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tools.checks import SuiteDisposition, verify_expected_suites


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

    def test_command_not_found_and_timeout_fail_closed(self) -> None:
        cases = {
            "missing": ('["ctower-command-that-does-not-exist"]', 30, "cannot execute"),
            "timeout": (
                '["python3", "-c", "import time; time.sleep(2)"]',
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
            f'["python3", "-c", "raise SystemExit({command_exit})"]'
            if command_exit is not None
            else f'["python3", "-m", "unittest", "discover", "-s", "{path}", "-v"]'
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


if __name__ == "__main__":
    unittest.main()
