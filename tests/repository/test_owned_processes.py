"""Behavioral tests for lifetime-bound verifier process cleanup."""

from __future__ import annotations

import asyncio
import io
import os
import signal
import subprocess
import sys
import textwrap
import time
import unittest
from contextlib import redirect_stderr
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
    def test_nondumpable_owned_process_is_unknown_and_remains_unsignalled(self) -> None:
        owner = "dumpable-zero-evidence"
        environment = os.environ | {_OWNER_ENV: owner}
        child_source = textwrap.dedent(
            """
                import ctypes
                import signal

                libc = ctypes.CDLL(None, use_errno=True)
                assert libc.prctl(4, 0, 0, 0, 0) == 0
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                print("ready", flush=True)
                signal.pause()
            """
        )
        process = subprocess.Popen(  # noqa: S603 - fixed interpreter and source
            (sys.executable, "-c", child_source),
            env=environment,
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            assert process.stdout is not None
            self.assertEqual(process.stdout.readline().strip(), "ready")
            with self.assertRaises(PermissionError):
                Path(f"/proc/{process.pid}/environ").read_bytes()
            result = asyncio.run(
                terminate_owned_processes(
                    _OWNER_ENV,
                    owner,
                    term_grace_seconds=0,
                    kill_grace_seconds=0,
                    candidate_pids=(process.pid,),
                    candidate_session_ids=(process.pid,),
                )
            )
            self.assertIs(result.outcome, TerminationOutcome.UNKNOWN)
            self.assertEqual((result.scanned, result.readable, result.unreadable), (1, 0, 1))
            self.assertEqual(result.unreadable_pids, (process.pid,))
            self.assertEqual(result.candidate_unreadable_pids, (process.pid,))
            self.assertIsNone(process.poll())
        finally:
            if process.poll() is None:
                os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()

    def test_stale_numeric_candidate_never_signals_an_unrelated_process(self) -> None:
        process = subprocess.Popen(
            (sys.executable, "-c", "import sys; sys.stdin.read()"),
            stdin=subprocess.PIPE,
            text=True,
        )
        try:
            started = time.monotonic()
            observation = owned_processes._OwnershipObservation(
                scanned=1,
                readable=1,
                unreadable_pids=(),
                candidate_unreadable_pids=(),
                owned_pids=(process.pid,),
            )
            with (
                mock.patch.object(
                    owned_processes, "_observe_owned_processes", return_value=observation
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
                owned_processes, "_observe_owned_processes", return_value=observation
            ):
                reused_outcome = asyncio.run(
                    terminate_owned_processes(
                        _OWNER_ENV,
                        "stale-observation",
                        term_grace_seconds=0,
                        kill_grace_seconds=0,
                    )
                )
            self.assertIs(vanished_outcome.outcome, TerminationOutcome.SURVIVED)
            self.assertIs(reused_outcome.outcome, TerminationOutcome.SURVIVED)
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

        impossible_pid = (
            int(Path("/proc/sys/kernel/pid_max").read_text(encoding="utf-8").strip()) + 1
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
                    "--candidate-pid",
                    str(impossible_pid),
                ]
            ),
            int(TerminationOutcome.GRACEFUL),
        )
        unknown_observation = owned_processes._OwnershipObservation(
            scanned=5,
            readable=4,
            unreadable_pids=(123,),
            candidate_unreadable_pids=(123,),
            owned_pids=(),
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(
                owned_processes,
                "_observe_owned_processes",
                return_value=unknown_observation,
            ),
            redirect_stderr(stderr),
        ):
            exit_status = owned_processes.main(
                [
                    "CTOWER_TEST_OWNER",
                    "unknown-owner",
                    "--term-grace-seconds",
                    "0",
                    "--kill-grace-seconds",
                    "0",
                ]
            )
        self.assertEqual(exit_status, int(TerminationOutcome.UNKNOWN))
        self.assertIn("UNKNOWN: scanned 5, readable 4, unreadable 1", stderr.getvalue())
        self.assertIn("candidate unreadable pids: 123", stderr.getvalue())
        with self.assertRaises(ProcessLookupError):
            owned_processes._open_pidfd(impossible_pid)


if __name__ == "__main__":
    unittest.main()
