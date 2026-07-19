"""Release clean-tree behavior from the fixed justfile porcelain recipe."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


async def _execute(cwd: Path, argv: tuple[str, ...]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
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


class JustfileCleanTreeTests(unittest.TestCase):
    justfile = Path(__file__).parents[2] / "justfile"

    def test_clean_repository_passes_and_non_repository_fails_closed(self) -> None:
        command = self._gate_command()
        with self._repository() as root:
            clean = self._run_gate(root, command)
        with tempfile.TemporaryDirectory() as name:
            non_repository = self._run_gate(Path(name), command)

        self.assertEqual(clean[0], 0, clean)
        self.assertNotEqual(non_repository[0], 0, non_repository)

    def test_staged_tracked_and_untracked_changes_each_fail(self) -> None:
        command = self._gate_command()
        for mutation in ("staged", "tracked", "untracked"):
            with self.subTest(mutation=mutation), self._repository() as root:
                self._make_dirty(root, mutation)
                observed = self._run_gate(root, command)

            self.assertNotEqual(observed[0], 0, observed)
            self.assertIn(
                f"{mutation}.txt" if mutation != "tracked" else "tracked.txt", observed[2]
            )

    def test_dirty_real_submodule_fails(self) -> None:
        command = self._gate_command()
        with self._repository() as root, tempfile.TemporaryDirectory() as child_name:
            child = Path(child_name)
            self._initialize_repository(child)
            self._git(
                root,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "--quiet",
                str(child),
                "deps/child",
            )
            self._git(root, "commit", "--quiet", "-m", "add submodule")
            (root / "deps/child/tracked.txt").write_text("dirty\n", encoding="utf-8")

            observed = self._run_gate(root, command)

        self.assertNotEqual(observed[0], 0, observed)
        self.assertIn("deps/child", observed[2])

    def test_verify_runs_the_same_recipe_before_and_after_its_body(self) -> None:
        self._assert_verify_clean_gate(self.justfile)

    def test_verify_rejects_a_missing_pre_or_post_clean_gate(self) -> None:
        source = self.justfile.read_text(encoding="utf-8")
        declaration = self._recipe_declaration(self.justfile, "verify")
        without_pre_gate = source.replace(
            declaration,
            declaration.replace("_verify-clean-tree ", "", 1),
            1,
        )
        without_post_gate = source.replace("    @just _verify-clean-tree", "    @true", 1)

        for mutation, content in (
            ("missing prerequisite", without_pre_gate),
            ("missing final command", without_post_gate),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as name:
                justfile = Path(name) / "justfile"
                justfile.write_text(content, encoding="utf-8")
                with self.assertRaises(AssertionError):
                    self._assert_verify_clean_gate(justfile)

    def _gate_command(self) -> str:
        declaration = self._recipe_declaration(self.justfile, "_verify-clean-tree")
        body = self._recipe_body(self.justfile, declaration)
        self.assertEqual(len(body), 1)
        return body[0].removeprefix("@")

    def _assert_verify_clean_gate(self, justfile: Path) -> None:
        declaration = self._recipe_declaration(justfile, "verify")
        prerequisites = declaration.partition(":")[2].split()
        body = self._recipe_body(justfile, declaration)

        self.assertEqual(prerequisites.count("_verify-clean-tree"), 1)
        self.assertTrue(body)
        self.assertEqual(body[-1], "@just _verify-clean-tree")

    def _recipe_body(self, justfile: Path, declaration: str) -> list[str]:
        lines = justfile.read_text(encoding="utf-8").splitlines()
        start = lines.index(declaration)
        body: list[str] = []
        for line in lines[start + 1 :]:
            if line and not line.startswith((" ", "\t")):
                break
            if line.startswith("    "):
                body.append(line.strip())
        return body

    def _recipe_declaration(self, justfile: Path, recipe: str) -> str:
        prefix = f"{recipe}:"
        matches = [
            line
            for line in justfile.read_text(encoding="utf-8").splitlines()
            if line.startswith(prefix)
        ]
        self.assertEqual(len(matches), 1, f"expected one {recipe} recipe")
        return matches[0]

    def _run_gate(self, root: Path, command: str) -> tuple[int, str, str]:
        bash = self._executable("bash")
        return asyncio.run(_execute(root, (bash, "-euo", "pipefail", "-c", command)))

    def _make_dirty(self, root: Path, mutation: str) -> None:
        path = root / ("tracked.txt" if mutation == "tracked" else f"{mutation}.txt")
        path.write_text(f"{mutation}\n", encoding="utf-8")
        if mutation == "staged":
            self._git(root, "add", path.name)

    def _git(self, root: Path, *arguments: str) -> None:
        result = asyncio.run(_execute(root, (self._executable("git"), *arguments)))
        self.assertEqual(result[0], 0, result)

    def _executable(self, name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            self.fail(f"{name} executable is required by this test")
        return executable

    @contextmanager
    def _repository(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self._initialize_repository(root)
            yield root

    def _initialize_repository(self, root: Path) -> None:
        self._git(root, "init", "--quiet")
        self._git(root, "config", "user.name", "ctower test")
        self._git(root, "config", "user.email", "ctower-test@example.invalid")
        (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self._git(root, "add", "tracked.txt")
        self._git(root, "commit", "--quiet", "-m", "baseline")


if __name__ == "__main__":
    unittest.main()
