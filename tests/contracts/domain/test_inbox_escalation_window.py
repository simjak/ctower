"""The declared P0 acknowledgement window is one number, stated identically everywhere."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
_WINDOW = "15 minutes"
_PROVENANCE = "operator-confirmed 2026-08-17"
_MANIFEST = "tests/contracts/evidence/fixtures/i1-complete-manifest.json"


def test_spec_declares_the_p0_acknowledgement_window_as_one_number() -> None:
    prose = re.sub(r"\s+", " ", _spec_section("### Inbox transport severity and pull contract"))

    assert f"declared P0 acknowledgement window is {_WINDOW}" in prose
    assert "through its declared acknowledgement window" not in prose, (
        "SPEC still points at a window value it never states"
    )
    assert "no scheduler, no escalation event kind, and no consumer" in prose, (
        "SPEC omits that the window is declared while the timer that observes it is unbuilt"
    )


def test_decision_d70_declares_the_same_window_with_its_provenance() -> None:
    clause = _decision_clause("## D70 — Inbox transport severity and pull delivery contract", "3.")

    assert _WINDOW in clause, f"D70 clause 3 omits the window: {clause}"
    assert _PROVENANCE in clause, f"D70 clause 3 omits the window provenance: {clause}"


def test_ac_comms_02_pins_the_window_and_marks_its_unexercised_escalation() -> None:
    row = _spec_acceptance_row("AC-COMMS-02")
    manifest_row = _manifest_criterion("AC-COMMS-02")

    assert "15-minute" in row, f"AC-COMMS-02 omits the declared window: {row}"
    assert manifest_row["owner"] == "ct-i1-038"
    assert manifest_row["disposition"] == "applicable"
    assert "15-minute" in manifest_row["reason"]
    assert "escalation observation is unexercised" in manifest_row["reason"], (
        "the manifest row claims escalation evidence this candidate does not carry"
    )


def _spec_section(heading: str) -> str:
    spec = (ROOT / "docs/internal/SPEC.md").read_text(encoding="utf-8")
    start = spec.index(heading)
    return spec[start : spec.index("\n### ", start + len(heading))]


def _decision_clause(heading: str, number: str) -> str:
    decisions = (ROOT / "docs/internal/DECISIONS.md").read_text(encoding="utf-8")
    start = decisions.index(heading)
    entry_end = decisions.find("\n## ", start + len(heading))
    entry = decisions[start : entry_end if entry_end != -1 else len(decisions)]
    clause_start = entry.index(f"\n{number} ")
    clause_end = entry.find(f"\n{int(number.rstrip('.')) + 1}. ", clause_start)
    return re.sub(r"\s+", " ", entry[clause_start : clause_end if clause_end != -1 else len(entry)])


def _spec_acceptance_row(code: str) -> str:
    spec = (ROOT / "docs/internal/SPEC.md").read_text(encoding="utf-8")
    rows = [line for line in spec.splitlines() if f"</a>{code} |" in line]
    assert len(rows) == 1, f"SPEC declares {code} {len(rows)} times"
    return rows[0]


def _manifest_criterion(code: str) -> dict[str, str]:
    manifest = json.loads((ROOT / _MANIFEST).read_text(encoding="utf-8"))
    rows = [
        cast(dict[str, str], row)
        for row in cast(list[object], manifest["criteria"])
        if cast(dict[str, str], row)["criterion_key"] == code
    ]
    assert len(rows) == 1, f"the evidence manifest declares {code} {len(rows)} times"
    return rows[0]
