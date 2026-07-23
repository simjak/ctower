"""Regression tests for runtime-state ignore boundaries."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class GitignorePolicyTests(unittest.TestCase):
    """Keep runtime spool state ignored without hiding authored source packages."""

    def test_root_runtime_spool_is_ignored_but_cli_source_is_trackable(self) -> None:
        root = Path(__file__).resolve().parents[2]
        runtime = self._check_ignore(root, "spool/policy-probe")
        source = self._check_ignore(
            root,
            "apps/ctowerctl/src/ctowerctl/spool/interface.py",
        )

        self.assertEqual(runtime.returncode, 0, runtime.stderr)
        self.assertEqual(source.returncode, 1, source.stdout)

    @staticmethod
    def _check_ignore(root: Path, relative: str) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "CHECK_IGNORE_PATH": relative}
        return subprocess.run(
            (
                sys.executable,
                "-c",
                "import os; os.execv('/usr/bin/git', "
                "['/usr/bin/git','check-ignore','--no-index','-v',"
                "os.environ['CHECK_IGNORE_PATH']])",
            ),
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
