"""Repository contracts for the stable and reproducible verification gate."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import cast

_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_EXACT_VERSION = re.compile(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.-]+\])?==[^\s;]+")


class VerificationSupplyChainTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_release_gate_has_one_stable_safe_full_history_context(self) -> None:
        workflow = self._read(".github/workflows/verify.yml")
        graph_completion_script = """\
          set -euo pipefail
          shallow_state="$(git rev-parse --is-shallow-repository)"
          printf 'is-shallow-repository=%s\\n' "${shallow_state}"
          shallow_path="$(git rev-parse --git-path shallow)"
          if [[ "${shallow_state}" == "true" ]]; then
            printf '.git/shallow stat:\\n'
            stat "${shallow_path}"
            printf '.git/shallow contents:\\n'
            cat "${shallow_path}"
            printf 'origin/main=%s\\n' "$(git rev-parse --verify 'origin/main^{commit}')"
            git fetch --unshallow origin
          fi
          final_shallow_state="$(git rev-parse --is-shallow-repository)"
          printf 'is-shallow-repository-after=%s\\n' "${final_shallow_state}"
          if [[ "${final_shallow_state}" != "false" ]]; then
            printf 'repository graph must be complete\\n' >&2
            exit 1
          fi
"""
        graph_completion_step = f"""\
      - name: Establish complete repository graph
        shell: bash
        run: |
{graph_completion_script}"""

        self.assertEqual(workflow.count("name: release gate"), 1)
        self.assertEqual(workflow.count("run: just check"), 1)
        self.assertEqual(workflow.count("run: just verify"), 1)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertEqual(workflow.count(graph_completion_step), 3)
        self.assertIn(
            "          persist-credentials: false\n\n" + graph_completion_step,
            workflow,
        )
        self.assertIn(
            graph_completion_step
            + "\n      - name: Run canonical warm gate\n"
            + "        run: just check",
            workflow,
        )
        self.assertIn(
            graph_completion_step
            + "\n      - name: Run canonical release gate\n"
            + "        run: just verify",
            workflow,
        )
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("pull_request_target", workflow)

    def test_workflow_installs_only_exact_checksum_or_hash_locked_inputs(self) -> None:
        workflow = self._read(".github/workflows/verify.yml")
        environment = self._workflow_environment(workflow)

        for name in ("NODE", "PNPM", "JUST", "ACTIONLINT", "GITLEAKS"):
            with self.subTest(tool=name):
                self.assertRegex(environment[f"CTOWER_VERIFY_{name}"], r"^\d+\.\d+\.\d+$")
                self.assertIsNotNone(_SHA256.fullmatch(environment[f"CTOWER_VERIFY_{name}_SHA256"]))
        self.assertRegex(environment["CTOWER_VERIFY_PYTHON"], r"^\d+\.\d+\.\d+$")
        self.assertIn("--require-hashes", workflow)
        self.assertIn("pnpm install --frozen-lockfile --ignore-scripts", workflow)
        self.assertIn('"${binary_root}/pnpm" "${CTOWER_VERIFY_PNPM_SHA256}"', workflow)
        self.assertIn("--connect-timeout 15 --max-time 300", workflow)
        self.assertNotIn("npm install --global", workflow)

    def test_python_and_javascript_verification_locks_are_present(self) -> None:
        direct = [
            line
            for line in self._read("requirements/verify.in").splitlines()
            if line and not line.startswith("#")
        ]
        compiled = self._read("requirements/verify.txt")
        package = cast(dict[str, object], json.loads(self._read("package.json")))
        workflow_environment = self._workflow_environment(
            self._read(".github/workflows/verify.yml")
        )

        self.assertTrue(direct)
        self.assertTrue(all(_EXACT_VERSION.fullmatch(line) for line in direct), direct)
        self.assertIn("uv 0.11.3", self._read("requirements/verify.in"))
        self.assertIn("uv 0.11.3", compiled)
        self.assertIn("--hash=sha256:", compiled)
        self.assertNotIn("git+", compiled)
        self.assertNotIn("-e ", compiled)
        self.assertRegex(
            cast(str, package["packageManager"]),
            rf"^pnpm@{re.escape(workflow_environment['CTOWER_VERIFY_PNPM'])}"
            r"\+sha512-[A-Za-z0-9+/=]+$",
        )
        self.assertTrue((self.root / "pnpm-lock.yaml").is_file())
        self.assertFalse((self.root / ".python-version").exists())
        self.assertFalse((self.root / "uv.lock").exists())

    def test_lock_stale_against_input(self) -> None:
        direct_input = self._read("requirements/verify.in")
        compiled = self._read("requirements/verify.txt")
        direct = [line for line in direct_input.splitlines() if line and not line.startswith("#")]
        # Resolved definitions in the compiled lock: `name==version` (name and any
        # extras are normalized by uv: coverage[toml] -> coverage, SecretStorage ->
        # secretstorage, ruamel.yaml -> ruamel-yaml). The version is the token before
        # any platform marker or the trailing backslash.
        resolved = dict(re.findall(r"^([A-Za-z0-9_.\-\[\]]+)==([^ \\\n]+)", compiled, re.MULTILINE))

        def _normalize(name: str) -> str:
            return re.sub(r"\[.*\]", "", name).lower().replace("_", "-").replace(".", "-")

        stale = [
            pin
            for pin in direct
            if resolved.get(_normalize(pin.split("==", 1)[0])) != pin.split("==", 1)[1]
        ]
        self.assertFalse(
            stale,
            "lock-stale-against-input: requirements/verify.txt is not a current "
            "compile of requirements/verify.in — these direct pins do not match the "
            f"locked version: {stale}",
        )

    def test_remote_precommit_hooks_are_immutable_commit_pins(self) -> None:
        source = self._read(".pre-commit-config.yaml")
        remote_repositories = 0
        for block in source.split("  - repo: ")[1:]:
            repository, *lines = block.splitlines()
            if repository.strip() == "local":
                continue
            remote_repositories += 1
            revs = [
                line.partition("rev:")[2].strip().split()[0] for line in lines if "rev:" in line
            ]
            self.assertEqual(len(revs), 1, repository)
            self.assertIsNotNone(_COMMIT.fullmatch(revs[0]), (repository, revs))
        self.assertGreater(remote_repositories, 0)

    def test_gitleaks_hook_and_canonical_gates_use_installed_binary_directly(self) -> None:
        precommit = self._read(".pre-commit-config.yaml")
        justfile = self._read("justfile")
        check = next(line for line in justfile.splitlines() if line.startswith("check:"))
        verify = next(line for line in justfile.splitlines() if line.startswith("verify:"))

        self.assertNotIn("github.com/gitleaks/gitleaks", precommit)
        self.assertIn("- id: gitleaks-staged", precommit)
        self.assertIn("language: system", precommit)
        self.assertIn("gitleaks git . --staged", precommit)
        self.assertIn("secrets-intended-tree", check.partition(":")[2].split())
        self.assertNotIn(
            "pre-commit", "\n".join(self._recipe_body(justfile, "secrets-intended-tree"))
        )
        self.assertNotIn("secrets-intended-tree", verify.partition(":")[2].split())
        self.assertIn("@just secrets-history", self._recipe_body(justfile, "verify"))
        self.assertNotIn("go install", precommit + justfile)

    def test_actionlint_is_a_dependency_of_the_canonical_warm_gate(self) -> None:
        justfile = self._read("justfile")
        check = next(line for line in justfile.splitlines() if line.startswith("check:"))

        self.assertIn("workflow-check", check.partition(":")[2].split())
        self.assertEqual(self._recipe_body(justfile, "workflow-check"), ["actionlint"])

    def test_python_tools_follow_the_configured_interpreter(self) -> None:
        justfile = self._read("justfile")
        python_check = self._recipe_body(justfile, "python-check")

        self.assertEqual(len(python_check), 3)
        self.assertTrue(python_check[0].startswith("{{python}} -m ruff format "))
        self.assertTrue(python_check[1].startswith("{{python}} -m ruff check "))
        self.assertTrue(python_check[2].startswith("{{python}} -m mypy "))
        self.assertEqual(self._recipe_body(justfile, "workflow-check"), ["actionlint"])
        self.assertIn("{{gitleaks}}", self._recipe_body(justfile, "secrets-history")[0])
        self.assertIn("@just secrets-history", self._recipe_body(justfile, "verify"))

    def _workflow_environment(self, workflow: str) -> dict[str, str]:
        values: dict[str, str] = {}
        inside_environment = False
        for line in workflow.splitlines():
            if line == "env:":
                inside_environment = True
                continue
            if inside_environment and line and not line.startswith("  "):
                break
            if inside_environment and line.startswith("  CTOWER_VERIFY_"):
                key, _, value = line.strip().partition(":")
                values[key] = value.strip().strip('"')
        return values

    def _recipe_body(self, justfile: str, recipe: str) -> list[str]:
        lines = justfile.splitlines()
        starts = [index for index, line in enumerate(lines) if line.startswith(f"{recipe}:")]
        self.assertEqual(len(starts), 1, f"expected one {recipe} recipe")
        start = starts[0]
        body: list[str] = []
        for line in lines[start + 1 :]:
            if line and not line.startswith((" ", "\t")):
                break
            if line.startswith(("    ", "\t")):
                body.append(line.strip())
        return body

    def _read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
