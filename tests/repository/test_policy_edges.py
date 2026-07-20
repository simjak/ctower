"""Fail-closed edge vectors through the Repository Policy public Interface."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.checks import verify

_GENERATED_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."
_GENERATED_SCHEMA = "ctower.generated-manifest/v1"


class RepositoryPolicyEdgeTests(unittest.TestCase):
    fixtures = Path(__file__).parent / "fixtures"
    repository_policy = Path(__file__).parents[2] / "tools/checks/policy.toml"

    def test_invalid_policy_and_unknown_profile_fail_closed(self) -> None:
        with self._repository() as root:
            (root / "tools/checks/policy.toml").write_text("source = 1\n", encoding="utf-8")
            invalid = verify(root, "full")
        self.assertEqual({item.rule_id for item in invalid.errors}, {"policy.invalid"})

        unknown = verify(self.fixtures / "positive", "not-a-profile")
        self.assertEqual({item.rule_id for item in unknown.errors}, {"policy.profile"})

    def test_source_shape_budgets_and_catch_all_name_are_enforced(self) -> None:
        methods = "\n".join(f"    def method_{index}(self): return {index}" for index in range(16))
        exports = "\n".join(f"export_{index} = {index}" for index in range(26))
        branches = "\n".join(f"    if value == {index}: value += 1" for index in range(11))
        source = f"def overloaded(value):\n{branches}\n\nclass God:\n{methods}\n\n{exports}\n"
        with self._repository() as root:
            (root / "app/utils.py").write_text(source, encoding="utf-8")
            report = verify(root, "fast")
        rules = {item.rule_id for item in report.findings}
        self.assertTrue(
            {
                "architecture.catch-all-module",
                "source.class-methods",
                "source.complexity",
                "source.public-exports",
            }.issubset(rules)
        )

    def test_effective_public_exports_include_reexports_and_declared_all(self) -> None:
        imported = ", ".join(f"name_{index} as export_{index}" for index in range(26))
        declared = ", ".join(repr(f"declared_{index}") for index in range(26))
        cases = {
            "imported reexports": f"from package import {imported}\n",
            "declared all": f"__all__ = [{declared}]\n",
            "annotated declared all": f"__all__: tuple[str, ...] = ({declared})\n",
        }
        for label, source in cases.items():
            with self.subTest(label):
                with self._repository() as root:
                    (root / "app/public.py").write_text(source, encoding="utf-8")
                    report = verify(root, "fast")
                self.assertIn("source.public-exports", {item.rule_id for item in report.errors})

    def test_dynamic_all_and_star_reexports_fail_closed(self) -> None:
        cases = {
            "dynamic all": "__all__ = make_exports()\n",
            "annotated dynamic all": "__all__: tuple[str, ...] = make_exports()\n",
            "star reexport": "from package import *\n",
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                with self._repository() as root:
                    (root / "app/public.py").write_text(source, encoding="utf-8")
                    report = verify(root, "fast")
                self.assertIn("source.parse", {item.rule_id for item in report.errors})

    def test_parse_error_warning_budget_and_ambiguous_owner_are_visible(self) -> None:
        with self._repository() as root:
            (root / "app/broken.py").write_text("def broken(:\n", encoding="utf-8")
            warning_source = "value = 0\n" + "value += 1\n" * 500
            (root / "app/warning.py").write_text(warning_source, encoding="utf-8")
            policy_path = root / "tools/checks/policy.toml"
            duplicate_owner = (
                '\n[[ownership]]\nname = "duplicate"\npaths = ["app/**"]\n'
                "allowed_dependencies = []\n"
            )
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8") + duplicate_owner,
                encoding="utf-8",
            )
            report = verify(root, "fast")
        rules = {item.rule_id for item in report.findings}
        self.assertIn("source.parse", rules)
        self.assertIn("source.file-lines", rules)
        self.assertIn("architecture.unowned-source", rules)

    def test_typescript_logical_lines_are_scanned(self) -> None:
        source = """/* opening\n+        ignored\n+        */ const first = 1;
        // ignored
        const second = 2;
        """
        with self._repository() as root:
            policy_path = root / "tools/checks/policy.toml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    'extensions = [".py"]', 'extensions = [".py", ".ts"]'
                ),
                encoding="utf-8",
            )
            (root / "app/sample.ts").write_text(source, encoding="utf-8")
            report = verify(root, "fast")
        self.assertTrue(report.ok, report.findings)
        self.assertGreaterEqual(report.scanned_files, 3)

    def test_declared_src_roots_expose_forbidden_first_party_edges(self) -> None:
        with self._repository() as root:
            policy_path = root / "tools/checks/policy.toml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    'extensions = [".py"]',
                    'extensions = [".py"]\nmodule_roots = ["apps/api/src", "packages/kernel/src"]',
                )
                + """

