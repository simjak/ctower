"""Raw Git graph telemetry capture for the release gate's pre-1.0 policy check."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ._release_history import RawHistory, RawHistoryReader

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
class GraphWalk:
    label: str
    feature_is_member: bool
    rev_list_returncode: int
    merge_base_returncode: int


@dataclass(frozen=True)
class GraphProbe:
    candidate: str
    is_shallow: bool
    raw_history: RawHistory
    walks: tuple[GraphWalk, ...]
    capture_problems: tuple[str, ...]
    telemetry: str


class GraphTelemetryProbe:
    """Capture raw git-graph telemetry proving pre-1.0 feature membership."""

    def __init__(self, root: Path, protected_feature: str) -> None:
        self._root = root
        self._protected_feature = protected_feature

    def capture(self) -> GraphProbe:
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
            self._root,
            self._protected_feature,
        ).walk(candidate)
        sections.append(raw_history.telemetry)
        walks, walk_sections = self._graph_walk_telemetry(candidate)
        sections.extend(walk_sections)
        return GraphProbe(
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
        chain_revisions = (
            ("head", "HEAD"),
            ("pre-rebase main", "1ef74d30bc0e5cd7241dc2c1a0dc80ea03748b1c"),
            ("checkout bump", "d9de5e08373e7b9ed1c5382a6cfdc637fdfca038"),
            ("protected feature", self._protected_feature),
        )
        sections: list[str] = []
        for mode, prefix in (
            ("default", ()),
            ("replace objects disabled", ("--no-replace-objects",)),
        ):
            for label, revision in chain_revisions:
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
    ) -> tuple[tuple[GraphWalk, ...], list[str]]:
        walks: list[GraphWalk] = []
        sections: list[str] = []
        for label, prefix in _GRAPH_MODES:
            rev_list_arguments = (*prefix, "rev-list", "--parents", candidate)
            rev_list_result = self._git(*rev_list_arguments)
            rev_list_rows = rev_list_result.stdout.splitlines()
            commits = [row.partition(" ")[0] for row in rev_list_rows]
            is_member = self._protected_feature in commits
            relevant_rows = (
                rev_list_rows[: commits.index(self._protected_feature) + 1]
                if is_member
                else rev_list_rows
            )
            merge_arguments = (
                *prefix,
                "merge-base",
                "--is-ancestor",
                self._protected_feature,
                candidate,
            )
            merge_result = self._git(*merge_arguments)
            walk = GraphWalk(
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
        walk: GraphWalk,
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
            cwd=self._root,
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
