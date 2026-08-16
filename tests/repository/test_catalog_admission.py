"""AC-CAT-01 admission proof for tenant catalog content."""

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

_STABLE_REFUSAL = "tenant-catalog-content-in-public-repository"
_FIXTURES = Path(__file__).parent / "fixtures"


class CatalogAdmissionTests(unittest.TestCase):
    def test_compact_json_tenant_catalog_artifact_refuses_by_stable_name(self) -> None:
        self._assert_tenant_artifact_refused(
            "packs/components/private-skill.json",
            '{"catalog_content":"tenant","name":"private operating instructions"}\n',
        )

    def test_pretty_json_tenant_catalog_artifact_refuses_by_stable_name(self) -> None:
        self._assert_tenant_artifact_refused(
            "packs/components/private-skill.json",
            "{\n"
            '  "\\u0063atalog_content": "tenant",\n'
            '  "name": "private operating instructions"\n'
            "}\n",
        )

    def test_yaml_block_tenant_catalog_artifact_refuses_by_stable_name(self) -> None:
        self._assert_tenant_artifact_refused(
            "packs/components/private-skill.yaml",
            "'catalog_content': tenant\nname: private operating instructions\n",
        )

    def test_yaml_flow_tenant_catalog_artifact_refuses_by_stable_name(self) -> None:
        self._assert_tenant_artifact_refused(
            "packs/components/private-skill.yaml",
            "{'catalog_content': tenant, name: private operating instructions}\n",
        )

    def test_unreadable_tenant_catalog_artifact_refuses_by_stable_name(self) -> None:
        with self._repository() as root:
            artifact = root / "packs/components/private-skill.yaml"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("catalog_content: [tenant\n", encoding="utf-8")

            report = verify(root, "full")

        self.assertFalse(report.ok, report.findings)
        self.assertTrue(
            any(finding.rule_id == _STABLE_REFUSAL for finding in report.errors),
            report.findings,
        )
        self.assertTrue(
            any(finding.path == "packs/components/private-skill.yaml" for finding in report.errors),
            report.findings,
        )

    def test_tenant_catalog_refusal_is_not_waivable(self) -> None:
        with self._repository() as root:
            relative = "packs/components/private-skill.yaml"
            artifact = root / relative
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "catalog_content: tenant\nname: private operating instructions\n",
                encoding="utf-8",
            )
            today = datetime.now(UTC).date()
            exception = {
                "schema": "ctower.repository-exceptions/v1",
                "exceptions": [
                    {
                        "id": "CT-TEST-519",
                        "rule": _STABLE_REFUSAL,
                        "path": relative,
                        "temporary_limit": 1,
                        "owner": "test-owner",
                        "reason": "prove tenant-content boundary cannot be waived",
                        "ticket": "CT-TEST-519",
                        "approver": "independent-reviewer",
                        "created_on": today.isoformat(),
                        "expires_on": (today + timedelta(days=7)).isoformat(),
                    }
                ],
            }
            (root / "tools/checks/exceptions.yaml").write_text(
                json.dumps(exception), encoding="utf-8"
            )

            report = verify(root, "full")

        self.assertFalse(report.ok, report.findings)
        self.assertTrue(
            any(finding.rule_id == _STABLE_REFUSAL for finding in report.errors),
            report.findings,
        )
        self.assertFalse(
            any(finding.rule_id == _STABLE_REFUSAL for finding in report.warnings),
            report.findings,
        )

    def _assert_tenant_artifact_refused(self, relative: str, content: str) -> None:
        with self._repository() as root:
            artifact = root / relative
            artifact.parent.mkdir(parents=True)
            artifact.write_text(content, encoding="utf-8")

            report = verify(root, "full")

            self.assertFalse(report.ok, report.findings)
            self.assertEqual(
                [
                    (finding.rule_id, finding.path)
                    for finding in report.errors
                    if finding.rule_id == _STABLE_REFUSAL
                ],
                [(_STABLE_REFUSAL, relative)],
                report.findings,
            )

            artifact.unlink()
            clean_report = verify(root, "full")

        self.assertTrue(clean_report.ok, clean_report.findings)

    def test_public_synthetic_catalog_artifact_is_admitted(self) -> None:
        with self._repository() as root:
            artifact = root / "examples/catalog/synthetic-skill.yaml"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "catalog_content: synthetic\nname: generic example\n",
                encoding="utf-8",
            )

            report = verify(root, "full")

        self.assertTrue(report.ok, report.findings)

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(_FIXTURES / "positive", root, dirs_exist_ok=True)
            yield root


if __name__ == "__main__":
    unittest.main()
