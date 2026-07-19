"""Generated traceability behavior through its command and policy Interfaces."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any, cast

import tools.checks.traceability as traceability_command
from tools.checks import verify
from tools.checks.traceability import main as traceability_main

_GENERATED_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."


class TraceabilityDriftTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_command_module_exposes_only_main(self) -> None:
        public_names = {name for name in vars(traceability_command) if not name.startswith("_")}

        self.assertEqual(traceability_command.__all__, ["main"])
        self.assertEqual(public_names, {"main"})

    def test_mutated_index_fails_policy_and_check_does_not_repair_it(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            fixture = Path(name)
            self._copy_policy_fixture(fixture)
            generated = fixture / "generated/traceability-index.json"
            generated.write_text("{}\n", encoding="utf-8")
            before = self._snapshot(fixture)

            report = verify(fixture, "full")
            check_exit = traceability_main(["--root", str(fixture), "--check"])
            after = self._snapshot(fixture)

        self.assertFalse(report.ok)
        self.assertIn(
            "generated/traceability-index.json",
            {finding.path for finding in report.errors if finding.rule_id == "generated.drift"},
        )
        self.assertEqual(check_exit, 1)
        self.assertEqual(after, before)

    def test_check_regenerates_twice_outside_source_and_preserves_every_byte(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            fixture = Path(name)
            self._copy_policy_fixture(fixture)
            before = self._snapshot(fixture)

            first_exit = traceability_main(["--root", str(fixture), "--check"])
            second_exit = traceability_main(["--root", str(fixture), "--check"])
            after = self._snapshot(fixture)

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(after, before)

    def test_write_repairs_stale_pair_and_emits_required_notices(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            fixture = Path(name)
            self._copy_policy_fixture(fixture)
            (fixture / "generated/traceability-index.json").write_text("{}\n", encoding="utf-8")
            self._stale_traceability_entry(fixture)

            write_exit = traceability_main(["--root", str(fixture), "--write"])
            check_exit = traceability_main(["--root", str(fixture), "--check"])
            report = verify(fixture, "full")
            index = self._read_json(fixture / "generated/traceability-index.json")
            manifest = self._read_json(fixture / "generated/.generated-manifest.json")

        self.assertEqual(write_exit, 0)
        self.assertEqual(check_exit, 0)
        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(index["_notice"], _GENERATED_NOTICE)
        self.assertEqual(manifest["_notice"], _GENERATED_NOTICE)

    def test_write_rejects_symlinked_generated_root_without_external_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as name, tempfile.TemporaryDirectory() as outside_name:
            fixture = Path(name)
            outside = Path(outside_name)
            self._copy_policy_fixture(fixture)
            shutil.copytree(fixture / "generated", outside, dirs_exist_ok=True)
            shutil.rmtree(fixture / "generated")
            (fixture / "generated").symlink_to(outside, target_is_directory=True)
            before = self._snapshot(outside)
            errors = io.StringIO()

            with redirect_stderr(errors):
                exit_code = traceability_main(["--root", str(fixture), "--write"])

            after = self._snapshot(outside)

        self.assertEqual(exit_code, 1)
        self.assertIn("symlink", errors.getvalue())
        self.assertEqual(after, before)

    def test_write_rejects_symlinked_and_nonregular_index_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as name, tempfile.TemporaryDirectory() as outside_name:
            fixture = Path(name)
            outside = Path(outside_name) / "outside.json"
            self._copy_policy_fixture(fixture)
            index = fixture / "generated/traceability-index.json"
            index.unlink()
            outside.write_text("outside baseline\n", encoding="utf-8")
            index.symlink_to(outside)

            symlink_exit = traceability_main(["--root", str(fixture), "--write"])
            outside_after = outside.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as name:
            fixture = Path(name)
            self._copy_policy_fixture(fixture)
            index = fixture / "generated/traceability-index.json"
            index.unlink()
            index.mkdir()

            directory_exit = traceability_main(["--root", str(fixture), "--write"])

        self.assertEqual(symlink_exit, 1)
        self.assertEqual(outside_after, "outside baseline\n")
        self.assertEqual(directory_exit, 1)

    def test_invalid_authored_sources_fail_through_the_command(self) -> None:
        mutations = {
            "unknown reference": self._unknown_reference,
            "path duplicates": self._duplicate_mapping,
            "unowned normative artifact": self._remove_mapping,
        }
        for expected, mutate in mutations.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as name:
                fixture = Path(name)
                self._copy_policy_fixture(fixture)
                mutate(fixture)
                errors = io.StringIO()
                with redirect_stderr(errors):
                    exit_code = traceability_main(["--root", str(fixture), "--check"])

                self.assertEqual(exit_code, 1)
                self.assertIn(expected, errors.getvalue())

    def test_missing_generated_index_returns_command_failure(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            fixture = Path(name)
            self._copy_policy_fixture(fixture)
            (fixture / "generated/traceability-index.json").unlink()

            exit_code = traceability_main(["--root", str(fixture), "--check"])

        self.assertEqual(exit_code, 1)

    def _copy_policy_fixture(self, fixture: Path) -> None:
        manifest = self._read_json(self.root / "generated/.generated-manifest.json")
        entry = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["id"] == "contract-traceability-index"
        )
        paths = {
            "generated/.generated-manifest.json",
            "tools/checks/policy.toml",
            "tools/checks/exceptions.yaml",
            "tools/checks/_impl/generated.py",
            "tools/checks/_impl/generated_inventory.py",
            *(item["path"] for group in ("inputs", "outputs") for item in entry[group]),
        }
        source_map = self._read_json(self.root / "contracts/traceability/sources.json")
        paths.update(artifact["path"] for artifact in source_map["artifacts"])
        for relative in sorted(paths):
            if relative == "generated/.generated-manifest.json":
                continue
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / relative, target)
        fixture_manifest = {
            "_notice": manifest["_notice"],
            "schema": manifest["schema"],
            "artifacts": [entry],
        }
        (fixture / "generated/.generated-manifest.json").write_text(
            json.dumps(fixture_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _stale_traceability_entry(self, fixture: Path) -> None:
        path = fixture / "generated/.generated-manifest.json"
        manifest = self._read_json(path)
        entry = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["id"] == "contract-traceability-index"
        )
        for group in ("inputs", "outputs"):
            for digest_entry in entry[group]:
                digest_entry["sha256"] = f"sha256:{'0' * 64}"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _unknown_reference(self, fixture: Path) -> None:
        path, source_map = self._source_map(fixture)
        source_map["artifacts"][0]["references"] = ["AC-UNKNOWN-99"]
        path.write_text(json.dumps(source_map), encoding="utf-8")

    def _duplicate_mapping(self, fixture: Path) -> None:
        path, source_map = self._source_map(fixture)
        source_map["artifacts"].append(dict(source_map["artifacts"][0]))
        path.write_text(json.dumps(source_map), encoding="utf-8")

    def _remove_mapping(self, fixture: Path) -> None:
        path, source_map = self._source_map(fixture)
        source_map["artifacts"].pop()
        path.write_text(json.dumps(source_map), encoding="utf-8")

    def _source_map(self, fixture: Path) -> tuple[Path, dict[str, Any]]:
        path = fixture / "contracts/traceability/sources.json"
        return path, self._read_json(path)

    def _snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def _read_json(self, path: Path) -> dict[str, Any]:
        value: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            self.fail(f"expected JSON object at {path}")
        return cast(dict[str, Any], value)


if __name__ == "__main__":
    unittest.main()
