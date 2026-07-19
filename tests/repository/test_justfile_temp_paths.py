"""Execution-level isolation checks for scratch paths in just recipes."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


async def _execute(
    cwd: Path,
    argv: tuple[str, ...],
    env: dict[str, str],
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


class JustfileTempPathTests(unittest.TestCase):
    justfile = Path(__file__).parents[2] / "justfile"

    def test_recipes_pass_real_shell_variables_to_bash(self) -> None:
        source = self.justfile.read_text(encoding="utf-8")

        self.assertNotIn("$$", source)
        self.assertIn('coverage_file="$(mktemp)"', self._recipe_body("compatibility-coverage"))
        self.assertIn('coverage_file="$(mktemp)"', self._recipe_body("product-coverage"))
        self.assertIn('site_dir="$(mktemp -d)"', self._recipe_body("docs-check"))
        intended_tree = self._recipe_body("secrets-intended-tree")
        self.assertIn('scan_root="$(mktemp -d)"', intended_tree)
        self.assertIn('target="$scan_root/$file_path"', intended_tree)
        self.assertIn('coverage_file="$(mktemp)"', self._recipe_body("verify"))
        codegen = self._recipe_body("codegen-check")
        self.assertIn('pycache_dir="$(mktemp -d)"', codegen)
        self.assertIn('PYTHONPYCACHEPREFIX="$pycache_dir"', codegen)
        self.assertIn("trap 'rm -rf -- \"$pycache_dir\"' EXIT", codegen)

    def test_docs_and_coverage_paths_are_external_and_cleaned(self) -> None:
        for recipe in ("docs-check", "compatibility-coverage", "product-coverage"):
            for probe_exit in (0, 17):
                with self.subTest(recipe=recipe, probe_exit=probe_exit):
                    self._assert_external_cleaned_path(recipe, probe_exit)

    def _assert_external_cleaned_path(self, recipe: str, probe_exit: int) -> None:
        with (
            tempfile.TemporaryDirectory() as workspace_name,
            tempfile.TemporaryDirectory() as harness_name,
        ):
            workspace = Path(workspace_name)
            harness = Path(harness_name)
            record = harness / "observed-path.txt"
            probe = harness / "probe.py"
            probe.write_text(self._probe_source(), encoding="utf-8")

            command = self._render_recipe(recipe, probe)
            env = {
                **os.environ,
                "CTOWER_PROBE_EXIT": str(probe_exit),
                "CTOWER_SCRATCH_RECORD": str(record),
            }
            observed = asyncio.run(
                _execute(
                    workspace,
                    (self._executable("bash"), "-euo", "pipefail", "-c", command),
                    env,
                )
            )

            self.assertEqual(observed[0], probe_exit, observed)
            scratch_path = Path(record.read_text(encoding="utf-8"))
            self.assertTrue(scratch_path.is_absolute(), scratch_path)
            self.assertFalse(scratch_path.is_relative_to(workspace.resolve()), scratch_path)
            self.assertFalse(scratch_path.exists(), scratch_path)
            self.assertEqual(list(workspace.iterdir()), [])

    def _render_recipe(self, recipe: str, probe: Path) -> str:
        body = self._recipe_body(recipe)
        command = body.removeprefix("@")
        probe_command = f"{shlex.quote(sys.executable)} {shlex.quote(str(probe))}"
        return command.replace("{{python}}", probe_command)

    def _recipe_body(self, recipe: str) -> str:
        lines = self.justfile.read_text(encoding="utf-8").splitlines()
        declaration = f"{recipe}:"
        candidates = [index for index, line in enumerate(lines) if line.startswith(declaration)]
        self.assertEqual(len(candidates), 1, f"expected one {recipe} recipe")
        body: list[str] = []
        for line in lines[candidates[0] + 1 :]:
            if line and not line.startswith((" ", "\t")):
                break
            if line.startswith(("    ", "\t")):
                body.append(line.strip())
        self.assertTrue(body, f"expected a body for {recipe}")
        return "\n".join(body)

    def _executable(self, name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            self.fail(f"{name} executable is required by this test")
        return executable

    def _probe_source(self) -> str:
        return """\
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
if "--site-dir" in arguments:
    scratch = Path(arguments[arguments.index("--site-dir") + 1])
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "probe.txt").write_text("probe\\n", encoding="utf-8")
else:
    scratch = Path(os.environ["COVERAGE_FILE"])
    scratch.write_text("probe\\n", encoding="utf-8")
Path(os.environ["CTOWER_SCRATCH_RECORD"]).write_text(
    str(scratch.resolve()), encoding="utf-8"
)
raise SystemExit(int(os.environ["CTOWER_PROBE_EXIT"]))
"""


if __name__ == "__main__":
    unittest.main()
