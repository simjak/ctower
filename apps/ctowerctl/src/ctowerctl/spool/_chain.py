"""Authenticated spool-chain validation and explicit tombstone bridges."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pydantic import BaseModel, ValidationError

from ctowerctl.spool._crypto import GENESIS_HASH, OpenedRecord
from ctowerctl.spool._models import (
    CompactionAnchor,
    CorruptDisposition,
    Disposition,
    Head,
)
from ctowerctl.spool._redaction import canonical_json
from ctowerctl.spool._store import StoredFile

__all__ = [
    "ChainValidation",
    "CorruptRecord",
    "RecoveredRecord",
    "validate_record_chain",
]


class ChainError(RuntimeError):
    """An authenticated sequence/hash relationship cannot be proven."""

    def __init__(self, message: str, *, code: str = "chain_integrity") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RecoveredRecord:
    stored: StoredFile
    opened: OpenedRecord


@dataclass(frozen=True, slots=True)
class CorruptRecord:
    """Opaque exact ciphertext evidence; plaintext and unauthenticated header are unused."""

    stored: StoredFile
    artifact_digest: str
    expected_record_hash: str = ""
    expected_predecessor_hash: str = ""


@dataclass(frozen=True, slots=True)
class ChainValidation:
    logical_hashes: dict[int, str]
    active_corrupt: tuple[CorruptRecord, ...]


type _ChainRecord = RecoveredRecord | CorruptRecord


def validate_record_chain(
    records: list[RecoveredRecord],
    corrupt: list[CorruptRecord],
    head: Head,
) -> ChainValidation:
    """Validate all present records and authenticated disposition bridges."""

    ordered: list[_ChainRecord] = sorted(
        [*records, *corrupt],
        key=lambda item: item.stored.sequence,
    )
    if not ordered:
        return ChainValidation(logical_hashes={}, active_corrupt=())
    discarded = _discarded_tombstones(records)
    corrupt_dispositions = _corrupt_dispositions(records)
    corrupt_sequences = {item.stored.sequence for item in corrupt}
    if not set(corrupt_dispositions).issubset(corrupt_sequences):
        raise ChainError("corrupt disposition has no exact artifact")
    expected_sequence, predecessor = _chain_start(ordered[0])
    logical_hashes: dict[int, str] = {}
    active: list[CorruptRecord] = []
    for index, item in enumerate(ordered):
        while item.stored.sequence > expected_sequence:
            predecessor = _bridge_discarded(
                expected_sequence,
                predecessor,
                discarded,
            )
            logical_hashes[expected_sequence] = predecessor
            expected_sequence += 1
        if item.stored.sequence != expected_sequence:
            raise ChainError("durable record sequence is duplicated or rewound")
        if isinstance(item, CorruptRecord):
            expected_hash = _expected_corrupt_hash(item, index, ordered, head)
            disposition = corrupt_dispositions.get(item.stored.sequence)
            enriched = replace(
                item,
                expected_record_hash=expected_hash,
                expected_predecessor_hash=predecessor,
            )
            if disposition is None:
                active.append(enriched)
            else:
                _verify_corrupt_disposition(enriched, disposition)
            predecessor = expected_hash
        else:
            if item.opened.header.predecessor_hash != predecessor:
                raise ChainError("durable record predecessor chain is broken")
            predecessor = item.opened.record_hash
        logical_hashes[expected_sequence] = predecessor
        expected_sequence += 1
    return ChainValidation(
        logical_hashes=logical_hashes,
        active_corrupt=tuple(active),
    )


def _chain_start(first: _ChainRecord) -> tuple[int, str]:
    if first.stored.sequence == 1:
        return 1, GENESIS_HASH
    if not isinstance(first, RecoveredRecord):
        return 1, GENESIS_HASH
    if first.opened.header.record_type != "anchor":
        return 1, GENESIS_HASH
    anchor = _payload(first, CompactionAnchor)
    if anchor.covered_from != 1 or anchor.covered_through != first.stored.sequence - 1:
        raise ChainError("compaction anchor does not cover the missing prefix")
    return first.stored.sequence, anchor.terminal_hash


def _discarded_tombstones(records: list[RecoveredRecord]) -> dict[int, Disposition]:
    discarded: dict[int, Disposition] = {}
    for record in records:
        if record.opened.header.record_type != "disposition":
            continue
        disposition = _payload(record, Disposition)
        if disposition.action != "discard":
            continue
        if disposition.command_predecessor_hash is None:
            raise ChainError(
                "legacy discard cannot authenticate its predecessor relationship",
                code="format_incompatible",
            )
        if disposition.command_sequence in discarded:
            raise ChainError("multiple discard tombstones target one sequence")
        discarded[disposition.command_sequence] = disposition
    return discarded


def _corrupt_dispositions(
    records: list[RecoveredRecord],
) -> dict[int, CorruptDisposition]:
    dispositions: dict[int, CorruptDisposition] = {}
    for record in records:
        if record.opened.header.record_type != "corrupt_disposition":
            continue
        disposition = _payload(record, CorruptDisposition)
        if disposition.command_sequence in dispositions:
            raise ChainError("multiple corrupt dispositions target one sequence")
        dispositions[disposition.command_sequence] = disposition
    return dispositions


def _bridge_discarded(
    sequence: int,
    predecessor: str,
    discarded: dict[int, Disposition],
) -> str:
    disposition = discarded.get(sequence)
    if disposition is None or disposition.command_predecessor_hash != predecessor:
        raise ChainError("durable record sequence contains an unexplained gap")
    return disposition.command_hash


def _expected_corrupt_hash(
    corrupt: CorruptRecord,
    index: int,
    ordered: list[_ChainRecord],
    head: Head,
) -> str:
    next_index = index + 1
    if next_index < len(ordered):
        successor = ordered[next_index]
        if successor.stored.sequence == corrupt.stored.sequence + 1 and isinstance(
            successor, RecoveredRecord
        ):
            return successor.opened.header.predecessor_hash
    if head.sequence == corrupt.stored.sequence:
        return head.record_hash
    raise ChainError("corrupt record hash has no authenticated successor or head")


def _verify_corrupt_disposition(
    corrupt: CorruptRecord,
    disposition: CorruptDisposition,
) -> None:
    if (
        disposition.command_hash != corrupt.expected_record_hash
        or disposition.command_predecessor_hash != corrupt.expected_predecessor_hash
        or disposition.artifact_digest != corrupt.artifact_digest
        or disposition.artifact_bytes != corrupt.stored.size
    ):
        raise ChainError("corrupt disposition does not bind the exact artifact and chain")


def _payload[Payload: BaseModel](
    record: RecoveredRecord,
    model: type[Payload],
) -> Payload:
    try:
        return model.model_validate_json(canonical_json(record.opened.payload), strict=True)
    except ValidationError as error:
        raise ChainError("durable record payload schema is unknown or invalid") from error
