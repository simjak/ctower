"""Executable invariants for the public SemVer and release foundation."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from typing import cast

_PINNED_ACTION = re.compile(r"[^@\s]+@[0-9a-f]{40}")
_IDENTIFIER = re.compile(r"[0-9A-Za-z-]+")
# Release Please 17.6.0 recognizes case-insensitive Release-As footer types with
# ":" or "#" separators. The history check below is intentionally a superset.
_RELEASE_AS_DIRECTIVE = re.compile(
    r"^release-as[ \t]*(?::|#)[ \t]*(.*)$",
    re.IGNORECASE,
)
_RELEASE_PLEASE_ACTION = "googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7"
_SEMVER_CORE_COMPONENTS = 3
_PRE1_FEATURE_COMMIT = "79e292e437457f92bb6a39bfbfdb2a3a62146529"


def _is_valid_semver(value: str) -> bool:
    """Return whether *value* follows the SemVer 2.0.0 grammar."""
    core_and_prerelease, build_separator, build = value.partition("+")
    if not _is_valid_build(build_separator, build):
        return False

    core, prerelease_separator, prerelease = core_and_prerelease.partition("-")
    return _is_valid_core(core) and _is_valid_prerelease(prerelease_separator, prerelease)


def _is_valid_build(separator: str, build: str) -> bool:
    if not separator:
        return True
    return bool(build) and all(_IDENTIFIER.fullmatch(item) for item in build.split("."))


def _is_valid_prerelease(separator: str, prerelease: str) -> bool:
    if not separator:
        return True
    return bool(prerelease) and all(
        _is_valid_prerelease_identifier(item) for item in prerelease.split(".")
    )


def _is_valid_prerelease_identifier(identifier: str) -> bool:
    valid_shape = _IDENTIFIER.fullmatch(identifier) is not None
    has_leading_zero = identifier.isdecimal() and len(identifier) > 1 and identifier.startswith("0")
    return valid_shape and not has_leading_zero


def _is_valid_core(core: str) -> bool:
    components = core.split(".")
    return len(components) == _SEMVER_CORE_COMPONENTS and all(
        component.isascii()
        and component.isdecimal()
        and (component == "0" or not component.startswith("0"))
        for component in components
    )


class ReleaseFoundationTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_version_authority_and_mirrors_are_valid_and_equal(self) -> None:
        manifest = self._read_json(".release-please-manifest.json")
        package = self._read_json("package.json")
        with (self.root / "pyproject.toml").open("rb") as stream:
            pyproject = tomllib.load(stream)
        pyproject_project = self._as_object(pyproject["project"], "pyproject.toml project")

        versions = {
            "VERSION": (self.root / "VERSION").read_text(encoding="utf-8").strip(),
            "release manifest": self._as_string(manifest["."], "release manifest"),
            "package.json": self._as_string(package["version"], "package.json version"),
            "pyproject.toml": self._as_string(
                pyproject_project["version"], "pyproject.toml version"
            ),
        }

        for source, version in versions.items():
            with self.subTest(source=source):
                self.assertTrue(
                    _is_valid_semver(version), f"{source} is not valid SemVer: {version}"
                )
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_semver_validator_rejects_noncanonical_and_malformed_versions(self) -> None:
        for version in ("0.0.0", "1.2.3-alpha.1+build.7", "10.20.30-rc-1"):
            with self.subTest(version=version, expected="valid"):
                self.assertTrue(_is_valid_semver(version))
        for version in (
            "1.2",
            "01.2.3",
            "1.02.3",
            "1.2.03",
            "1.2.3-01",
            "1.2.3-",
            "1.2.3+",
            "1.2.3+build..7",
            "\N{ARABIC-INDIC DIGIT ONE}.2.3",
            "v1.2.3",
        ):
            with self.subTest(version=version, expected="invalid"):
                self.assertFalse(_is_valid_semver(version))

    def test_release_please_preserves_the_root_simple_release_contract(self) -> None:
        config = self._read_json("release-please-config.json")

        self.assertEqual(config["release-type"], "simple")
        self.assertTrue(config["include-v-in-tag"] is True)
        self.assertTrue(config["include-component-in-tag"] is False)
        packages = self._as_object(config["packages"], "Release Please packages")
        self.assertEqual(set(packages), {"."})

        root_package = self._as_object(packages["."], "Release Please root package")
        self.assertEqual(root_package["version-file"], "VERSION")
        self.assertEqual(
            root_package["extra-files"],
            [
                {
                    "type": "json",
                    "path": "package.json",
                    "jsonpath": "$.version",
                },
                {
                    "type": "toml",
                    "path": "pyproject.toml",
                    "jsonpath": "$.project.version",
                },
            ],
        )

    def test_first_release_proposal_preserves_pre_1_0_policy(self) -> None:
        config = self._read_json("release-please-config.json")
        manifest = self._read_json(".release-please-manifest.json")
        workflow = (self.root / ".github/workflows/release-please.yml").read_text(encoding="utf-8")
        root_package = self._as_object(
            self._as_object(config["packages"], "Release Please packages")["."],
            "Release Please root package",
        )

        self.assertIn(f"uses: {_RELEASE_PLEASE_ACTION}", workflow)
        self.assertEqual(manifest["."], "0.0.0")
        self.assertEqual(
            self._pre1_release_tags(),
            [],
        )
        self._assert_pre1_feature_history()
        self.assertEqual(
            "0.1.0",
            root_package.get("initial-version", config.get("initial-version")),
        )
        self.assertEqual(
            [],
            self._release_as_policy_violations(config, root_package),
            "unreleased history can override Release Please's pre-1.0 initial version",
        )

    def test_workflow_actions_are_sha_pinned_and_unsafe_trigger_is_absent(self) -> None:
        workflow_directory = self.root / ".github/workflows"
        workflows = sorted(
            path
            for path in workflow_directory.iterdir()
            if path.is_file() and path.suffix in {".yaml", ".yml"}
        )
        self.assertTrue(workflows, "at least one checked-in workflow is required")

        for workflow in workflows:
            text = workflow.read_text(encoding="utf-8")
            with self.subTest(workflow=workflow.name, assertion="trigger"):
                self.assertNotIn("pull_request_target", text)
            for line_number, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if not stripped.startswith(("uses:", "- uses:")):
                    continue
                reference = stripped.split("uses:", maxsplit=1)[1].strip().split()[0]
                with self.subTest(
                    workflow=workflow.name,
                    line=line_number,
                    reference=reference,
                ):
                    self.assertIsNotNone(_PINNED_ACTION.fullmatch(reference))

    def test_action_pin_validator_rejects_moving_and_malformed_references(self) -> None:
        valid = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
        self.assertIsNotNone(_PINNED_ACTION.fullmatch(valid))
        for reference in (
            "actions/checkout@v4",
            f"{valid}-suffix",
            valid.replace("@", "@prefix", 1),
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af68",
            "actions/checkout@11BD71901BBE5B1630CEA73D27597364C9AF683",
        ):
            with self.subTest(reference=reference):
                self.assertIsNone(_PINNED_ACTION.fullmatch(reference))

    def test_release_workflow_preserves_private_token_fallback(self) -> None:
        workflow = (self.root / ".github/workflows/release-please.yml").read_text(encoding="utf-8")

        self.assertEqual(
            self._workflow_values(workflow, "token"),
            ["${{ secrets.RELEASE_PLEASE_TOKEN || github.token }}"],
        )
        self.assertEqual(
            self._workflow_values(workflow, "config-file"),
            ["release-please-config.json"],
        )
        self.assertEqual(
            self._workflow_values(workflow, "manifest-file"),
            [".release-please-manifest.json"],
        )

    def test_release_workflow_is_write_capable_only_for_trusted_main_pushes(self) -> None:
        workflow = (self.root / ".github/workflows/release-please.yml").read_text(encoding="utf-8")

        self.assertNotIn("workflow_dispatch", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.repository == 'simjak/ctower'", workflow)

    def _read_json(self, path: str) -> dict[str, object]:
        payload = json.loads((self.root / path).read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)
        return cast(dict[str, object], payload)

    def _as_object(self, value: object, source: str) -> dict[str, object]:
        self.assertIsInstance(value, dict, f"{source} must be an object")
        return cast(dict[str, object], value)

    def _as_string(self, value: object, source: str) -> str:
        self.assertIsInstance(value, str, f"{source} must be a string")
        return cast(str, value)

    def _pre1_release_tags(self) -> list[str]:
        result = subprocess.run(
            (
                "/usr/bin/git",
                "tag",
                "--merged",
                "HEAD",
                "--list",
                "v[0-9]*",
            ),
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.splitlines()

    def _assert_pre1_feature_history(self) -> None:
        environment = {
            **os.environ,
            "PRE1_FEATURE_COMMIT": _PRE1_FEATURE_COMMIT,
        }
        result = subprocess.run(
            (
                sys.executable,
                "-c",
                "import os; os.execv('/usr/bin/git', "
                "['/usr/bin/git', 'merge-base', '--is-ancestor', "
                "os.environ['PRE1_FEATURE_COMMIT'], 'HEAD'])",
            ),
            cwd=self.root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"{_PRE1_FEATURE_COMMIT} must exist in pre-1.0 history: {result.stderr.strip()}",
        )

    def _release_as_policy_violations(
        self,
        config: dict[str, object],
        root_package: dict[str, object],
    ) -> list[str]:
        violations = [
            f"{source}: {value!r}"
            for source, value in (
                ("config release-as", config.get("release-as")),
                ("root package release-as", root_package.get("release-as")),
            )
            if value is not None and not self._is_pre1_release_as(value)
        ]
        for commit, message in self._commit_messages():
            for line in message.splitlines():
                match = _RELEASE_AS_DIRECTIVE.match(line.lstrip(" \t"))
                if match is not None and not self._is_pre1_release_as(match.group(1)):
                    violations.append(f"commit {commit}: {line.strip()}")
        return violations

    def _commit_messages(self) -> list[tuple[str, str]]:
        result = subprocess.run(
            (
                "/usr/bin/git",
                "log",
                "-z",
                "--format=%H%x00%B",
                "HEAD",
            ),
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        fields = result.stdout.rstrip("\0").split("\0")
        self.assertEqual(len(fields) % 2, 0, "git log returned incomplete commit records")
        return list(zip(fields[::2], fields[1::2], strict=True))

    def _is_pre1_release_as(self, value: object) -> bool:
        return isinstance(value, str) and _is_valid_semver(value) and value.startswith("0.")

    def _workflow_values(self, workflow: str, key: str) -> list[str]:
        prefix = f"{key}:"
        return [
            line.strip().removeprefix(prefix).strip()
            for line in workflow.splitlines()
            if line.strip().startswith(prefix)
        ]


if __name__ == "__main__":
    unittest.main()
