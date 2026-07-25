"""Private accepted-archive retention and compaction policy."""

from __future__ import annotations

from datetime import datetime, timedelta

from ctowerctl.spool._crypto import RecordType
from ctowerctl.spool._recovery import (
    AcceptedReceipt,
    CompactionAnchor,
    RecoveredRecord,
    Session,
    parse_utc,
    utc_text,
)
from ctowerctl.spool._redaction import canonical_json


def compact_accepted(session: Session, *, now: datetime, horizon: timedelta) -> int:
    """Compact only a wholly terminal old chain, preserving one authenticated anchor."""

    if session.torn_evidence or not session.records:
        return 0
    if any(command.stored.directory != "accepted" for command in session.commands()):
        return 0
    receipts = _accepted_receipts(session.records)
    if not receipts or any(now - parse_utc(receipt.accepted_at) < horizon for receipt in receipts):
        return 0
    if any(
        record.opened.header.record_type not in {"command", "accepted_receipt"}
        for record in session.records
    ):
        return 0
    covered = tuple(session.records)
    terminal = covered[-1]
    anchor = CompactionAnchor(
        schema_version=1,
        covered_from=covered[0].stored.sequence,
        covered_through=terminal.stored.sequence,
        terminal_hash=terminal.opened.record_hash,
        created_at=utc_text(now),
    )
    session.append(RecordType.ANCHOR, "anchors", anchor)
    for record in covered:
        session.remove(record)
    return len(covered)


def _accepted_receipts(records: list[RecoveredRecord]) -> tuple[AcceptedReceipt, ...]:
    return tuple(
        AcceptedReceipt.model_validate_json(
            canonical_json(record.opened.payload),
            strict=True,
        )
        for record in records
        if record.opened.header.record_type == "accepted_receipt"
    )
