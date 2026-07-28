"""Executable invariants for the public SemVer and release foundation."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from repository._release_history import RawHistory, RawHistoryReader
else:
    from tests.repository._release_history import RawHistory, RawHistoryReader

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
_FIRST_RELEASE_TAG = "v0.1.0"
_FIRST_RELEASE_COMMIT = "171b49242e8abe0e3084552e6dac6939732bb738"
_GRAPH_CHAIN_REVISIONS = (
    ("head", "HEAD"),
    ("pre-rebase main", "1ef74d30bc0e5cd7241dc2c1a0dc80ea03748b1c"),
    ("checkout bump", "d9de5e08373e7b9ed1c5382a6cfdc637fdfca038"),
    ("protected feature", _PRE1_FEATURE_COMMIT),
)
_GRAPH_MODES = (
    ("default", ()),
    ("commit graph disabled", ("-c", "core.commitGraph=false")),
    ("replace objects disabled", ("--no-replace-objects",)),
    (
        "commit graph and replace objects disabled",
        ("--no-replace-objects", "-c", "core.commitGraph=false"),
    ),
)
_SENSITIVE_CONFIG_KEY = re.compile(
    r"(?:credential|extraheader|password|secret|token)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _GraphWalk:
    label: str
    feature_is_member: bool
    rev_list_returncode: int
    merge_base_returncode: int


@dataclass(frozen=True)
class _GraphProbe:
    candidate: str
    is_shallow: bool
    raw_history: RawHistory
    walks: tuple[_GraphWalk, ...]
    capture_problems: tuple[str, ...]
    telemetry: str


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
        history = self._assert_pre1_feature_history()
        candidate = history.candidate
        config = self._read_json("release-please-config.json")
        manifest = self._read_json(".release-please-manifest.json")
        workflow = (self.root / ".github/workflows/release-please.yml").read_text(encoding="utf-8")
        root_package = self._as_object(
            self._as_object(config["packages"], "Release Please packages")["."],
            "Release Please root package",
        )
        manifest_version = self._as_string(manifest["."], "release manifest")
        release_tags = self._release_tags(history)

        self.assertIn(f"uses: {_RELEASE_PLEASE_ACTION}", workflow)
        self.assertEqual(
            [tag for tag in release_tags if not self._is_pre1_version(tag.removeprefix("v"))],
            [],
            f"[POLICY] candidate={candidate}: merged release tags must remain below 1.0.0",
        )
        self.assertEqual(
            "0.1.0",
            root_package.get("initial-version", config.get("initial-version")),
            f"[POLICY] candidate={candidate}: first release must begin at 0.1.0",
        )
        if manifest_version != "0.0.0":
            self.assertTrue(
                self._is_pre1_version(manifest_version),
                f"[POLICY] candidate={candidate}: release proposal {manifest_version!r} "
                "must remain below 1.0.0",
            )
        self.assertEqual(
            [],
            self._release_as_policy_violations(config, root_package, history),
            f"[POLICY] candidate={candidate}: unreleased history can override "
            "Release Please's pre-1.0 initial version",
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
        verify = (self.root / ".github/workflows/verify.yml").read_text(encoding="utf-8")

        self.assertNotIn("workflow_dispatch", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.repository == 'simjak/ctower'", workflow)
        self.assertEqual(self._workflow_values(verify, "fetch-depth"), ["0"])
        self.assertEqual(self._workflow_values(verify, "fetch-tags"), ["true"])

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

    def _release_tags(self, history: RawHistory) -> list[str]:
        result = RawHistoryReader(
            self.root,
            _PRE1_FEATURE_COMMIT,
        ).merged_release_tags(history)
        if result.problems:
            self.fail(
                f"[GRAPH-INFRASTRUCTURE] candidate={history.candidate}: "
                f"{'; '.join(result.problems)}"
            )
        history_ids = {commit.object_id for commit in history.commits}
        if _FIRST_RELEASE_COMMIT in history_ids:
            targets = dict(result.targets)
            if targets.get(_FIRST_RELEASE_TAG) != _FIRST_RELEASE_COMMIT:
                self.fail(
                    f"[GRAPH-INFRASTRUCTURE] candidate={history.candidate}: "
                    f"expected {_FIRST_RELEASE_TAG} -> {_FIRST_RELEASE_COMMIT} is not visible"
                )
        return list(result.names)

    def _assert_pre1_feature_history(self) -> RawHistory:
        probe = self._capture_graph_probe()
        sys.stdout.write(f"{probe.telemetry}\n")
        sys.stdout.flush()
        graph_problems = self._graph_infrastructure_problems(probe)
        if graph_problems:
            self.fail(
                f"[GRAPH-INFRASTRUCTURE] candidate={probe.candidate}: "
                f"{'; '.join(graph_problems)}\n{probe.telemetry}"
            )
        # Shallow overlays can alter revision walkers without altering stored parents.
        # The no-replace raw walk is authoritative; the other modes remain telemetry.
        self.assertTrue(
            probe.raw_history.feature_is_member,
            f"[POLICY] candidate={probe.candidate}: {_PRE1_FEATURE_COMMIT} "
            "must exist in pre-1.0 history",
        )
        return probe.raw_history

    def _capture_graph_probe(self) -> _GraphProbe:
        problems: list[str] = []
        sections = [self._render_git("git build", ("version", "--build-options"))]
        sections.append(
            self._render_git(
                "repository paths",
                ("rev-parse", "--show-toplevel", "--git-dir"),
            )
        )
        candidate_arguments = (
            "--no-replace-objects",
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        )
        candidate_result = self._git(*candidate_arguments)
        candidate = candidate_result.stdout.strip() or "<unresolved>"
        if candidate_result.returncode != 0:
            problems.append("candidate digest could not be resolved")
        sections.append(
            self._render_result(
                "resolved candidate",
                candidate_arguments,
                candidate_result,
            )
        )
        is_shallow, shallow_sections, _ = self._shallow_telemetry()
        sections.extend(shallow_sections)
        sections.extend(self._configuration_telemetry())
        sections.extend(self._cat_file_telemetry(candidate))
        raw_history = RawHistoryReader(
            self.root,
            _PRE1_FEATURE_COMMIT,
        ).walk(candidate)
        sections.append(raw_history.telemetry)
        walks, walk_sections = self._graph_walk_telemetry(candidate)
        sections.extend(walk_sections)
        return _GraphProbe(
            candidate=candidate,
            is_shallow=is_shallow,
            raw_history=raw_history,
            walks=walks,
            capture_problems=tuple(problems),
            telemetry="\n".join(sections),
        )

    def _shallow_telemetry(self) -> tuple[bool, list[str], list[str]]:
        problems: list[str] = []
        shallow_result = self._git("rev-parse", "--is-shallow-repository")
        shallow_value = shallow_result.stdout.strip()
        if shallow_result.returncode != 0 or shallow_value not in {"true", "false"}:
            problems.append("shallow state could not be determined")
        path_result = self._git("rev-parse", "--git-path", "shallow")
        shallow_ids = "<absent>"
        if path_result.returncode == 0:
            shallow_path = Path(path_result.stdout.strip())
            try:
                if shallow_path.is_file():
                    shallow_ids = shallow_path.read_text(encoding="utf-8").strip() or "<empty>"
            except OSError as error:
                problems.append(f"shallow boundary could not be read: {error}")
        else:
            problems.append("shallow boundary path could not be resolved")
        sections = [
            self._render_result(
                "shallow state",
                ("rev-parse", "--is-shallow-repository"),
                shallow_result,
            ),
            self._render_result(
                "shallow path",
                ("rev-parse", "--git-path", "shallow"),
                path_result,
            ),
            f"## .git/shallow commit IDs\n{shallow_ids}",
        ]
        return shallow_value == "true", sections, problems

    def _configuration_telemetry(self) -> list[str]:
        config_result = self._git("config", "--show-origin", "--show-scope", "--list")
        config = "\n".join(
            self._redact_config_line(line) for line in config_result.stdout.splitlines()
        )
        git_environment = "\n".join(
            f"{name}=<redacted>" for name in sorted(os.environ) if name.startswith("GIT_")
        )
        return [
            self._render_result(
                "effective config with origins",
                ("config", "--show-origin", "--show-scope", "--list"),
                config_result,
                stdout=config,
            ),
            f"## inherited GIT_* names\n{git_environment or '<none>'}",
        ]

    def _cat_file_telemetry(self, candidate: str) -> list[str]:
        sections: list[str] = []
        for mode, prefix in (
            ("default", ()),
            ("replace objects disabled", ("--no-replace-objects",)),
        ):
            for label, revision in _GRAPH_CHAIN_REVISIONS:
                resolved_revision = candidate if revision == "HEAD" else revision
                arguments = (*prefix, "cat-file", "-p", resolved_revision)
                result = self._git(*arguments)
                sections.append(
                    self._render_result(
                        f"raw commit record: {mode}: {label}",
                        arguments,
                        result,
                        stdout="\n".join(
                            line
                            for line in result.stdout.splitlines()
                            if line.startswith(("tree ", "parent "))
                        ),
                    )
                )
        return sections

    def _graph_walk_telemetry(
        self,
        candidate: str,
    ) -> tuple[tuple[_GraphWalk, ...], list[str]]:
        walks: list[_GraphWalk] = []
        sections: list[str] = []
        for label, prefix in _GRAPH_MODES:
            rev_list_arguments = (*prefix, "rev-list", "--parents", candidate)
            rev_list_result = self._git(*rev_list_arguments)
            rev_list_rows = rev_list_result.stdout.splitlines()
            commits = [row.partition(" ")[0] for row in rev_list_rows]
            is_member = _PRE1_FEATURE_COMMIT in commits
            relevant_rows = (
                rev_list_rows[: commits.index(_PRE1_FEATURE_COMMIT) + 1]
                if is_member
                else rev_list_rows
            )
            merge_arguments = (
                *prefix,
                "merge-base",
                "--is-ancestor",
                _PRE1_FEATURE_COMMIT,
                candidate,
            )
            merge_result = self._git(*merge_arguments)
            walk = _GraphWalk(
                label,
                is_member,
                rev_list_result.returncode,
                merge_result.returncode,
            )
            walks.append(walk)
            sections.extend(
                self._graph_walk_sections(
                    walk,
                    rev_list_arguments,
                    rev_list_result,
                    relevant_rows,
                    merge_arguments,
                    merge_result,
                )
            )
        return tuple(walks), sections

    def _graph_walk_sections(
        self,
        walk: _GraphWalk,
        rev_list_arguments: tuple[str, ...],
        rev_list_result: subprocess.CompletedProcess[str],
        relevant_rows: list[str],
        merge_arguments: tuple[str, ...],
        merge_result: subprocess.CompletedProcess[str],
    ) -> list[str]:
        return [
            (
                self._render_result(
                    f"rev-list parents: {walk.label}",
                    rev_list_arguments,
                    rev_list_result,
                    stdout="\n".join(relevant_rows),
                )
                + f"\nfeature-membership={str(walk.feature_is_member).lower()}"
            ),
            self._render_result(
                f"merge-base ancestry: {walk.label}",
                merge_arguments,
                merge_result,
            ),
        ]

    def _graph_infrastructure_problems(self, probe: _GraphProbe) -> list[str]:
        return [*probe.capture_problems, *probe.raw_history.problems]

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "CTOWER_RELEASE_GATE_GIT_ARGUMENTS": json.dumps(arguments),
        }
        return subprocess.run(
            (
                sys.executable,
                "-c",
                "import json, os; os.execv('/usr/bin/git', "
                "['/usr/bin/git', *json.loads("
                "os.environ['CTOWER_RELEASE_GATE_GIT_ARGUMENTS'])])",
            ),
            cwd=self.root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def _render_git(self, label: str, arguments: tuple[str, ...]) -> str:
        return self._render_result(label, arguments, self._git(*arguments))

    def _render_result(
        self,
        label: str,
        arguments: tuple[str, ...],
        result: subprocess.CompletedProcess[str],
        *,
        stdout: str | None = None,
    ) -> str:
        rendered_stdout = result.stdout.strip() if stdout is None else stdout.strip()
        rendered_stderr = result.stderr.strip()
        return "\n".join(
            (
                f"## {label}",
                f"$ {shlex.join(('/usr/bin/git', *arguments))}",
                f"returncode={result.returncode}",
                "stdout:",
                rendered_stdout or "<empty>",
                "stderr:",
                rendered_stderr or "<empty>",
            )
        )

    def _redact_config_line(self, line: str) -> str:
        prefix, separator, setting = line.rpartition("\t")
        key, equals, value = setting.partition("=")
        if not separator or not equals:
            return line
        if _SENSITIVE_CONFIG_KEY.search(key):
            value = "<redacted>"
        else:
            value = re.sub(r"(://)[^/@\s]+@", r"\1<redacted>@", value)
        return f"{prefix}\t{key}={value}"

    def _release_as_policy_violations(
        self,
        config: dict[str, object],
        root_package: dict[str, object],
        history: RawHistory,
    ) -> list[str]:
        violations = [
            f"{source}: {value!r}"
            for source, value in (
                ("config release-as", config.get("release-as")),
                ("root package release-as", root_package.get("release-as")),
            )
            if value is not None and not self._is_pre1_version(value)
        ]
        for commit in history.commits:
            for line in commit.message.splitlines():
                match = _RELEASE_AS_DIRECTIVE.match(line.lstrip(" \t"))
                if match is not None and not self._is_pre1_version(match.group(1)):
                    violations.append(f"commit {commit.object_id}: {line.strip()}")
        return violations

    def _is_pre1_version(self, value: object) -> bool:
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
