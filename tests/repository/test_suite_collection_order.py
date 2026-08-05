"""Test collection must not depend on which suite pytest visits first.

`tests/modules/__init__.py` makes `tests/modules/**` a real dotted package, so pytest's
default "prepend" import mode puts `tests/` itself on `sys.path` the first time it
collects anything under `tests/modules/`. `tests/acceptance/increment-1/` carries no
`__init__.py` (its own directory name is not a valid package component), so a bare
`from modules...` import there previously only resolved once some `tests/modules/` file
had already been collected in the same process — silently order-dependent, and always
absent in the deferred `increment-1-acceptance` suite, which collects
`tests/acceptance/increment-1` on its own. Fixed by putting `tests` on
`[tool.pytest.ini_options].pythonpath` so it is importable from the first collected file,
regardless of order.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).parents[2]

__all__: tuple[str, ...] = ()


async def _collect(*paths: str) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pytest",
        *paths,
        "-q",
        "--collect-only",
        cwd=_ROOT,
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


class SuiteCollectionOrderTests(unittest.TestCase):
    def test_the_deferred_acceptance_suite_collects_standalone(self) -> None:
        """The exact command `increment-1-acceptance` runs, alone, per expected-suites.toml."""

        returncode, stdout, stderr = asyncio.run(_collect("tests/acceptance/increment-1"))

        self.assertEqual(returncode, 0, stdout + stderr)
        self.assertNotIn("ModuleNotFoundError", stdout + stderr)

    def test_the_modules_then_acceptance_order_still_collects(self) -> None:
        """The order `just check`/`just verify` actually run, modules ahead of acceptance."""

        returncode, stdout, stderr = asyncio.run(
            _collect("tests/modules", "tests/acceptance/increment-1")
        )

        self.assertEqual(returncode, 0, stdout + stderr)
        self.assertNotIn("ModuleNotFoundError", stdout + stderr)


if __name__ == "__main__":
    unittest.main()
