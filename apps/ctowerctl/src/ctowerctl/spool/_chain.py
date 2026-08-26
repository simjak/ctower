"""Authenticated spool-chain validation and explicit tombstone bridges."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ctowerctl.spool import _crypto
from ctowerctl.spool._crypto import GENESIS_HASH, OpenedRecord
from ctowerctl.spool._models import (
    CompactionAnchor,
    CorruptDisposition,
    Disposition,
    Head,
)
from ctowerctl.spool._redaction import JsonObject, canonical_json, digest_json
from ctowerctl.spool._store import LockedStore, StoredFile

__all__ = [
    "ChainValidation",
    "CorruptRecord",
    "RecoveredRecord",
    "validate_record_chain",
]


class RecoveryError(RuntimeError):
    def __init__(self, message: str, *, code: str = "chain_integrity") -> None:
        super().__init__(message)
        self.code = code


class ChainError(RecoveryError):
    """An authenticated sequence/hash relationship cannot be proven."""


class RecoveryCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    format_version: Literal[1]
    sequence: Annotated[int, Field(ge=0)]
    record_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    state_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


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


def load_recovery_cursor(
    store: LockedStore,
    keys: _crypto.KeySet,
    head: Head,
    records: Sequence[RecoveredRecord],
    logical_hashes: dict[int, str],
) -> RecoveryCursor | None:
    if not store.exists_control("recovery"):
        return None
    try:
        cursor = RecoveryCursor.model_validate(
            _crypto.verify_signed_document(store.read_control("recovery"), keys.metadata_mac),
            strict=True,
        )
    except (_crypto.CryptoError, ValidationError) as error:
        raise RecoveryError("spool recovery cursor is invalid or unauthenticated") from error
    if cursor.sequence > head.sequence:
        raise RecoveryError("spool recovery cursor is ahead of the durable head")
    expected_hash = GENESIS_HASH if cursor.sequence == 0 else logical_hashes.get(cursor.sequence)
    if expected_hash is None:
        anchor = next((item for item in records if item.opened.header.record_type == "anchor"), None)
        if anchor is not None and _payload(anchor, CompactionAnchor).covered_through == cursor.sequence:
            expected_hash = _payload(anchor, CompactionAnchor).terminal_hash
    if expected_hash != cursor.record_hash:
        raise RecoveryError("spool recovery cursor does not match the durable chain")
    return cursor


def load_or_create_head(store: LockedStore, keys: _crypto.KeySet) -> Head:
    if not store.exists_control("head"):
        if store.scan_records():
            raise RecoveryError("spool head is missing while records exist")
        head = Head(format_version=_crypto.FORMAT_VERSION, sequence=0, record_hash=GENESIS_HASH)
        store.write_control(
            "head",
            _crypto.sign_document(
                cast(JsonObject, head.model_dump(mode="json")), keys.metadata_mac
            ),
        )
        return head
    try:
        return Head.model_validate(
            _crypto.verify_signed_document(store.read_control("head"), keys.metadata_mac),
            strict=True,
        )
    except (_crypto.CryptoError, ValidationError) as error:
        raise RecoveryError("spool head is invalid or unauthenticated") from error


def state_digest(records: Sequence[RecoveredRecord]) -> str:
    return digest_json(
        {
            "commands": [
                {"sequence": record.stored.sequence, "state": record.stored.directory}
                for record in records
                if record.opened.header.record_type == "command"
            ]
        }
    )


def recover_compaction(
    store: LockedStore,
    records: list[RecoveredRecord],
    *,
    repair: bool,
) -> list[RecoveredRecord]:
    anchors = tuple(record for record in records if record.opened.header.record_type == "anchor")
    if not anchors:
        return records
    if len(anchors) != 1:
        raise RecoveryError("multiple compaction anchors are ambiguous")
    anchor_record = anchors[0]
    anchor = _payload(anchor_record, CompactionAnchor)
    if (
        anchor.covered_from != 1
        or anchor_record.stored.sequence != anchor.covered_through + 1
        or anchor_record.opened.header.predecessor_hash != anchor.terminal_hash
    ):
        raise RecoveryError("compaction anchor range or predecessor is invalid")
    covered = [
        record
        for record in records
        if anchor.covered_from <= record.stored.sequence <= anchor.covered_through
    ]
    if covered and not repair:
        raise RecoveryError("compaction deletion recovery is required")
    for record in covered:
        store.remove(record.stored)
        records.remove(record)
    return records


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
