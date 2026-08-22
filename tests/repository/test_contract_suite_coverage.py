"""Every authored test directory must be gated by the suite manifest."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
_TESTS = ROOT / "tests"
_MANIFEST = ROOT / "tools/checks/expected-suites.toml"


class TestSuiteCoverageTests(unittest.TestCase):
    def test_every_test_directory_is_referenced_by_the_manifest(self) -> None:
        """A future test directory cannot silently escape the canonical gate.

        ``tools/checks/expected-suites.toml`` is the only verification-scope
        manifest (CODING_STANDARDS "Tests and review"). Every directory under
        ``tests/`` that directly holds a ``test_*.py`` module must be referenced
        by at least one manifest suite ``path``, otherwise it is an invisible
        orphan that no gate ever executes. Discovery comes from the filesystem;
        the manifest is never used to discover test directories.
        """

        manifest = tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))
        manifest_paths = tuple(ROOT / suite["path"] for suite in manifest["suite"])

        discovered: dict[str, list[str]] = {}
        for test in sorted(_TESTS.rglob("test_*.py")):
            if not test.is_file() or test.parent == _TESTS or "__pycache__" in test.parts:
                continue
            directory = test.parent.relative_to(ROOT).as_posix()
            discovered.setdefault(directory, []).append(test.name)

        self.assertTrue(discovered, "no test directories were discovered")
        ungated = sorted(
            path
            for path in discovered
            if not any(
                self._is_within(ROOT / path, suite_path)
                for suite_path in manifest_paths
            )
        )
        self.assertFalse(
            ungated,
            f"test directories are absent from the suite manifest: {ungated}",
        )

    def _is_within(self, directory: Path, suite_path: Path) -> bool:
        try:
            directory.relative_to(suite_path)
        except ValueError:
            return False
        return True

    def test_manifest_renames_do_not_orphan_contract_directories(self) -> None:
        """A gated contract path must still point at a real test directory."""

        manifest = tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))
        contract_paths = {
            suite["path"]
            for suite in manifest["suite"]
            if suite["path"].startswith("tests/contracts/")
        }
        self.assertTrue(contract_paths, "no contract suites are declared")
        missing = sorted(
            path
            for path in contract_paths
            if not (ROOT / path).is_dir() or not any((ROOT / path).glob("test_*.py"))
        )
        self.assertFalse(missing, f"manifest contract paths point nowhere: {missing}")


if __name__ == "__main__":
    unittest.main()
