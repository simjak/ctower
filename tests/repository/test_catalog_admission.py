"""AC-CAT-01 admission proof for tenant catalog content."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tools.checks import verify

_STABLE_REFUSAL = "tenant-catalog-content-in-public-repository"
_FIXTURES = Path(__file__).parent / "fixtures"


class CatalogAdmissionTests(unittest.TestCase):
    def test_injected_tenant_catalog_artifact_refuses_by_stable_name(self) -> None:
        with self._repository() as root:
            artifact = root / "packs/components/private-skill.yaml"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "catalog_content: " + "tenant\nname: private operating instructions\n",
                encoding="utf-8",
            )

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
