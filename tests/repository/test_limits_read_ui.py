"""Behavioral proof for the strict credential-pool parser.

Two claims, both only checkable by running the shipped module.

The first is the record's own shape: each entry carries its own three axes and
its own reset clock, and the surface must keep them per entry and in the order
the record answered. A pool holding two capped accounts and one available one is
not one state, and a parser that flattened it would make the screen say it was.

The second is the projection allowlist as behaviour rather than as a grep. The
read projection has no field a credential value can occupy, so an entry that
arrives carrying one anyway — the shape a sweep taken beside a real credential
store would have if the closed boundary ever gave way — must come out of this
parser with neither the field nor its value anywhere in it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from repository import _typescript_modules as ts
else:
    from tests.repository import _typescript_modules as ts

_FIXTURE = Path(__file__).with_name("pool_limits_fixtures.ts")
_OUTCOMES: dict[str, Any] = {}

EXPECTED_TOPOLOGY_REVISION = 4
EXPECTED_REQUEST_COUNT = 412
EXPECTED_MILLICREDITS = 1250


def _outcomes() -> dict[str, Any]:
    if not _OUTCOMES:
        _OUTCOMES.update(ts.drive(_FIXTURE))
    return _OUTCOMES


def _profiles(case: str) -> list[dict[str, Any]]:
    parsed = cast("dict[str, Any]", _outcomes()[case])
    return cast("list[dict[str, Any]]", parsed["profiles"])


class PoolLimitsParserTests(unittest.TestCase):
    def test_every_entry_keeps_its_own_axes_and_its_own_clock(self) -> None:
        entries = cast("list[dict[str, Any]]", _profiles("parsed")[0]["entries"])
        self.assertEqual([entry["quotaState"] for entry in entries], ["capped", "available"])
        self.assertEqual(
            [entry["quotaResetAt"] for entry in entries],
            ["2026-08-20T06:29:00Z", None],
            "the two accounts' clocks were flattened into one",
        )
        self.assertEqual([entry["selectable"] for entry in entries], [False, True])
        self.assertEqual(entries[0]["authState"], "healthy")
        self.assertEqual(entries[0]["reachState"], "ok")
        self.assertEqual(entries[0]["requestCount"], EXPECTED_REQUEST_COUNT)
        self.assertEqual(entries[1]["meteredMillicredits"], EXPECTED_MILLICREDITS)
        self.assertIsNone(entries[1]["lastStatusObserved"])

    def test_the_record_s_own_profile_order_and_counts_survive(self) -> None:
        profiles = _profiles("parsed")
        self.assertEqual([profile["harnessKey"] for profile in profiles], ["hermes", "claude-code"])
        self.assertEqual([profile["profileKey"] for profile in profiles], ["engineer", "reviewer"])
        self.assertEqual([profile["selectableEntryCount"] for profile in profiles], [1, 0])
        self.assertEqual(profiles[0]["earliestKnownResetAt"], "2026-08-20T06:29:00Z")
        self.assertIsNone(profiles[1]["earliestKnownResetAt"])

    def test_a_drift_finding_and_the_weight_table_arrive_whole(self) -> None:
        parsed = cast("dict[str, Any]", _outcomes()["parsed"])
        drift = cast("list[dict[str, Any]]", _profiles("parsed")[0]["drift"])
        self.assertEqual(drift[0]["finding"], "missing")
        self.assertEqual(drift[0]["enactment"], "operator-ceremony")
        self.assertIn("did not observe it", drift[0]["detail"])
        weights = cast("list[dict[str, Any]]", parsed["weights"])
        self.assertEqual(weights[0]["modelRef"], "gpt-5")
        self.assertEqual(parsed["topologyRevision"], EXPECTED_TOPOLOGY_REVISION)

    def test_an_entry_carrying_credential_material_loses_it_at_the_boundary(self) -> None:
        outcomes = _outcomes()
        poisoned = json.dumps(outcomes["poisoned"])
        self.assertNotIn(
            cast("str", outcomes["poison"]),
            poisoned,
            "a credential value survived the read boundary and would reach the screen",
        )
        for name in ("secret_fingerprint", "secretFingerprint", "access_token", "accessToken"):
            with self.subTest(field=name):
                self.assertNotIn(name, poisoned)
        # and the entry is still read, whole, from the fields the projection does have
        entries = cast("list[dict[str, Any]]", _profiles("poisoned")[0]["entries"])
        self.assertEqual(entries[0]["providerKey"], "openai-codex")
        self.assertEqual(entries[0]["quotaState"], "capped")

    def test_the_parser_refuses_unknown_members_and_missing_fields(self) -> None:
        outcomes = _outcomes()
        for name in (
            "rejectsUnknownQuotaState",
            "rejectsUnknownHarness",
            "rejectsMissingSelectable",
            "rejectsMissingDriftDetail",
            "rejectsMissingTopologyRevision",
        ):
            with self.subTest(case=name):
                self.assertTrue(outcomes[name]["thrown"], f"{name} defaulted malformed data")


if __name__ == "__main__":
    unittest.main()
