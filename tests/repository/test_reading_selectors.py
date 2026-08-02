"""Semantic tests for the ranking selectors' mixed present/unavailable branches.

Round-2 review of PR #207 established that the structural boundary check proves
layer ownership, not semantic preservation: a selector may sit inside the read
layer and still erase unavailability while ranking. These tests close that gap
by executing the selector module itself and asserting on its outcomes.

`apps/ctower-ui/src/read/selectors.ts` is pure and imports only a type, so Node
runs it directly with type stripping — no bundler, no network, no live state and
no clock, which makes every case here deterministic.
"""

from __future__ import annotations

import json
import shutil
import unittest
from functools import cache
from pathlib import Path

import tools.process_execution as process_execution  # noqa: PLR0402

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).with_name("selector_fixtures.ts")
_TIMEOUT_SECONDS = 120


@cache
def _outcomes() -> dict[str, dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not on PATH for the selector fixtures")
    # the repository's single bounded process boundary, not a raw subprocess
    completed = process_execution.run(
        (node, "--no-warnings", str(_FIXTURES)),
        timeout_seconds=_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
    )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise TypeError("the selector fixture did not emit an object")
    return parsed


class ReadingSelectorTests(unittest.TestCase):
    """A missing input may never be discarded before a ranking is claimed."""

    def _case(self, name: str) -> dict[str, object]:
        case = _outcomes()[name]
        if not isinstance(case, dict):
            raise TypeError(f"selector case {name} is not an object")
        return case

    def test_a_complete_fan_out_ranks_and_reports_nothing_unread(self) -> None:
        case = self._case("complete")
        self.assertEqual(case["state"], "present")
        value = case["value"]
        assert isinstance(value, dict)
        self.assertEqual(value["chosen"], "newer")
        self.assertEqual(value["unread"], 0)
        self.assertIsNone(value["reason"])

    def test_a_mixed_fan_out_keeps_the_failure_and_marks_the_choice_provisional(self) -> None:
        for name in ("mixed", "mixedFirst"):
            with self.subTest(case=name):
                case = self._case(name)
                self.assertEqual(case["state"], "present")
                value = case["value"]
                assert isinstance(value, dict)
                self.assertEqual(value["chosen"], "survivor")
                self.assertEqual(value["unread"], 1, "an unread candidate was discarded")
                self.assertEqual(value["considered"], 2)
                self.assertEqual(value["reason"], "audit read timed out")

    def test_every_unread_candidate_is_counted(self) -> None:
        value = self._case("mixedMany")["value"]
        assert isinstance(value, dict)
        self.assertEqual(value["unread"], 2)
        self.assertEqual(value["considered"], 3)
        self.assertEqual(value["reason"], "first failure")

    def test_an_absent_candidate_is_not_counted_as_unread(self) -> None:
        value = self._case("absentDoesNotCountAsUnread")["value"]
        assert isinstance(value, dict)
        self.assertEqual(value["unread"], 0, "an empty stream answered; it is not a failed read")
        self.assertIsNone(value["reason"])

    def test_a_wholly_unavailable_fan_out_is_unavailable_not_absent(self) -> None:
        case = self._case("allUnavailable")
        self.assertEqual(case["state"], "unavailable")
        failure = case["failure"]
        assert isinstance(failure, dict)
        self.assertEqual(failure["reason"], "first failure")

    def test_a_wholly_absent_or_empty_fan_out_is_absent(self) -> None:
        for name in ("allAbsent", "empty"):
            with self.subTest(case=name):
                self.assertEqual(self._case(name)["state"], "absent")

    def test_a_strict_ranking_refuses_a_partial_fan_out(self) -> None:
        case = self._case("strictMixed")
        self.assertEqual(
            case["state"],
            "unavailable",
            "a superlative was claimed from a fan-out that was not fully read",
        )
        failure = case["failure"]
        assert isinstance(failure, dict)
        reason = failure["reason"]
        assert isinstance(reason, str)
        self.assertIn("1 of 2 candidates did not answer", reason)
        self.assertIn("join read failed", reason)

    def test_a_strict_ranking_refuses_rather_than_falling_back(self) -> None:
        case = self._case("strictAllUnavailable")
        self.assertEqual(
            case["state"],
            "unavailable",
            "the selector fell back to a candidate whose ordering value was never read",
        )

    def test_a_strict_ranking_still_answers_a_complete_fan_out(self) -> None:
        case = self._case("strictComplete")
        self.assertEqual(case["state"], "present")
        value = case["value"]
        assert isinstance(value, dict)
        self.assertEqual(value["chosen"], "newer")
        self.assertEqual(value["unread"], 0)


if __name__ == "__main__":
    unittest.main()
