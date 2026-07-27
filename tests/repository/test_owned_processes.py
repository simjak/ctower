"""Behavioral tests for lifetime-bound verifier process cleanup."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.checks import owned_processes
from tools.checks.owned_processes import (
    TerminationOutcome,
    terminate_owned_processes,
)

__all__ = ()

_OWNER_ENV = "CTOWER_VERIFY_SUITE_OWNER"


class OwnedProcessTests(unittest.TestCase):
    def test_stale_numeric_candidate_never_signals_an_unrelated_process(self) -> None:
        process = subprocess.Popen(
            (sys.executable, "-c", "import sys; sys.stdin.read()"),
            stdin=subprocess.PIPE,
            text=True,
        )
        try:
            started = time.monotonic()
            with (
                mock.patch.object(
                    owned_processes, "_owned_process_ids", return_value=(process.pid,)
                ),
                mock.patch.object(owned_processes, "_open_pidfd", side_effect=ProcessLookupError),
            ):
                vanished_outcome = asyncio.run(
                    terminate_owned_processes(
                        _OWNER_ENV,
                        "vanished-observation",
                        term_grace_seconds=0,
                        kill_grace_seconds=0,
                    )
                )
            with mock.patch.object(
                owned_processes, "_owned_process_ids", return_value=(process.pid,)
            ):
                reused_outcome = asyncio.run(
                    terminate_owned_processes(
                        _OWNER_ENV,
                        "stale-observation",
                        term_grace_seconds=0,
                        kill_grace_seconds=0,
                    )
                )
            self.assertIs(vanished_outcome, TerminationOutcome.SURVIVED)
            self.assertIs(reused_outcome, TerminationOutcome.SURVIVED)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertIsNone(process.poll())
        finally:
            assert process.stdin is not None
            process.stdin.close()
            process.wait(timeout=2)

    def test_marker_bounds_and_missing_pid_fail_closed(self) -> None:
        cases = (
            ("invalid environment name", "lowercase", "owner", 0.0, 0.0),
            ("empty owner", "CTOWER_TEST_OWNER", "", 0.0, 0.0),
            ("infinite grace", "CTOWER_TEST_OWNER", "owner", float("inf"), 0.0),
        )
        for label, environment_name, owner, term_grace, kill_grace in cases:
            with self.subTest(label=label), self.assertRaises(ValueError):
                asyncio.run(
                    terminate_owned_processes(
                        environment_name,
                        owner,
                        term_grace_seconds=term_grace,
                        kill_grace_seconds=kill_grace,
                    )
                )

        self.assertEqual(
            owned_processes.main(
                [
                    "CTOWER_TEST_OWNER",
                    "absent-owner",
                    "--term-grace-seconds",
                    "0",
                    "--kill-grace-seconds",
                    "0",
                ]
            ),
            int(TerminationOutcome.GRACEFUL),
        )
        impossible_pid = (
            int(Path("/proc/sys/kernel/pid_max").read_text(encoding="utf-8").strip()) + 1
        )
        with self.assertRaises(ProcessLookupError):
            owned_processes._open_pidfd(impossible_pid)


if __name__ == "__main__":
    unittest.main()
