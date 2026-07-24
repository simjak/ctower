"""Exact corrupt-ciphertext disposition under one locked spool session."""

from __future__ import annotations

import re
from typing import Literal

from ctowerctl.spool._crypto import RecordType
from ctowerctl.spool._identity import same_binding
from ctowerctl.spool._models import CorruptDisposition
from ctowerctl.spool._recovery import CorruptRecord, Session, utc_text
from ctowerctl.spool._redaction import SpoolEntry, discarded_entry, reason_digest

__all__ = [
    "CorruptDispositionError",
    "dispose_corrupt",
    "require_no_artifact_digest",
]


class CorruptDispositionError(ValueError):
    """An operator disposition does not bind the active exact artifact."""


def dispose_corrupt(
    session: Session,
    corrupt: CorruptRecord,
    action: Literal["retry", "discard"],
    reason: str,
    artifact_digest: str | None,
) -> SpoolEntry:
    """Append an authenticated disposition without removing corrupt evidence."""

    if action != "discard":
        raise CorruptDispositionError("corrupt ciphertext can only be explicitly discarded")
    if artifact_digest is None or re.fullmatch(r"[0-9a-f]{64}", artifact_digest) is None:
        raise CorruptDispositionError(
            "corrupt disposition requires its exact inventory artifact digest"
        )
    if not same_binding(artifact_digest, corrupt.artifact_digest):
        raise CorruptDispositionError(
            "corrupt artifact changed or the digest targets another entry"
        )
    session.verify_corrupt_artifact(corrupt)
    disposition = CorruptDisposition(
        schema_version=1,
        command_sequence=corrupt.stored.sequence,
        command_hash=corrupt.expected_record_hash,
        command_predecessor_hash=corrupt.expected_predecessor_hash,
        artifact_digest=corrupt.artifact_digest,
        artifact_bytes=corrupt.stored.size,
        action="discard",
        reason_digest=reason_digest(reason),
        recorded_at=utc_text(),
    )
    session.append(RecordType.CORRUPT_DISPOSITION, "quarantine", disposition)
    return discarded_entry(corrupt.stored.sequence)


def require_no_artifact_digest(artifact_digest: str | None) -> None:
    """Reject corrupt-only evidence on a normal command disposition."""

    if artifact_digest is not None:
        raise CorruptDispositionError("artifact digest applies only to corrupt quarantine")
