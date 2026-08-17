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
_TENANT_VALUE = "tenant"
_PUBLIC_VALUE = "synthetic"
_BYTE_ORDER_MARK = "\ufeff"


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

    def test_unterminated_frontmatter_refuses_by_stable_name(self) -> None:
        for label, content in (
            ("no-delimiter", "---\ncatalog_content: tenant\nname: private\n"),
            ("scanner-error", "---\ncatalog_content: tenant\n\tname: private\n"),
        ):
            with self.subTest(label=label):
                with self._repository() as root:
                    artifact = root / "packs/components/skills/private-skill/SKILL.md"
                    artifact.parent.mkdir(parents=True)
                    artifact.write_text(content, encoding="utf-8")

                    report = verify(root, "full")

                self.assertFalse(report.ok, report.findings)
                self.assertTrue(
                    any(
                        finding.rule_id == _STABLE_REFUSAL
                        and finding.path == "packs/components/skills/private-skill/SKILL.md"
                        and "could not be classified" in finding.message
                        for finding in report.errors
                    ),
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

    def test_semantic_documents_refuse_wherever_the_class_occurs(self) -> None:
        for label, relative, tenant_content, public_content in _documents_outside_catalog():
            with self.subTest(label=label):
                self._assert_admission(relative, tenant_content, refused=True)
                self._assert_admission(relative, public_content, refused=False)

    def test_multi_document_streams_are_judged_document_by_document(self) -> None:
        for label, relative, tenant_content, public_content in _multi_document_streams():
            with self.subTest(label=label):
                self._assert_admission(relative, tenant_content, refused=True)
                self._assert_admission(relative, public_content, refused=False)

    def test_stream_composition_decides_admission_not_the_spelling_of_the_bytes(self) -> None:
        for label, relative, content, refused in _composition_boundary():
            with self.subTest(label=label):
                self._assert_admission(relative, content, refused=refused)

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

    def _assert_admission(self, relative: str, content: str | bytes, *, refused: bool) -> None:
        with self._repository() as root:
            artifact = root / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                artifact.write_bytes(content)
            else:
                artifact.write_text(content, encoding="utf-8")

            report = verify(root, "full")

        refusals = [
            (finding.rule_id, finding.path)
            for finding in report.errors
            if finding.rule_id == _STABLE_REFUSAL
        ]
        self.assertEqual(
            refusals, [(_STABLE_REFUSAL, relative)] if refused else [], report.findings
        )
        self.assertEqual(report.ok, not refused, report.findings)

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


def _documents_outside_catalog() -> Iterator[tuple[str, str, str, str]]:
    """Semantic documents at paths the catalog artifact registry never covers."""

    for label, key, value in _spellings():
        yield (
            f"json-{label}",
            "docs/private-catalog.json",
            f'{{"{key}":"{value}","name":"private"}}\n',
            f'{{"{key}":"synthetic","name":"generic example"}}\n',
        )
        yield (
            f"yaml-{label}",
            "contracts/private-catalog.yml",
            f'metadata:\n  "{key}": "{value}"\nname: private\n',
            f'metadata:\n  "{key}": "synthetic"\nname: generic example\n',
        )
        yield (
            f"frontmatter-{label}",
            "docs/notes/private-runbook.md",
            f'---\nmetadata:\n  "{key}": "{value}"\nname: private\n---\n\n# Runbook\n',
            f'---\nmetadata:\n  "{key}": "synthetic"\nname: generic example\n---\n\n# Runbook\n',
        )
    for label, key, value in _yaml_only_spellings():
        yield (
            f"yaml-{label}",
            "contracts/private-catalog.yml",
            f'metadata:\n  "{key}": "{value}"\nname: private\n',
            f'metadata:\n  "{key}": "synthetic"\nname: generic example\n',
        )
        yield (
            f"frontmatter-{label}",
            "docs/notes/private-runbook.md",
            f'---\nmetadata:\n  "{key}": "{value}"\nname: private\n---\n\n# Runbook\n',
            f'---\nmetadata:\n  "{key}": "synthetic"\nname: generic example\n---\n\n# Runbook\n',
        )


def _multi_document_streams() -> Iterator[tuple[str, str, str, str]]:
    """Streams that no single-document composition can decode, marker anywhere in them."""

    for label, relative, template in _stream_templates():
        yield (
            label,
            relative,
            _rendered(template, _TENANT_VALUE),
            _rendered(template, _PUBLIC_VALUE),
        )


def _stream_templates() -> tuple[tuple[str, str, str], ...]:
    """One template per stream shape; only the decoded class varies between renderings."""

    key = "catalog_content"
    escaped = _unicode_escaped(key)
    hex_key = _hex_escaped(key)
    return (
        (
            "multi-document-yaml-literal-doc2",
            "docs/private-multidoc.yaml",
            f'name: public first document\n---\n"{key}": <VALUE>\n',
        ),
        (
            "multi-document-yaml-escaped-doc2",
            "docs/private-multidoc-escaped.yaml",
            f'name: public first document\n---\n"{escaped}": <VALUE>\n',
        ),
        (
            "multi-document-yaml-escaped-doc1",
            "docs/private-multidoc-escaped-doc1.yaml",
            f'"{escaped}": <VALUE>\n---\nname: second document\n',
        ),
        (
            "bom-three-document-yaml-hex-escaped-doc3",
            "reference/streams/private-inventory.yml",
            f"{_BYTE_ORDER_MARK}---\nname: first\n...\n---\nscope: second\n...\n"
            f'---\ninventory:\n  - entry:\n      "{hex_key}": "<HEX_VALUE>"\n',
        ),
        (
            "concatenated-json-escaped-doc1",
            "docs/private-concat.json",
            f'{{"{escaped}":"<VALUE>"}}\n{{"name":"second"}}\n',
        ),
        (
            "juxtaposed-json-escaped-doc3",
            "reference/streams/private-registry.json",
            f'{{"name":"first"}}{{"scope":"second"}}{{"{escaped}":"<UNICODE_VALUE>"}}',
        ),
        (
            "bom-json-escaped",
            "docs/private-bom.json",
            f'{_BYTE_ORDER_MARK}{{"{escaped}":"<VALUE>","name":"private"}}\n',
        ),
    )


def _rendered(template: str, value: str) -> str:
    return (
        template.replace("<VALUE>", value)
        .replace("<UNICODE_VALUE>", _unicode_escaped(value))
        .replace("<HEX_VALUE>", _hex_escaped(value))
    )


def _composition_boundary() -> tuple[tuple[str, str, str | bytes, bool], ...]:
    """A stream is refused when no document composes, whatever its bytes spell."""

    return (
        (
            "yaml-naming-the-field",
            "docs/private-catalog-broken.yaml",
            "catalog_content: [tenant\n",
            True,
        ),
        ("json-naming-nothing", "docs/notes/draft.json", '{"name": "private",\n', True),
        ("json-trailing-garbage", "docs/notes/trailing.json", '{"name":"public"} tenant\n', True),
        (
            "yaml-second-document-unparsable",
            "docs/notes/half-broken.yaml",
            "name: public first document\n---\nvalues: [1\n",
            True,
        ),
        (
            "frontmatter-scanner-error",
            "docs/notes/private-runbook.md",
            "---\nname: private\n\tscope: broken\n",
            True,
        ),
        (
            "undecodable-bytes-in-the-registry",
            "packs/components/private-skill.yaml",
            b"\xff\xfe",
            True,
        ),
        ("undecodable-bytes-outside-the-registry", "docs/notes/binary.dat", b"\xff\xfe", False),
        (
            "zero-document-json-stream",
            "docs/notes/placeholder.json",
            f"{_BYTE_ORDER_MARK}  \n",
            False,
        ),
        (
            "prose-naming-the-field-is-not-a-document",
            "docs/notes/prose.md",
            "# Notes\n\nThe catalog_content field marks tenant artifacts.\n",
            False,
        ),
    )


def _unicode_escaped(value: str) -> str:
    return f"\\u{ord(value[0]):04x}{value[1:]}"


def _hex_escaped(value: str) -> str:
    return f"\\x{ord(value[0]):02x}{value[1:]}"


def _spellings() -> tuple[tuple[str, str, str], ...]:
    """The one semantic field, written the ways JSON and YAML both decode."""

    return (
        ("literal", "catalog_content", "tenant"),
        ("unicode-escaped-key", "\\u0063atalog_content", "tenant"),
        ("unicode-escaped-value", "catalog_content", "\\u0074enant"),
    )


def _yaml_only_spellings() -> tuple[tuple[str, str, str], ...]:
    """Hexadecimal escapes are legal YAML and rejected by JSON."""

    return (("hex-escaped-key-and-value", "\\x63atalog_content", "\\x74enant"),)


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
    for label, scalar_prefix in _frontmatter_scalar_prefixes():
        tenant = (
            f"---\n{scalar_prefix}catalog_content: tenant\n"
            "name: private operating instructions\n---\n\n# Private\n"
        )
        public = (
            f"---\n{scalar_prefix}catalog_content: synthetic\n"
            "name: generic example\n---\n\n# Public\n"
        )
        yield (
            f"frontmatter-scalar-{label}",
            "packs/components/skills/private-skill/SKILL.md",
            tenant,
            public,
        )


def _frontmatter_scalar_prefixes() -> tuple[tuple[str, str], ...]:
    return (
        ("block-dash", "description: |\n  public preface\n  ---\n"),
        ("block-dots", "description: |\n  public preface\n  ...\n"),
        ("double-quoted-delimiters", 'description: "public preface\n  ---\n  ..."\n'),
        ("folded-nested-dots", "metadata:\n  description: >\n    public preface\n    ...\n"),
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
