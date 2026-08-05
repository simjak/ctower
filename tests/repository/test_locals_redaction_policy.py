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

# Value-shaped bypass (a): a DSN password under the innocent key `dsn` — the repo's own
# `_wait_for_postgres(dsn)` (tests/modules/migration/_postgres.py) renders exactly this shape by
# default (no `-l` needed: `dsn` is a call argument, not a local).
_FAKE_DSN_PASSWORD = "hunter7-fake-CTOWER-DSN-PW"  # noqa: S105 - fake, proves redaction
_FAKE_DSN_HOST = "dbhost.internal:5432/appdb"
_DSN_FAILING_MODULE = f"""
import pytest


@pytest.fixture
def dsn():
    return "postgresql://appuser:{_FAKE_DSN_PASSWORD}@{_FAKE_DSN_HOST}"


def _wait_for_postgres(dsn):
    raise RuntimeError("PostgreSQL did not start")


def test_dsn_password_never_renders(dsn):
    _wait_for_postgres(dsn)
"""

# Value-shaped bypass (b): a Bearer token under the innocent key `innocent_header` — the key
# never matches `_SENSITIVE_KEY`, only the value's `Bearer <token>` shape does.
_FAKE_BEARER_TOKEN = "xyz123-fake-CTOWER-BEARER-TOKEN"  # noqa: S105 - fake, proves redaction
_BEARER_FAILING_MODULE = f"""
import pytest


@pytest.fixture
def headers():
    return {{"innocent_header": "Bearer {_FAKE_BEARER_TOKEN}"}}


def _send(headers):
    raise RuntimeError("request failed")


def test_bearer_value_never_renders(headers):
    _send(headers)
"""

# Value-shaped bypass (c): a base64-shaped secret under the innocent key `payload`. Low-entropy
# (repeating blocks) by construction so gitleaks' own generic-api-key rule does not flag this
# fixture literal as a real high-entropy secret while still fulfilling the base64-token shape.
_FAKE_BASE64_SECRET = "FakeFakeFakeFakeFakeFake12341234"  # noqa: S105 - fake
_BASE64_FAILING_MODULE = f'''
import pytest


@pytest.fixture
def response():
    return {{"payload": "{_FAKE_BASE64_SECRET}"}}


def _handle(response):
    raise RuntimeError("handler failed")


def test_base64_payload_never_renders(response):
    _handle(response)
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
            harness = self._harness(name, _FAILING_MODULE)
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

    def test_dsn_password_never_renders_under_innocent_key(self) -> None:
        """Bypass (a): key-based scrub never sees a password under the innocent key `dsn`."""
        with tempfile.TemporaryDirectory() as name:
            harness = self._harness(name, _DSN_FAILING_MODULE)
            worst_case = self._run(harness, "-l", "--tb=long")
            default_invocation = self._run(harness)

        for returncode, combined in (worst_case, default_invocation):
            self.assertNotEqual(returncode, 0, combined)
            self.assertNotIn(_FAKE_DSN_PASSWORD, combined, combined)

        # Diagnostic value preserved: host/db are not the credential, so they stay visible.
        _, default_output = default_invocation
        self.assertIn(_FAKE_DSN_HOST, default_output)

    def test_bearer_token_never_renders_under_innocent_key(self) -> None:
        """Bypass (b): key-based scrub never sees a Bearer token under `innocent_header`."""
        with tempfile.TemporaryDirectory() as name:
            harness = self._harness(name, _BEARER_FAILING_MODULE)
            worst_case = self._run(harness, "-l", "--tb=long")
            default_invocation = self._run(harness)

        for returncode, combined in (worst_case, default_invocation):
            self.assertNotEqual(returncode, 0, combined)
            self.assertNotIn(_FAKE_BEARER_TOKEN, combined, combined)

        # Diagnostic value preserved: the auth scheme word stays visible.
        _, default_output = default_invocation
        self.assertIn("Bearer", default_output)

    def test_base64_payload_never_renders_under_innocent_key(self) -> None:
        """Bypass (c): key-based scrub never sees a base64-shaped secret under `payload`."""
        with tempfile.TemporaryDirectory() as name:
            harness = self._harness(name, _BASE64_FAILING_MODULE)
            worst_case = self._run(harness, "-l", "--tb=long")
            default_invocation = self._run(harness)

        for returncode, combined in (worst_case, default_invocation):
            self.assertNotEqual(returncode, 0, combined)
            self.assertNotIn(_FAKE_BASE64_SECRET, combined, combined)

    def _harness(self, tmp_dir: str, module_source: str) -> Path:
        harness = Path(tmp_dir)
        shutil.copyfile(self.root / "conftest.py", harness / "conftest.py")
        (harness / "test_fake_leak.py").write_text(module_source, encoding="utf-8")
        return harness

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
