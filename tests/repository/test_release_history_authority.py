"""Adversarial checks for the release gate's single raw-history authority."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ReleaseHistoryAuthorityTests(unittest.TestCase):
    root = Path(__file__).parents[2]
    gate_source = root / "tests/repository/test_release_foundation.py"
    authority_source = root / "tests/repository/_release_history.py"

    def test_shallow_overlay_cannot_hide_release_as_policy_violation(self) -> None:
        with self._repository() as repository:
            self._commit(repository, "feat: forbidden\n\nRelease-As: 1.0.0")
            boundary = self._commit(repository, "chore: overlay boundary")
            self._commit(repository, "chore: benign candidate")
            self._write_shallow_boundary(repository, boundary)

            result = self._run_gate(repository)

        self._assert_gate_failure(result, "[POLICY]", "Release-As: 1.0.0")

    def test_shallow_overlay_cannot_hide_merged_release_tag(self) -> None:
        with self._repository() as repository:
            tagged = self._commit(repository, "chore: hidden release tag target")
            self._git(repository, "tag", "v0.0.9", tagged)
            boundary = self._commit(repository, "chore: overlay boundary")
            self._commit(repository, "chore: benign candidate")
            self._write_shallow_boundary(repository, boundary)

            result = self._run_gate(repository)

        self._assert_gate_failure(result, "[POLICY]", "v0.0.9")

    def test_replacement_ref_cannot_mask_release_as_policy_violation(self) -> None:
        with self._repository() as repository:
            violation = self._commit(
                repository,
                "feat: replaced violation\n\nRelease-As: 1.0.0",
            )
            tree = self._git(repository, "show", "-s", "--format=%T", violation).stdout.strip()
            parent = self._git(repository, "show", "-s", "--format=%P", violation).stdout.strip()
            replacement = self._git(
                repository,
                "commit-tree",
                tree,
                "-p",
                parent,
                input_text="chore: clean replacement\n",
            ).stdout.strip()
            self._git(repository, "replace", violation, replacement)
            self._commit(repository, "chore: benign candidate")

            result = self._run_gate(repository)

        self._assert_gate_failure(result, "[POLICY]", "Release-As: 1.0.0")

    def test_non_commit_parent_is_graph_infrastructure_failure(self) -> None:
        with self._repository() as repository:
            base = self._git(repository, "rev-parse", "HEAD").stdout.strip()
            tree = self._git(repository, "show", "-s", "--format=%T", base).stdout.strip()
            shaped_blob = self._git(
                repository,
                "hash-object",
                "-w",
                "--stdin",
                input_text=f"tree {tree}\n\nnot a commit\n",
            ).stdout.strip()
            corrupt = self._git(
                repository,
                "hash-object",
                "-t",
                "commit",
                "-w",
                "--stdin",
                input_text=(
                    f"tree {tree}\n"
                    f"parent {base}\n"
                    f"parent {shaped_blob}\n"
                    "author Gate Test <gate@example.com> 1700000000 +0000\n"
                    "committer Gate Test <gate@example.com> 1700000000 +0000\n"
                    "\nchore: ambiguous graph\n"
                ),
            ).stdout.strip()
            self._git(repository, "update-ref", "HEAD", corrupt)
            self._write_shallow_boundary(repository, corrupt)

            result = self._run_gate(repository)

        self._assert_gate_failure(result, "[GRAPH-INFRASTRUCTURE]", "non-commit")

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="ctower-release-history-") as temporary:
            repository = Path(temporary) / "repository"
            self._git_process(
                Path(temporary),
                "clone",
                "--quiet",
                "--no-local",
                str(self.root),
                str(repository),
            )
            shutil.copy2(
                self.gate_source,
                repository / "tests/repository/test_release_foundation.py",
            )
            shutil.copy2(
                self.authority_source,
                repository / "tests/repository/_release_history.py",
            )
            yield repository

    def _commit(self, repository: Path, message: str) -> str:
        self._git(repository, "commit", "--allow-empty", "-m", message)
        return self._git(repository, "rev-parse", "HEAD").stdout.strip()

    def _write_shallow_boundary(self, repository: Path, commit: str) -> None:
        shallow = self._git(repository, "rev-parse", "--git-path", "shallow").stdout.strip()
        (repository / shallow).write_text(f"{commit}\n", encoding="utf-8")

    def _run_gate(self, repository: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (
                sys.executable,
                "-m",
                "unittest",
                "tests.repository.test_release_foundation.ReleaseFoundationTests."
                "test_first_release_proposal_preserves_pre_1_0_policy",
            ),
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )

    def _git(
        self,
        repository: Path,
        *arguments: str,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._git_process(repository, *arguments, input_text=input_text)

    def _git_process(
        self,
        repository: Path,
        *arguments: str,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "CTOWER_RELEASE_AUTHORITY_GIT_ARGUMENTS": json.dumps(arguments),
        }
        return subprocess.run(
            (
                sys.executable,
                "-c",
                "import json, os; os.execv('/usr/bin/git', "
                "['/usr/bin/git', '-c', 'user.name=Gate Test', "
                "'-c', 'user.email=gate@example.com', "
                "*json.loads(os.environ['CTOWER_RELEASE_AUTHORITY_GIT_ARGUMENTS'])])",
            ),
            cwd=repository,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            input=input_text,
        )

    def _assert_gate_failure(
        self,
        result: subprocess.CompletedProcess[str],
        classification: str,
        evidence: str,
    ) -> None:
        transcript = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, transcript)
        self.assertIn(classification, transcript)
        self.assertIn(evidence, transcript)


if __name__ == "__main__":
    unittest.main()
