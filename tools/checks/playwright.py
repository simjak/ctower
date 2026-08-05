"""Run Playwright without leaving generated evidence in the checkout, under one deadline."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path

from tools.checks.owned_processes import terminate_owned_processes

__all__ = ["main"]

# Mirrors expected-suites.toml's "browser-e2e" suite timeout_seconds; keep both in sync.
_TIMEOUT_SECONDS = 900
_TIMEOUT_EXIT_CODE = 124
_OWNER_ENVIRONMENT_NAME = "CTOWER_PLAYWRIGHT_OWNER"
_TERM_GRACE_SECONDS = 0.25
_KILL_GRACE_SECONDS = 0.25
_DIAGNOSTIC_ENTRY_LIMIT = 20


def _external_temporary_parent(checkout: Path) -> Path:
    candidates = (Path(tempfile.gettempdir()).resolve(), checkout.parent)
    for candidate in candidates:
        if candidate != checkout and not candidate.is_relative_to(checkout):
            return candidate
    raise RuntimeError("cannot allocate Playwright artifacts outside the checkout")


async def _run_playwright(pnpm: str, checkout: Path, environment: dict[str, str]) -> int:
    owner = uuid.uuid4().hex
    environment[_OWNER_ENVIRONMENT_NAME] = owner
    process = await asyncio.create_subprocess_exec(
        pnpm,
        "exec",
        "playwright",
        "test",
        "--output",
        environment["PLAYWRIGHT_OUTPUT_DIR"],
        cwd=checkout,
        env=environment,
        start_new_session=True,
    )
    try:
        return await asyncio.wait_for(process.wait(), timeout=_TIMEOUT_SECONDS)
    except TimeoutError:
        await _fail_on_timeout(process, owner, environment)
        return _TIMEOUT_EXIT_CODE


async def _fail_on_timeout(
    process: asyncio.subprocess.Process, owner: str, environment: dict[str, str]
) -> None:
    cleanup = await terminate_owned_processes(
        _OWNER_ENVIRONMENT_NAME,
        owner,
        term_grace_seconds=_TERM_GRACE_SECONDS,
        kill_grace_seconds=_KILL_GRACE_SECONDS,
        candidate_pids=(process.pid,),
        candidate_session_ids=(process.pid,),
    )
    partial_artifacts = ", ".join(
        _bounded_listing(environment[key])
        for key in ("PLAYWRIGHT_HTML_OUTPUT_DIR", "PLAYWRIGHT_OUTPUT_DIR")
    )
    print(
        f"Playwright gate exceeded its {_TIMEOUT_SECONDS} second deadline; "
        f"process tree cleanup {cleanup.outcome.name} ({cleanup.observation_summary()}); "
        f"partial artifacts: {partial_artifacts}",
        file=sys.stderr,
    )


def _bounded_listing(directory: str) -> str:
    root = Path(directory)
    entries = (
        sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
        if root.is_dir()
        else []
    )
    if not entries:
        return f"{root.name}: none"
    shown = entries[:_DIAGNOSTIC_ENTRY_LIMIT]
    remainder = len(entries) - len(shown)
    suffix = f" (+{remainder} more)" if remainder else ""
    return f"{root.name}: {', '.join(shown)}{suffix}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the fixed repository E2E command with automatically cleaned output."""

    if argv:
        raise ValueError("the repository Playwright gate does not accept command overrides")

    checkout = Path.cwd().resolve()
    temporary_parent = _external_temporary_parent(checkout)
    with tempfile.TemporaryDirectory(prefix="ctower-playwright-", dir=temporary_parent) as name:
        artifact_root = Path(name)
        environment = os.environ.copy()
        environment["PLAYWRIGHT_HTML_OUTPUT_DIR"] = str(artifact_root / "html-report")
        environment["PLAYWRIGHT_OUTPUT_DIR"] = str(artifact_root / "test-results")
        pnpm = shutil.which("pnpm", path=environment.get("PATH"))
        if pnpm is None:
            raise RuntimeError("pnpm is required by the repository Playwright gate")
        return_code = asyncio.run(_run_playwright(pnpm, checkout, environment))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