[[ownership]]
name = "kernel"
paths = ["packages/kernel/src/kernel/**"]
allowed_dependencies = []

[[ownership]]
name = "api"
paths = ["apps/api/src/api/**"]
allowed_dependencies = []
""",
                encoding="utf-8",
            )
            kernel = root / "packages/kernel/src/kernel"
            kernel.mkdir(parents=True)
            (kernel / "_private.py").write_text("VALUE = 1\n", encoding="utf-8")
            api = root / "apps/api/src/api"
            api.mkdir(parents=True)
            (api / "main.py").write_text("from kernel._private import VALUE\n", encoding="utf-8")
            report = verify(root, "fast")
        rules = {item.rule_id for item in report.errors}
        self.assertIn("architecture.dependency", rules)
        self.assertIn("architecture.private-import", rules)

    def test_declared_src_roots_fail_unresolved_first_party_edges(self) -> None:
        with self._repository() as root:
            policy_path = root / "tools/checks/policy.toml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    'extensions = [".py"]',
                    'extensions = [".py"]\nmodule_roots = ["apps/api/src", "packages/kernel/src"]',
                )
                + """

[[ownership]]
name = "api"
paths = ["apps/api/src/api/**"]
allowed_dependencies = []
""",
                encoding="utf-8",
            )
            kernel = root / "packages/kernel/src/kernel"
            kernel.mkdir(parents=True)
            (kernel / "__init__.py").write_text("", encoding="utf-8")
            api = root / "apps/api/src/api"
            api.mkdir(parents=True)
            (api / "main.py").write_text("from kernel.missing import VALUE\n", encoding="utf-8")
            report = verify(root, "fast")
        self.assertIn("architecture.unresolved-import", {item.rule_id for item in report.errors})

    def test_record_boundary_findings_cannot_be_waived(self) -> None:
        cases = {
            "forbidden CLI-to-Record dependency": (
                "architecture.dependency",
                "from ctower_kernel.record.postgres import PostgresRecord\n",
            ),
            "private Record import": (
                "architecture.private-import",
                "from ctower_kernel.record._private import VALUE\n",
            ),
            "unresolved first-party Record import": (
                "architecture.unresolved-import",
                "from ctower_kernel.record.missing import VALUE\n",
            ),
        }
        for label, (rule_id, source) in cases.items():
            with self.subTest(label=label):
                with self._architecture_repository(rule_id, source) as root:
                    report = verify(root, "fast")
                matching = [item for item in report.findings if item.rule_id == rule_id]
                self.assertEqual(len(matching), 1, report.findings)
                self.assertEqual(matching[0].severity.value, "error")
                self.assertIsNone(matching[0].exception_id)

    def test_exception_store_rejects_malformed_unmatched_and_over_limit_entries(self) -> None:
        today = datetime.now(UTC).date()
        cases = {
            "wrong schema": {"schema": "wrong", "exceptions": []},
            "not list": {"schema": "ctower.repository-exceptions/v1", "exceptions": {}},
            "wrong fields": {"schema": "ctower.repository-exceptions/v1", "exceptions": [{}]},
            "bad date": self._exception_payload(created_on="invalid"),
            "too long": self._exception_payload(
                created_on=today.isoformat(),
                expires_on=(today + timedelta(days=31)).isoformat(),
            ),
            "bad limit": self._exception_payload(temporary_limit=0),
        }
        for label, payload in cases.items():
            with self.subTest(label):
                with self._repository() as root:
                    self._write_exceptions(root, payload)
                    report = verify(root, "fast")
                self.assertIn("exception.invalid", {item.rule_id for item in report.errors})

        with self._repository() as root:
            self._write_exceptions(root, self._exception_payload(path="app/public.py"))
            unmatched = verify(root, "fast")
        self.assertIn("exception.unmatched", {item.rule_id for item in unmatched.errors})

        with self._repository() as root:
            oversized = "value = 0\n" + "value += 1\n" * 600
            (root / "app/oversized.py").write_text(oversized, encoding="utf-8")
            self._write_exceptions(
                root,
                self._exception_payload(path="app/oversized.py", temporary_limit=600),
            )
            over_limit = verify(root, "fast")
        self.assertIn("source.file-lines", {item.rule_id for item in over_limit.errors})

    def test_generated_manifest_all_invalid_shapes_and_matching_digest(self) -> None:
        cases: list[object] = [
            {"schema": _GENERATED_SCHEMA, "artifacts": []},
            self._manifest([], schema="wrong"),
            self._manifest({}),
            self._manifest(["bad"]),
            self._manifest([{}]),
            self._manifest([self._artifact(inputs={}, outputs=[])]),
            self._manifest([self._artifact(inputs=[{}], outputs=[])]),
            {**self._manifest([]), "unknown": True},
            self._manifest([self._artifact(inputs=[], outputs=[], unknown=True)]),
            self._manifest(
                [
                    self._artifact(
                        inputs=[],
                        outputs=[
                            {
                                "path": "generated/output.py",
                                "sha256": f"sha256:{'0' * 64}",
                                "unknown": True,
                            }
                        ],
                    )
                ]
            ),
        ]
        for index, payload in enumerate(cases):
            with self.subTest(index=index):
                with self._repository() as root:
                    self._write_generated(root, payload)
                    report = verify(root, "full")
                self.assertFalse(report.ok)
                self.assertTrue(
                    {item.rule_id for item in report.errors}
                    & {"generated.drift", "generated.manifest"}
                )

        with self._repository() as root:
            generated = root / "generated/output.py"
            generated.write_text("VALUE = 1\n", encoding="utf-8")
            digest = f"sha256:{hashlib.sha256(generated.read_bytes()).hexdigest()}"
            payload = self._manifest(
                [
                    self._artifact(
                        inputs=[], outputs=[{"path": "generated/output.py", "sha256": digest}]
                    )
                ]
            )
            self._write_generated(root, payload)
            report = verify(root, "full")
        self.assertTrue(report.ok, report.findings)

    def test_generated_json_output_requires_exact_do_not_edit_notice(self) -> None:
        with self._repository() as root:
            generated = root / "generated/output.json"
            generated.write_text('{"value": 1}\n', encoding="utf-8")
            self._write_output_manifest(root, generated)
            missing = verify(root, "full")

            generated.write_text(
                json.dumps({"_notice": _GENERATED_NOTICE, "value": 1}) + "\n",
                encoding="utf-8",
            )
            self._write_output_manifest(root, generated)
            present = verify(root, "full")

        self.assertIn("generated.notice", {item.rule_id for item in missing.errors})
        self.assertTrue(present.ok, present.findings)

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(self.fixtures / "positive", root, dirs_exist_ok=True)
            yield root

    @contextmanager
    def _architecture_repository(self, rule_id: str, source: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            policy = root / "tools/checks/policy.toml"
            policy.parent.mkdir(parents=True)
            shutil.copyfile(self.repository_policy, policy)
            cli = root / "apps/ctowerctl/src/ctowerctl/main.py"
            cli.parent.mkdir(parents=True)
            cli.write_text(source, encoding="utf-8")
            record = root / "packages/ctower-kernel/src/ctower_kernel/record"
            record.mkdir(parents=True)
            (record.parent / "__init__.py").write_text("", encoding="utf-8")
            (record / "__init__.py").write_text("", encoding="utf-8")
            (record / "postgres.py").write_text("class PostgresRecord: pass\n", encoding="utf-8")
            (record / "_private.py").write_text("VALUE = 1\n", encoding="utf-8")
            self._write_exceptions(
                root,
                self._exception_payload(
                    rule=rule_id,
                    path="apps/ctowerctl/src/ctowerctl/main.py",
                    temporary_limit=1,
                ),
            )
            yield root

    def _write_exceptions(self, root: Path, payload: object) -> None:
        (root / "tools/checks/exceptions.yaml").write_text(json.dumps(payload), encoding="utf-8")

    def _exception_payload(self, **updates: object) -> dict[str, object]:
        today = datetime.now(UTC).date()
        entry: dict[str, object] = {
            "id": "CT-EDGE-001",
            "rule": "source.file-lines",
            "path": "app/not-present.py",
            "temporary_limit": 650,
            "owner": "test-owner",
            "reason": "exercise the exact exception contract",
            "ticket": "CT-EDGE-001",
            "approver": "independent-reviewer",
            "created_on": today.isoformat(),
            "expires_on": (today + timedelta(days=7)).isoformat(),
        }
        entry.update(updates)
        return {"schema": "ctower.repository-exceptions/v1", "exceptions": [entry]}

    def _write_generated(self, root: Path, payload: object) -> None:
        (root / "generated/.generated-manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def _artifact(self, *, inputs: object, outputs: object, **unknown: object) -> dict[str, object]:
        artifact: dict[str, object] = {
            "id": "fixture",
            "generator": "fixture",
            "tool_version": "1",
            "command": "fixture generate",
            "inputs": inputs,
            "outputs": outputs,
        }
        artifact.update(unknown)
        return artifact

    def _manifest(self, artifacts: object, *, schema: str = _GENERATED_SCHEMA) -> dict[str, object]:
        return {
            "_notice": _GENERATED_NOTICE,
            "schema": schema,
            "artifacts": artifacts,
        }

    def _write_output_manifest(self, root: Path, output: Path) -> None:
        digest = f"sha256:{hashlib.sha256(output.read_bytes()).hexdigest()}"
        self._write_generated(
            root,
            self._manifest(
                [
                    self._artifact(
                        inputs=[],
                        outputs=[
                            {
                                "path": output.relative_to(root).as_posix(),
                                "sha256": digest,
                            }
                        ],
                    )
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
