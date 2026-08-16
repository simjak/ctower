"""Behavioral proof for the strict Requests adapter parser.

The browser must keep the record's order and refuse incomplete or unknown
payloads before a screen can mistake them for an empty/normal Request read.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_FIXTURE = Path(__file__).with_name("requests_fixtures.ts")


class RequestsParserTests(unittest.TestCase):
    def test_parser_keeps_record_order_and_project_answer_facts(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        parsed = cast("dict[str, Any]", outcomes["parsed"])
        rows = cast("list[dict[str, Any]]", parsed["rows"])

        self.assertEqual([row["reference"] for row in rows], ["R2", "R1"])
        self.assertEqual(rows[0]["owner"], "")
        self.assertEqual(parsed["answeredProjectCount"], 1)
        self.assertEqual(parsed["requestedProjectCount"], 1)
        self.assertEqual(parsed["watermark"], 7)

    def test_parser_refuses_unknown_state_missing_scope_and_missing_fields(self) -> None:
        outcomes = ts.drive(_FIXTURE)
        for name in (
            "rejectsUnknownState",
            "rejectsMissingUnansweredProjects",
            "rejectsMissingRowField",
        ):
            with self.subTest(case=name):
                self.assertTrue(outcomes[name]["thrown"], f"{name} defaulted malformed data")


if __name__ == "__main__":
    unittest.main()
