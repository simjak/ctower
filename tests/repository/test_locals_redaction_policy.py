"""Execution proof that a failing test's secret-shaped locals never render (gh#290)."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_FAKE_SECRET_VALUE = "sk-fake-CTOWER-TEST-SECRET-DO-NOT-LEAK-4f8b2c91"  # noqa: S105 - fake, proves redaction
_SAFE_VALUE = "us-east-1"

# Mirrors the real defect: `_compose_async` in tests/modules/migration/_postgres.py takes an
# `environment` dict (built from `{**os.environ, ...}`) as a call argument and raises on failure,
# which put a live ANTHROPIC_AUTH_TOKEN into pytest's default failure rendering.
_FAILING_MODULE = f'''
import pytest

FAKE_SECRET_VALUE = "{_FAKE_SECRET_VALUE}"


@pytest.fixture
def environment():
    return {{"ANTHROPIC_AUTH_TOKEN": FAKE_SECRET_VALUE, "REGION": "{_SAFE_VALUE}"}}


def _compose(environment):
    raise RuntimeError("docker compose failed")


def test_fake_secret_never_renders(environment):
    _compose(environment)
'''


async def _execute(cwd: Path, argv: tuple[str, ...]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=os.environ.copy(),
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


class LocalsRedactionPolicyTests(unittest.TestCase):
    root = Path(__file__).parents[2]

    def test_secret_value_never_renders_in_failure_output(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            harness = Path(name)
            shutil.copyfile(self.root / "conftest.py", harness / "conftest.py")
            (harness / "test_fake_leak.py").write_text(_FAILING_MODULE, encoding="utf-8")

            worst_case = self._run(harness, "-l", "--tb=long")
            default_invocation = self._run(harness)

        for returncode, combined in (worst_case, default_invocation):
            self.assertNotEqual(returncode, 0, combined)
            self.assertNotIn(_FAKE_SECRET_VALUE, combined, combined)

        # Redaction is targeted, not blanket suppression: the sensitive key name and an
        # unrelated sibling value stay visible so the failure is still diagnosable.
        _, worst_case_output = worst_case
        self.assertIn("ANTHROPIC_AUTH_TOKEN", worst_case_output)
        self.assertIn(_SAFE_VALUE, worst_case_output)

    def _run(self, harness: Path, *flags: str) -> tuple[int, str]:
        returncode, stdout, stderr = asyncio.run(
            _execute(
                harness,
                (
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    *flags,
                    "test_fake_leak.py",
                ),
            )
        )
        return returncode, stdout + stderr


if __name__ == "__main__":
    unittest.main()
