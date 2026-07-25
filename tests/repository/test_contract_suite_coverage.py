"""Every authored contract test directory must be gated by the suite manifest."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
_CONTRACTS = ROOT / "tests/contracts"
_MANIFEST = ROOT / "tools/checks/expected-suites.toml"


class ContractSuiteCoverageTests(unittest.TestCase):
    def test_every_contract_test_directory_is_required_by_the_manifest(self) -> None:
        """A future contract suite cannot silently escape the canonical gate.

        ``tools/checks/expected-suites.toml`` is the only verification-scope
        manifest (CODING_STANDARDS "Tests and review"). Every directory under
        ``tests/contracts`` that holds a ``test_*.py`` module must be referenced
        by at least one manifest suite ``path``, otherwise the suite is an
        invisible orphan that no gate ever executes.
        """

        manifest = tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))
        gated_paths = {suite["path"] for suite in manifest["suite"]}

        discovered: dict[str, list[str]] = {}
        for directory in sorted(path for path in _CONTRACTS.iterdir() if path.is_dir()):
            tests = sorted(
                test.name
                for test in directory.glob("test_*.py")
                if test.is_file() and "__pycache__" not in test.parts
            )
            if tests:
                discovered[directory.relative_to(ROOT).as_posix()] = tests

        self.assertTrue(discovered, "no contract test directories were discovered")
        ungated = sorted(path for path in discovered if path not in gated_paths)
        self.assertFalse(
            ungated,
            f"contract test directories are absent from the suite manifest: {ungated}",
        )

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
