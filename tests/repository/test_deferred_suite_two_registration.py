"""A deferred suite must be registered exactly twice, or not at all."""

from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
_MANIFEST = ROOT / "tools/checks/expected-suites.toml"
_FIXTURE = ROOT / "tests/contracts/evidence/fixtures/i1-complete-manifest.json"


def _deferred_suite_ids() -> set[str]:
    manifest = tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))
    return {suite["id"] for suite in manifest["suite"] if suite.get("status") == "deferred"}


def _fixture_deferred_ids() -> tuple[list[str], list[str]]:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    entries = fixture.get("deferred_suites")
    if not isinstance(entries, list):  # fail closed on a missing/renamed key
        raise TypeError(f"{_FIXTURE.relative_to(ROOT)} has no deferred_suites list")
    ids: list[str] = []
    malformed: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("suite_id"), str):
            malformed.append(repr(entry))
            continue
        ids.append(entry["suite_id"])
    if malformed:
        raise AssertionError(
            "deferred_suites rows without a string suite_id: " + ", ".join(malformed)
        )
    return ids, [i for i, c in sorted((i, ids.count(i)) for i in set(ids)) if ids.count(i) > 1]


class TwoRegistrationGuardTests(unittest.TestCase):
    def test_fixture_deferred_suites_match_the_registry_exactly(self) -> None:
        """The two-registration trap cannot reopen.

        ``expected-suites.toml`` (status = "deferred") and the evidence
        fixture's ``deferred_suites`` must name the SAME suite id set — no
        registry deferral without a matching fixture row (the suite silently
        leaves the evidence denominator), no fixture row without a registry
        deferral (a row that claims a deferral the gate never granted). Both
        directions, exact set equality, duplicates refused.
        """

        registered = _deferred_suite_ids()
        self.assertTrue(registered, "no deferred suites found in the registry")

        fixture_ids, duplicates = _fixture_deferred_ids()
        self.assertFalse(
            duplicates,
            f"duplicate deferred_suites rows in the evidence fixture: {duplicates}",
        )

        missing = sorted(registered - set(fixture_ids))
        unregistered = sorted(set(fixture_ids) - registered)
        self.assertFalse(
            missing,
            f"deferred in expected-suites.toml but absent from the evidence "
            f"fixture's deferred_suites: {missing}",
        )
        self.assertFalse(
            unregistered,
            f"in the evidence fixture's deferred_suites but not deferred in "
            f"expected-suites.toml: {unregistered}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
