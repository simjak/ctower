"""The rehearsal report and JSON evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tools.development_runtime._rehearsal_live import LiveProperties
from tools.development_runtime._rehearsal_scenarios import RehearsalResult
from tools.development_runtime._rehearsal_vocabulary import OFFLINE_FIXTURE_ENDPOINT

__all__ = ["emit_json", "render"]

# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def render(live: LiveProperties, results: list[RehearsalResult], target: str, base: str) -> None:
    print(f"\nCTOWER UPGRADE REHEARSAL   target {target}   base {base}")
    print(f"  run at {datetime.now(UTC).isoformat(timespec='seconds')}\n")
    print(f"LIVE PROBE (read-only, {live.endpoint}, in_recovery={live.in_recovery})")
    print(f"  server            {live.server_version}")
    print(f"  ledger            {live.ledger_rows} rows, terminal {live.terminal_migration}")
    print(f"  schema digest     {live.schema_fingerprint}")
    print(
        f"  ledger attests    {live.ledger_attestation}"
        f"{'   *** DRIFT ***' if live.attestation_drift else '   (matches)'}"
    )
    print(f"  non-empty tables  {len(live.non_empty_tables)} of {len(live.table_counts)}")
    print(
        f"  events            {live.table_counts.get('events', 0)} "
        f"({', '.join(f'{k}={v}' for k, v in sorted(live.event_kinds.items()))})"
    )
    rejected = ", ".join(live.rejected_checks) or "none"
    print(f"  live rejects      {rejected}")
    for code, detail in live.blockers:
        print(f"  BLOCKER           {code}: {detail}")
    for result in results:
        _render_scenario(result, live)
    print()


def _render_scenario(result: RehearsalResult, live: LiveProperties) -> None:
    verdict = "PASS" if result.passed else ("BLOCKED (live-state)" if result.blocked else "FAIL")
    print(f"\nSCENARIO {result.name}   {verdict}")
    for note in result.notes:
        print(f"  note              {note}")
    print(f"  ledger before     {result.ledger_before[0]} rows, terminal {result.ledger_before[1]}")
    print(f"  ledger after      {result.ledger_after[0]} rows, terminal {result.ledger_after[1]}")
    print(f"  schema before     {result.schema_digest_before}")
    print(f"  schema after      {result.schema_digest_after}")
    fixture_suffix = (
        "(offline fixture mode)"
        if live.endpoint == OFFLINE_FIXTURE_ENDPOINT
        else "(live vector matched)"
    )
    print(f"  fixture rejects   {', '.join(result.fixture_vector) or 'none'}   {fixture_suffix}")
    print(f"  fixture history   {_counts_line(result.counts_before)}")
    print(f"  after upgrade     {_counts_line(result.counts_after)}")
    uncovered = [t for t in live.non_empty_tables if not result.counts_before.get(t)]
    if uncovered:
        print(
            f"  live tables the fixture does NOT populate ({len(uncovered)}): {', '.join(uncovered)}"
        )
    print(f"  result            {result.reason}")
    if result.first_failing_precondition:
        print(f"  FIRST FAILING PRECONDITION BY NAME: {result.first_failing_precondition}")


def _counts_line(counts: dict[str, int]) -> str:
    populated = {name: value for name, value in counts.items() if value}
    head = ", ".join(f"{name}={value}" for name, value in sorted(populated.items())[:8])
    return f"{len(populated)} non-empty tables: {head}…"


def emit_json(
    path: Path, live: LiveProperties, results: list[RehearsalResult], meta: dict[str, str]
) -> None:
    payload = {
        "schema": "ctower.upgrade-rehearsal/v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **meta,
        "live": {
            "endpoint": live.endpoint,
            "in_recovery": live.in_recovery,
            "ledger_rows": live.ledger_rows,
            "terminal_migration": live.terminal_migration,
            "schema_fingerprint": live.schema_fingerprint,
            "ledger_attestation": live.ledger_attestation,
            "attestation_drift": live.attestation_drift,
            "rejected_checks": list(live.rejected_checks),
            "event_kinds": live.event_kinds,
            "link_subject_kinds": live.link_subject_kinds,
            "non_empty_tables": list(live.non_empty_tables),
            "blockers": [{"code": c, "detail": d} for c, d in live.blockers],
        },
        "scenarios": [
            {
                "name": r.name,
                "passed": r.passed,
                "blocked_by_live_state": r.blocked,
                "code": r.code,
                "reason": r.reason,
                "first_failing_precondition": r.first_failing_precondition,
                "ledger_before": list(r.ledger_before),
                "ledger_after": list(r.ledger_after),
                "schema_digest_before": r.schema_digest_before,
                "schema_digest_after": r.schema_digest_after,
                "fixture_rejects": list(r.fixture_vector),
                "counts_before": {k: v for k, v in r.counts_before.items() if v},
                "counts_after": {k: v for k, v in r.counts_after.items() if v},
                "notes": r.notes,
            }
            for r in results
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


