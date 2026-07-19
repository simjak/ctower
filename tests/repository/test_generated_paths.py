"""Generated-manifest filesystem trust-boundary tests through the public Interface."""

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

from tools.checks import PolicyReport, verify

_GENERATED_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."


class GeneratedPathPolicyTests(unittest.TestCase):
    fixtures = Path(__file__).parent / "fixtures"

    def test_allowed_authored_inputs_and_generated_outputs_pass(self) -> None:
        with self._repository() as root:
            root_input = root / "ROOT.md"
            root_input.write_text("authored root file\n", encoding="utf-8")
            policy = root / "tools/checks/policy.toml"
            policy.write_text(
                policy.read_text(encoding="utf-8").replace(
                    "input_files = []", 'input_files = ["ROOT.md"]'
                ),
                encoding="utf-8",
            )
            output = root / "generated/output.py"
            output.write_text("VALUE = 1\n", encoding="utf-8")
            self._write_manifest(
                root,
                inputs=(root / "app/public.py", root_input),
                outputs=(output,),
            )

            report = verify(root, "full")

        self.assertTrue(report.ok, report.findings)

    def test_authored_file_cannot_be_declared_as_generated_output(self) -> None:
        with self._repository() as root:
            authored = root / "app/public.py"
            self._write_manifest(root, inputs=(), outputs=(authored,))

            report = verify(root, "full")

        self._assert_manifest_error(report)

    def test_input_must_be_in_an_explicit_authored_root_or_file(self) -> None:
        with self._repository() as root:
            disallowed = root / "other/input.py"
            disallowed.parent.mkdir()
            disallowed.write_text("VALUE = 1\n", encoding="utf-8")
            self._write_manifest(root, inputs=(disallowed,), outputs=())

            report = verify(root, "full")

        self._assert_manifest_error(report)

    def test_lexical_escape_is_rejected_before_filesystem_access(self) -> None:
        with self._repository() as root:
            self._write_manifest_entries(
                root,
                inputs=(),
                outputs=(("generated/../app/public.py", self._digest(root / "app/public.py")),),
            )

            report = verify(root, "full")

        self._assert_manifest_error(report)

    def test_leaf_symlinks_and_external_targets_are_rejected(self) -> None:
        with self._repository() as root, tempfile.TemporaryDirectory() as external_name:
            input_link = root / "app/input-link.py"
            input_link.symlink_to(root / "app/public.py")
            self._write_manifest(root, inputs=(input_link,), outputs=())
            input_report = verify(root, "full")

            internal_target = root / "generated/internal-target.py"
            internal_target.write_text("VALUE = 1\n", encoding="utf-8")
            internal_link = root / "generated/internal-link.py"
            internal_link.symlink_to(internal_target)
            self._write_manifest(root, inputs=(), outputs=(internal_link,))
            internal_report = verify(root, "full")

            external_target = Path(external_name) / "external.py"
            external_target.write_text("VALUE = 2\n", encoding="utf-8")
            external_link = root / "generated/external-link.py"
            external_link.symlink_to(external_target)
            self._write_manifest(root, inputs=(), outputs=(external_link,))
            external_report = verify(root, "full")

        self._assert_manifest_error(input_report)
        self._assert_manifest_error(internal_report)
        self._assert_manifest_error(external_report)

    def test_symlinked_parent_is_rejected_for_inputs_and_outputs(self) -> None:
        with self._repository() as root, tempfile.TemporaryDirectory() as external_name:
            external = Path(external_name)
            external_input = external / "input.py"
            external_input.write_text("INPUT = 1\n", encoding="utf-8")
            authored_parent = root / "app/linked"
            authored_parent.symlink_to(external, target_is_directory=True)
            self._write_manifest(root, inputs=(authored_parent / "input.py",), outputs=())
            input_report = verify(root, "full")

            external_output = external / "output.py"
            external_output.write_text("OUTPUT = 1\n", encoding="utf-8")
            generated_parent = root / "generated/linked"
            generated_parent.symlink_to(external, target_is_directory=True)
            self._write_manifest(root, inputs=(), outputs=(generated_parent / "output.py",))
            output_report = verify(root, "full")

        self._assert_manifest_error(input_report)
        self._assert_manifest_error(output_report)

    def test_directories_and_missing_files_are_manifest_errors(self) -> None:
        with self._repository() as root:
            input_directory = root / "app/directory"
            input_directory.mkdir()
            self._write_manifest_entries(
                root,
                inputs=(("app/directory", f"sha256:{'0' * 64}"),),
                outputs=(),
            )
            input_directory_report = verify(root, "full")

            self._write_manifest_entries(
                root,
                inputs=(("app/missing.py", f"sha256:{'0' * 64}"),),
                outputs=(),
            )
            input_missing_report = verify(root, "full")

            directory = root / "generated/directory"
            directory.mkdir()
            self._write_manifest_entries(
                root,
                inputs=(),
                outputs=(("generated/directory", f"sha256:{'0' * 64}"),),
            )
            directory_report = verify(root, "full")

            self._write_manifest_entries(
                root,
                inputs=(),
                outputs=(("generated/missing.py", f"sha256:{'0' * 64}"),),
            )
            missing_report = verify(root, "full")

        self._assert_manifest_error(input_directory_report)
        self._assert_manifest_error(input_missing_report)
        self._assert_manifest_error(directory_report)
        self._assert_manifest_error(missing_report)

    def test_generated_notice_cannot_be_downgraded_by_exception(self) -> None:
        with self._repository() as root:
            output = root / "generated/output.json"
            output.write_text('{"value": 1}\n', encoding="utf-8")
            self._write_manifest(root, inputs=(), outputs=(output,))
            today = datetime.now(UTC).date()
            exception = {
                "id": "CT-NOTICE-001",
                "rule": "generated.notice",
                "path": "generated/output.json",
                "temporary_limit": 1,
                "owner": "test-owner",
                "reason": "prove generated integrity cannot be waived",
                "ticket": "CT-NOTICE-001",
                "approver": "independent-reviewer",
                "created_on": today.isoformat(),
                "expires_on": (today + timedelta(days=7)).isoformat(),
            }
            self._write_exceptions(root, [exception])

            report = verify(root, "full")

        self.assertIn("generated.notice", {item.rule_id for item in report.errors})
        self.assertNotIn("generated.notice", {item.rule_id for item in report.warnings})

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(self.fixtures / "positive", root, dirs_exist_ok=True)
            yield root

    def _write_manifest(
        self, root: Path, *, inputs: tuple[Path, ...], outputs: tuple[Path, ...]
    ) -> None:
        self._write_manifest_entries(
            root,
            inputs=tuple(
                (path.relative_to(root).as_posix(), self._digest(path)) for path in inputs
            ),
            outputs=tuple(
                (path.relative_to(root).as_posix(), self._digest(path)) for path in outputs
            ),
        )

    def _write_manifest_entries(
        self,
        root: Path,
        *,
        inputs: tuple[tuple[str, str], ...],
        outputs: tuple[tuple[str, str], ...],
    ) -> None:
        artifact = {
            "id": "fixture",
            "generator": "fixture",
            "tool_version": "1",
            "command": "fixture generate",
            "inputs": [{"path": path, "sha256": digest} for path, digest in inputs],
            "outputs": [{"path": path, "sha256": digest} for path, digest in outputs],
        }
        manifest = {
            "_notice": _GENERATED_NOTICE,
            "schema": "ctower.generated-manifest/v1",
            "artifacts": [artifact],
        }
        (root / "generated/.generated-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def _write_exceptions(self, root: Path, entries: list[dict[str, object]]) -> None:
        payload = {"schema": "ctower.repository-exceptions/v1", "exceptions": entries}
        (root / "tools/checks/exceptions.yaml").write_text(json.dumps(payload), encoding="utf-8")

    def _digest(self, path: Path) -> str:
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

    def _assert_manifest_error(self, report: PolicyReport) -> None:
        self.assertIn("generated.manifest", {item.rule_id for item in report.errors})


if __name__ == "__main__":
    unittest.main()
