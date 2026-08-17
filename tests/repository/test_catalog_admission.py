"""AC-CAT-01 admission proof for tenant catalog content."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from tools.checks import verify

_STABLE_REFUSAL = "tenant-catalog-content-in-public-repository"
_ROOT = Path(__file__).parents[2]
_FIXTURES = Path(__file__).parent / "fixtures"
_CANONICAL_POLICY = _ROOT / "tools/checks/policy.toml"


class CatalogAdmissionTests(unittest.TestCase):
    def test_tenant_catalog_representations_refuse_by_stable_name(self) -> None:
        for label, relative, tenant_content, public_content in _catalog_representations():
            with self.subTest(label=label):
                self._assert_tenant_artifact_refused(relative, tenant_content)
                self._assert_public_artifact_admitted(relative, public_content)

    def test_conflicting_duplicate_json_names_refuse_at_every_object_depth(self) -> None:
        for label, payload in _duplicate_json_payloads():
            with self.subTest(label=label):
                self._assert_tenant_artifact_refused(
                    f"packs/components/private-skill-{label}.json", payload
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
        with self._repository(policy_source=_CANONICAL_POLICY) as root:
            relative = "packs/components/private-skill.yaml"
            self._write_tenant_artifact(root, relative)
            self._write_valid_exception(root, relative)

            self._assert_non_waivable_report(root, relative)

    def test_non_waivable_regression_detects_canonical_policy_removal(self) -> None:
        with self._repository(policy_source=_CANONICAL_POLICY) as root:
            relative = "packs/components/private-skill.yaml"
            self._write_tenant_artifact(root, relative)
            self._write_valid_exception(root, relative)

            policy = root / "tools/checks/policy.toml"
            policy_text = policy.read_text(encoding="utf-8")
            protected_entry = f'  "{_STABLE_REFUSAL}",\n'
            self.assertEqual(policy_text.count(protected_entry), 1)
            policy.write_text(policy_text.replace(protected_entry, "", 1), encoding="utf-8")

            with self.assertRaises(AssertionError):
                self._assert_non_waivable_report(root, relative)

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

    def _assert_public_artifact_admitted(self, relative: str, content: str) -> None:
        with self._repository() as root:
            artifact = root / relative
            artifact.parent.mkdir(parents=True)
            artifact.write_text(content, encoding="utf-8")

            report = verify(root, "full")

        self.assertTrue(report.ok, report.findings)

    def _write_tenant_artifact(self, root: Path, relative: str) -> None:
        artifact = root / relative
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            "catalog_content: tenant\nname: private operating instructions\n",
            encoding="utf-8",
        )

    def _write_valid_exception(self, root: Path, relative: str) -> None:
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
        (root / "tools/checks/exceptions.yaml").write_text(json.dumps(exception), encoding="utf-8")

    def _assert_non_waivable_report(self, root: Path, relative: str) -> None:
        report = verify(root, "full")

        self.assertFalse(report.ok, report.findings)
        self.assertTrue(
            any(
                finding.rule_id == _STABLE_REFUSAL and finding.path == relative
                for finding in report.errors
            ),
            report.findings,
        )
        self.assertFalse(
            any(
                finding.rule_id == _STABLE_REFUSAL and finding.path == relative
                for finding in report.warnings
            ),
            report.findings,
        )

    @contextmanager
    def _repository(self, policy_source: Path | None = None) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(_FIXTURES / "positive", root, dirs_exist_ok=True)
            if policy_source is not None:
                shutil.copyfile(policy_source, root / "tools/checks/policy.toml")
            yield root


def _catalog_representations() -> Iterator[tuple[str, str, str, str]]:
    for suffix in (".json", ".yaml", ".yml"):
        for label, document in _catalog_documents():
            tenant = _render_document(document, suffix, flow=label == "flow")
            public = _render_document(
                _replace_marker(document, "synthetic"), suffix, flow=label == "flow"
            )
            yield (
                f"{label}-{suffix[1:]}",
                f"packs/components/private-skill-{label}{suffix}",
                tenant,
                public,
            )
    for filename in ("SKILL.md", "PERSONA.md", "INSTRUCTIONS.txt"):
        tenant = (
            "---\ncatalog_content: tenant\nname: private operating instructions\n---\n\n# Private\n"
        )
        public = "---\ncatalog_content: synthetic\nname: generic example\n---\n\n# Public\n"
        yield (
            f"frontmatter-{filename.lower()}",
            f"packs/components/skills/private-skill/{filename}",
            tenant,
            public,
        )


def _catalog_documents() -> tuple[tuple[str, dict[str, object]], ...]:
    return (
        (
            "root",
            {"catalog_content": "tenant", "name": "private operating instructions"},
        ),
        (
            "nested",
            {
                "metadata": [
                    {
                        "catalog_content": "tenant",
                        "name": "private operating instructions",
                    }
                ]
            },
        ),
        (
            "flow",
            {"catalog_content": "tenant", "name": "private operating instructions"},
        ),
    )


def _duplicate_json_payloads() -> tuple[tuple[str, str], ...]:
    return (
        (
            "duplicate-root",
            '{"catalog_content":"tenant","catalog_content":"synthetic","name":"private"}\n',
        ),
        (
            "duplicate-nested",
            '{"metadata":{"catalog_content":"tenant","catalog_content":"synthetic"}}\n',
        ),
    )


def _render_document(document: object, suffix: str, *, flow: bool) -> str:
    if suffix == ".json":
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    yaml = YAML(typ="safe")
    yaml.default_flow_style = flow
    output = StringIO()
    yaml.dump(document, output)
    return output.getvalue()


def _replace_marker(value: object, replacement: str) -> object:
    if isinstance(value, dict):
        return {
            key: replacement if key == "catalog_content" else _replace_marker(item, replacement)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_marker(item, replacement) for item in value]
    return value


if __name__ == "__main__":
    unittest.main()
