"""Closed-world generated ownership through the public repository-policy Interface."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tools.checks import PolicyReport, verify

_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."


class GeneratedInventoryTests(unittest.TestCase):
    fixtures = Path(__file__).parent / "fixtures"

    def test_manifest_is_metadata_and_exact_declared_inventory_passes(self) -> None:
        with self._repository() as root:
            output = root / "generated/nested/output.py"
            output.parent.mkdir()
            output.write_text("VALUE = 1\n", encoding="utf-8")
            self._write_manifest(root, (("first", (output,)),))

            report = verify(root, "full")

        self.assertTrue(report.ok, report.findings)

    def test_extra_root_and_nested_regular_files_fail_closed(self) -> None:
        for relative in ("generated/extra.py", "generated/nested/extra.py"):
            with self.subTest(relative=relative), self._repository() as root:
                extra = root / relative
                extra.parent.mkdir(parents=True, exist_ok=True)
                extra.write_text("VALUE = 1\n", encoding="utf-8")

                report = verify(root, "full")

            self._assert_inventory_error(report, relative)

    def test_bytecode_under_generated_is_not_inventory(self) -> None:
        with self._repository() as root:
            output = root / "generated/nested/output.py"
            output.parent.mkdir()
            output.write_text("VALUE = 1\n", encoding="utf-8")
            self._write_manifest(root, (("first", (output,)),))
            pycache = root / "generated/__pycache__"
            pycache.mkdir()
            (pycache / "x.pyc").write_bytes(b"\x00")
            nested_pycache = root / "generated/nested/__pycache__"
            nested_pycache.mkdir()
            (nested_pycache / "output.cpython-312.pyc").write_bytes(b"\x00")

            report = verify(root, "full")

        self.assertTrue(report.ok, report.findings)

    def test_output_path_cannot_be_owned_by_multiple_artifacts(self) -> None:
        with self._repository() as root:
            output = root / "generated/output.py"
            output.write_text("VALUE = 1\n", encoding="utf-8")
            self._write_manifest(root, (("first", (output,)), ("second", (output,))))

            report = verify(root, "full")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("globally unique" in finding.message for finding in report.errors),
            report.findings,
        )

    def test_undeclared_and_declared_symlinks_fail_without_following_targets(self) -> None:
        with self._repository() as root, tempfile.TemporaryDirectory() as outside_name:
            outside = Path(outside_name)
            target = outside / "outside.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            link = root / "generated/output.py"
            link.symlink_to(target)

            undeclared = verify(root, "full")
            self._write_manifest_entries(
                root, (("first", (("generated/output.py", self._zero()),)),)
            )
            declared = verify(root, "full")

        self._assert_inventory_error(undeclared, "generated/output.py")
        self.assertFalse(declared.ok)
        self.assertTrue(
            any("symlink" in item.message for item in declared.errors), declared.findings
        )

    def test_symlinked_nested_directory_cannot_escape_generated_ownership(self) -> None:
        with self._repository() as root, tempfile.TemporaryDirectory() as outside_name:
            outside = Path(outside_name)
            (outside / "escaped.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "generated/linked").symlink_to(outside, target_is_directory=True)

            report = verify(root, "full")

        self._assert_inventory_error(report, "generated/linked")

    def test_unsupported_filesystem_entry_fails_closed(self) -> None:
        with self._repository() as root:
            pipe = root / "generated/evidence.pipe"
            os.mkfifo(pipe)

            report = verify(root, "full")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("unsupported filesystem type" in item.message for item in report.errors),
            report.findings,
        )

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(self.fixtures / "positive", root, dirs_exist_ok=True)
            yield root

    def _write_manifest(
        self, root: Path, artifacts: tuple[tuple[str, tuple[Path, ...]], ...]
    ) -> None:
        entries = tuple(
            (
                artifact_id,
                tuple((path.relative_to(root).as_posix(), self._digest(path)) for path in outputs),
            )
            for artifact_id, outputs in artifacts
        )
        self._write_manifest_entries(root, entries)

    def _write_manifest_entries(
        self,
        root: Path,
        artifacts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
    ) -> None:
        payload = {
            "_notice": _NOTICE,
            "schema": "ctower.generated-manifest/v1",
            "artifacts": [
                {
                    "id": artifact_id,
                    "generator": "fixture",
                    "tool_version": "1",
                    "command": "fixture generate",
                    "inputs": [],
                    "outputs": [{"path": path, "sha256": digest} for path, digest in outputs],
                }
                for artifact_id, outputs in artifacts
            ],
        }
        (root / "generated/.generated-manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def _digest(self, path: Path) -> str:
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

    def _zero(self) -> str:
        return f"sha256:{'0' * 64}"

    def _assert_inventory_error(self, report: PolicyReport, path: str) -> None:
        self.assertFalse(report.ok)
        self.assertTrue(any(path in finding.message for finding in report.errors), report.findings)


if __name__ == "__main__":
    unittest.main()
