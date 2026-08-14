"""Execution proofs for exact secret-scan exceptions and both release scan modes."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


async def _execute(
    cwd: Path, argv: tuple[str, ...], env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode is None:
        raise RuntimeError("completed subprocess has no return code")
    return (
        process.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


class SecretScanPolicyTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_only_exact_fake_fixture_is_allowed_in_both_scan_modes(self) -> None:
        with self._repository() as repository:
            intended = self._scan(repository, "secrets-intended-tree")
            history = self._scan(repository, "secrets-history")

        self.assertEqual(intended[0], 0, intended)
        self.assertEqual(history[0], 0, history)

    def test_same_detector_shaped_value_elsewhere_fails_both_scan_modes(self) -> None:
        with self._repository() as repository:
            token = self._fixture_token(repository)
            other = repository / "tests/repository/fixtures/secret-scan/other.txt"
            other.write_text(f"fixture-token = {token}\n", encoding="utf-8")
            intended = self._scan(repository, "secrets-intended-tree")
            self._commit(repository, "add disallowed fixture")
            history = self._scan(repository, "secrets-history")

        self.assertNotEqual(intended[0], 0, intended)
        self.assertNotEqual(history[0], 0, history)

    def test_neighboring_decision_text_does_not_expand_the_exact_allowlist(self) -> None:
        with self._repository() as repository:
            token = self._fixture_token(repository)
            decision = repository / "docs/internal/DECISIONS.md"
            decision.write_text(
                decision.read_text(encoding="utf-8") + f"fixture-token = {token}\n",
                encoding="utf-8",
            )
            intended = self._scan(repository, "secrets-intended-tree")
            self._commit(repository, "add disallowed decision value")
            history = self._scan(repository, "secrets-history")

        self.assertNotEqual(intended[0], 0, intended)
        self.assertNotEqual(history[0], 0, history)

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            repository = Path(name)
            fixture = repository / "tests/repository/fixtures/secret-scan/exact-fake.txt"
            fixture.parent.mkdir(parents=True)
            shutil.copyfile(
                self.root / "tests/repository/fixtures/secret-scan/exact-fake.txt", fixture
            )
            shutil.copyfile(self.root / ".gitleaks.toml", repository / ".gitleaks.toml")
            decision = repository / "docs/internal/DECISIONS.md"
            decision.parent.mkdir(parents=True)
            decision.write_text(
                "The reusable-image lifecycle is setup -> capture -> scrub -> secret scan -> "
                "SBOM/vulnerability scan ->\n",
                encoding="utf-8",
            )
            self._git(repository, "init", "--quiet")
            self._git(repository, "config", "user.name", "ctower test")
            self._git(repository, "config", "user.email", "ctower-test@example.invalid")
            self._commit(repository, "baseline")
            yield repository

    def _scan(self, repository: Path, recipe: str) -> tuple[int, str, str]:
        command = (
            self._recipe_body(recipe)
            .removeprefix("@")
            .replace("{{gitleaks}}", shlex.quote(str(self._gitleaks())))
        )
        bash = self._executable("bash")
        return asyncio.run(
            _execute(
                repository,
                (bash, "-euo", "pipefail", "-c", command),
                {**os.environ, "PATH": os.environ.get("PATH", "")},
            )
        )

    def _recipe_body(self, recipe: str) -> str:
        lines = (self.root / "justfile").read_text(encoding="utf-8").splitlines()
        declaration = f"{recipe}:"
        matches = [index for index, line in enumerate(lines) if line == declaration]
        self.assertEqual(len(matches), 1, f"expected one {recipe} recipe")
        body: list[str] = []
        for line in lines[matches[0] + 1 :]:
            if line and not line.startswith((" ", "\t")):
                break
            if line.startswith(("    ", "\t")):
                body.append(line.strip())
        self.assertEqual(len(body), 1, f"expected one command in {recipe}")
        return body[0]

    def _fixture_token(self, repository: Path) -> str:
        line = (repository / "tests/repository/fixtures/secret-scan/exact-fake.txt").read_text(
            encoding="utf-8"
        )
        return line.partition("=")[2].strip()

    def _commit(self, repository: Path, message: str) -> None:
        self._git(repository, "add", "--all")
        self._git(repository, "commit", "--quiet", "-m", message)

    def _git(self, repository: Path, *arguments: str) -> None:
        result = asyncio.run(
            _execute(repository, (self._executable("git"), *arguments), os.environ.copy())
        )
        self.assertEqual(result[0], 0, result)

    def _gitleaks(self) -> Path:
        configured = os.environ.get("GITLEAKS")
        if configured:
            return Path(configured)
        executable = shutil.which("gitleaks")
        if executable is not None:
            return Path(executable)
        self.fail("GITLEAKS or an executable gitleaks on PATH is required by this proof")

    def _executable(self, name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            self.fail(f"{name} executable is required by this release-gate proof")
        return executable


if __name__ == "__main__":
    unittest.main()
