"""Run Playwright without leaving generated evidence in the checkout."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

__all__ = ["main"]


def _external_temporary_parent(checkout: Path) -> Path:
    candidates = (Path(tempfile.gettempdir()).resolve(), checkout.parent)
    for candidate in candidates:
        if candidate != checkout and not candidate.is_relative_to(checkout):
            return candidate
    raise RuntimeError("cannot allocate Playwright artifacts outside the checkout")


async def _run_playwright(pnpm: str, checkout: Path, environment: dict[str, str]) -> int:
    process = await asyncio.create_subprocess_exec(
        pnpm,
        "exec",
        "playwright",
        "test",
        "--pass-with-no-tests",
        "--output",
        environment["PLAYWRIGHT_OUTPUT_DIR"],
        cwd=checkout,
        env=environment,
    )
    return await process.wait()


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
