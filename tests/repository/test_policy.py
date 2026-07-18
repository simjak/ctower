"""Behavioral tests through the Repository Policy public Interface."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.checks import verify


class RepositoryPolicyTests(unittest.TestCase):
    fixtures = Path(__file__).parent / "fixtures"

    def test_positive_repository_passes_full_profile(self) -> None:
        report = verify(self.fixtures / "positive", "full")
        self.assertTrue(report.ok, report.findings)
        self.assertGreaterEqual(report.scanned_files, 2)

    def test_private_cross_owner_import_fails(self) -> None:
        report = verify(self.fixtures / "negative", "full")
        self.assertFalse(report.ok)
        self.assertIn("architecture.private-import", {item.rule_id for item in report.errors})

    def test_authored_file_over_hard_limit_fails(self) -> None:
        with self._temporary_positive() as root:
            oversized = "value = 0\n" + "value += 1\n" * 600
            (root / "app/oversized.py").write_text(oversized, encoding="utf-8")
            report = verify(root, "fast")
        finding = next(item for item in report.errors if item.rule_id == "source.file-lines")
        self.assertEqual(finding.observed, 601)
        self.assertEqual(finding.limit, 600)

    def test_exact_unexpired_exception_downgrades_one_finding(self) -> None:
        with self._temporary_positive() as root:
            oversized = "value = 0\n" + "value += 1\n" * 600
            (root / "app/oversized.py").write_text(oversized, encoding="utf-8")
            today = datetime.now(UTC).date()
            self._write_exceptions(
                root,
                [
                    {
                        "id": "CT-TEST-001",
                        "rule": "source.file-lines",
                        "path": "app/oversized.py",
                        "temporary_limit": 650,
                        "owner": "test-owner",
                        "reason": "exercise the exact bounded exception contract",
                        "ticket": "CT-TEST-001",
                        "approver": "independent-reviewer",
                        "created_on": today.isoformat(),
                        "expires_on": (today + timedelta(days=7)).isoformat(),
                    }
                ],
            )
            report = verify(root, "fast")
        self.assertTrue(report.ok, report.findings)
        warning = next(item for item in report.warnings if item.rule_id == "source.file-lines")
        self.assertEqual(warning.exception_id, "CT-TEST-001")

    def test_expired_exception_fails_closed(self) -> None:
        with self._temporary_positive() as root:
            yesterday = datetime.now(UTC).date() - timedelta(days=1)
            self._write_exceptions(
                root,
                [
                    {
                        "id": "CT-TEST-EXPIRED",
                        "rule": "source.file-lines",
                        "path": "app/public.py",
                        "temporary_limit": 650,
                        "owner": "test-owner",
                        "reason": "expired exception must never remain invisible",
                        "ticket": "CT-TEST-EXPIRED",
                        "approver": "independent-reviewer",
                        "created_on": (yesterday - timedelta(days=7)).isoformat(),
                        "expires_on": yesterday.isoformat(),
                    }
                ],
            )
            report = verify(root, "fast")
        self.assertFalse(report.ok)
        self.assertIn("exception.invalid", {item.rule_id for item in report.errors})

    def test_generated_digest_drift_is_non_waivable(self) -> None:
        with self._temporary_positive() as root:
            manifest = {
                "schema": "ctower.generated-manifest/v1",
                "artifacts": [
                    {
                        "id": "fixture-client",
                        "generator": "fixture",
                        "tool_version": "1",
                        "command": "fixture generate",
                        "inputs": [],
                        "outputs": [{"path": "app/public.py", "sha256": "sha256:invalid"}],
                    }
                ],
            }
            (root / "generated/.generated-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            report = verify(root, "full")
        self.assertFalse(report.ok)
        self.assertIn("generated.drift", {item.rule_id for item in report.errors})

    @contextmanager
    def _temporary_positive(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            target = Path(name)
            shutil.copytree(self.fixtures / "positive", target, dirs_exist_ok=True)
            yield target

    def _write_exceptions(self, root: Path, entries: list[dict[str, object]]) -> None:
        payload = {"schema": "ctower.repository-exceptions/v1", "exceptions": entries}
        (root / "tools/checks/exceptions.yaml").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
