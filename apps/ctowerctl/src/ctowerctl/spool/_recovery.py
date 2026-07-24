"""Private authenticated head, chain, and deterministic crash recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from ctowerctl.spool import _keyring
from ctowerctl.spool._crypto import (
    FORMAT_VERSION,
    GENESIS_HASH,
    CryptoError,
    KeySet,
    OpenedRecord,
    RecordType,
    derive_keys,
    inspect_signed_body,
    key_id,
    open_record,
    seal_record,
    sign_document,
    verify_signed_document,
)
from ctowerctl.spool._models import (
    AcceptedReceipt,
    CommandEnvelope,
    CompactionAnchor,
    Disposition,
    Head,
    Metadata,
    QuarantineReceipt,
)
from ctowerctl.spool._redaction import JsonObject, canonical_json, digest_json
from ctowerctl.spool._store import DirectoryName, LockedStore, StorageError, StoredFile

__all__ = [
    "AcceptedReceipt",
    "CommandEnvelope",
    "CompactionAnchor",
    "Disposition",
    "QuarantineReceipt",
    "RecoveredRecord",
    "RecoveryError",
    "Session",
    "command_payload",
    "parse_utc",
    "recover_session",
    "utc_text",
]


class RecoveryError(RuntimeError):
    """The spool cannot safely infer one durable state."""


@dataclass(frozen=True, slots=True)
class RecoveredRecord:
    stored: StoredFile
    opened: OpenedRecord


class Session:
    """One fully verified, flock-protected mutable spool session."""

    def __init__(
        self,
        store: LockedStore,
        metadata: Metadata,
        head: Head,
        keys: KeySet,
        records: list[RecoveredRecord],
        *,
        maximum_record_bytes: int,
        torn_evidence: int,
    ) -> None:
        self.store = store
        self.metadata = metadata
        self.head = head
        self.keys = keys
        self.records = records
        self.maximum_record_bytes = maximum_record_bytes
        self.torn_evidence = torn_evidence

    def append(
        self,
        record_type: RecordType,
        directory: DirectoryName,
        payload: BaseModel,
    ) -> RecoveredRecord:
        sequence = self.head.sequence + 1
        body = cast(JsonObject, payload.model_dump(mode="json"))
        sealed = seal_record(
            record_type,
            sequence,
            self.head.record_hash,
            self.metadata.key_id,
            body,
            keys=self.keys,
        )
        if len(sealed.data) > self.maximum_record_bytes:
            raise StorageError("encrypted durable record exceeds bounded size")
        next_head = Head(
            format_version=FORMAT_VERSION,
            sequence=sequence,
            record_hash=sealed.record_hash,
        )
        head_data = sign_document(
            cast(JsonObject, next_head.model_dump(mode="json")),
            self.keys.metadata_mac,
        )
        self.store.append_record(directory, sealed.filename, sealed.data, head_data)
        stored = StoredFile(
            directory=directory,
            name=sealed.filename,
            sequence=sequence,
            kind=record_type.value,
            size=len(sealed.data),
        )
        recovered = RecoveredRecord(
            stored=stored,
            opened=OpenedRecord(
                header=sealed.header,
                payload=body,
                record_hash=sealed.record_hash,
            ),
        )
        self.records.append(recovered)
        self.head = next_head
        return recovered

    def move(self, record: RecoveredRecord, destination: DirectoryName) -> RecoveredRecord:
        moved = RecoveredRecord(
            stored=self.store.move(record.stored, destination),
            opened=record.opened,
        )
        self.records[self.records.index(record)] = moved
        return moved

    def remove(self, record: RecoveredRecord) -> None:
        self.store.remove(record.stored)
        self.records.remove(record)

    def commands(self) -> tuple[RecoveredRecord, ...]:
        return tuple(item for item in self.records if item.opened.header.record_type == "command")

    def command(self, sequence: int) -> RecoveredRecord | None:
        return next((item for item in self.commands() if item.stored.sequence == sequence), None)


def recover_session(
    store: LockedStore,
    origin_digest: str,
    *,
    maximum_record_bytes: int,
    repair: bool = True,
) -> Session:
    """Initialize or fully authenticate one spool and resolve completed transitions."""

    metadata, keys = _load_or_create_metadata(store, origin_digest)
    head = _load_or_create_head(store, keys)
    temporary_count = store.recover_temps() if repair else store.temporary_count()
    recovered = _open_records(
        store,
        metadata,
        keys,
        maximum_record_bytes,
        repair=repair,
    )
    recovered = _recover_compaction(store, recovered, repair=repair)
    head = _validate_chain(store, keys, head, recovered, repair=repair)
    session = Session(
        store,
        metadata,
        head,
        keys,
        recovered,
        maximum_record_bytes=maximum_record_bytes,
        torn_evidence=store.quarantine_evidence_count() + (0 if repair else temporary_count),
    )
    _recover_transitions(session, repair=repair)
    return session


def command_payload(record: RecoveredRecord) -> CommandEnvelope:
    """Validate the encrypted command body after record authentication."""

    try:
        payload = CommandEnvelope.model_validate(record.opened.payload, strict=True)
        UUID(payload.command_id)
        _parse_utc(payload.enqueued_at)
        _parse_utc(payload.expires_at)
    except (ValidationError, ValueError) as error:
        raise RecoveryError("command payload schema is unknown or invalid") from error
    if payload.origin_digest == GENESIS_HASH:
        raise RecoveryError("command payload origin cannot be empty")
    return payload


def utc_text(value: datetime | None = None) -> str:
    """Canonical UTC timestamp for encrypted payloads."""

    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("spool timestamps must be timezone-aware")
    return timestamp.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    """Parse one canonical encrypted UTC timestamp."""

    return _parse_utc(value)


def _load_or_create_metadata(store: LockedStore, origin_digest: str) -> tuple[Metadata, KeySet]:
    if not store.exists_control("metadata"):
        if store.exists_control("head") or store.scan_records():
            raise RecoveryError("spool metadata is missing while durable state exists")
        spool_uuid = uuid4()
        master_key = _keyring.create_master_key(spool_uuid)
        metadata = Metadata(
            format_version=FORMAT_VERSION,
            spool_uuid=str(spool_uuid),
            key_id=key_id(master_key),
            origin_digest=origin_digest,
        )
        keys = derive_keys(master_key, spool_uuid)
        store.write_control(
            "metadata",
            sign_document(
                cast(JsonObject, metadata.model_dump(mode="json")),
                keys.metadata_mac,
            ),
        )
        return metadata, keys
    data = store.read_control("metadata")
    try:
        unverified = Metadata.model_validate(inspect_signed_body(data), strict=True)
        spool_uuid = UUID(unverified.spool_uuid)
        master_key = _keyring.load_master_key(spool_uuid)
        if key_id(master_key) != unverified.key_id:
            raise RecoveryError("keyring key identity does not match spool metadata")
        keys = derive_keys(master_key, spool_uuid)
        metadata = Metadata.model_validate(
            verify_signed_document(data, keys.metadata_mac),
            strict=True,
        )
    except (CryptoError, ValidationError, ValueError) as error:
        raise RecoveryError("spool metadata is invalid or unauthenticated") from error
    if metadata.origin_digest != origin_digest:
        raise RecoveryError("spool metadata belongs to another API origin")
    return metadata, keys


def _load_or_create_head(store: LockedStore, keys: KeySet) -> Head:
    if not store.exists_control("head"):
        if store.scan_records():
            raise RecoveryError("spool head is missing while records exist")
        head = Head(format_version=FORMAT_VERSION, sequence=0, record_hash=GENESIS_HASH)
        store.write_control(
            "head",
            sign_document(cast(JsonObject, head.model_dump(mode="json")), keys.metadata_mac),
        )
        return head
    try:
        return Head.model_validate(
            verify_signed_document(store.read_control("head"), keys.metadata_mac),
            strict=True,
        )
    except (CryptoError, ValidationError) as error:
        raise RecoveryError("spool head is invalid or unauthenticated") from error


def _open_records(
    store: LockedStore,
    metadata: Metadata,
    keys: KeySet,
    maximum_record_bytes: int,
    *,
    repair: bool,
) -> list[RecoveredRecord]:
    recovered: list[RecoveredRecord] = []
    for stored in store.scan_records():
        try:
            opened = open_record(
                store.read_file(stored, maximum=maximum_record_bytes),
                keys,
                metadata.key_id,
            )
        except (CryptoError, StorageError) as error:
            if repair and stored.directory == "pending":
                store.move(stored, "quarantine")
            raise RecoveryError("spool record is corrupt; ordered replay is blocked") from error
        if opened.header.sequence != stored.sequence or opened.header.record_type != stored.kind:
            raise RecoveryError("record filename does not match its authenticated header")
        _validate_location(stored)
        recovered.append(RecoveredRecord(stored=stored, opened=opened))
    return recovered


def _validate_chain(
    store: LockedStore,
    keys: KeySet,
    head: Head,
    records: list[RecoveredRecord],
    *,
    repair: bool,
) -> Head:
    if not records:
        if head.sequence != 0 or head.record_hash != GENESIS_HASH:
            raise RecoveryError("spool head names a missing durable record")
        return head
    _validate_record_chain(records)
    if head.sequence > records[-1].stored.sequence:
        raise RecoveryError("spool head names a missing durable record")
    if not _head_matches_record(head, records):
        raise RecoveryError("spool head does not match its durable record")
    if head.sequence == records[-1].stored.sequence:
        return head
    if not repair:
        raise RecoveryError("spool head recovery is required")
    next_head = Head(
        format_version=FORMAT_VERSION,
        sequence=records[-1].stored.sequence,
        record_hash=records[-1].opened.record_hash,
    )
    store.write_control(
        "head",
        sign_document(cast(JsonObject, next_head.model_dump(mode="json")), keys.metadata_mac),
    )
    return next_head


def _recover_compaction(
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


def _validate_record_chain(records: list[RecoveredRecord]) -> None:
    first = records[0]
    expected_sequence, predecessor = _chain_start(first)
    discarded = _discarded_hashes(records)
    for record in records:
        if record.stored.sequence != expected_sequence:
            expected_sequence, predecessor = _bridge_discarded_command(
                expected_sequence,
                predecessor,
                record,
                discarded,
            )
        if record.opened.header.predecessor_hash != predecessor:
            raise RecoveryError("durable record predecessor chain is broken")
        predecessor = record.opened.record_hash
        expected_sequence += 1


def _chain_start(first: RecoveredRecord) -> tuple[int, str]:
    if first.stored.sequence == 1:
        return 1, GENESIS_HASH
    if first.opened.header.record_type != "anchor":
        return 1, GENESIS_HASH
    anchor = _payload(first, CompactionAnchor)
    if anchor.covered_from != 1 or anchor.covered_through != first.stored.sequence - 1:
        raise RecoveryError("compaction anchor does not cover the missing prefix")
    return first.stored.sequence, anchor.terminal_hash


def _discarded_hashes(records: list[RecoveredRecord]) -> dict[int, str]:
    discarded: dict[int, str] = {}
    for record in records:
        if record.opened.header.record_type != "disposition":
            continue
        disposition = _payload(record, Disposition)
        if disposition.action == "discard":
            discarded[disposition.command_sequence] = disposition.command_hash
    return discarded


def _bridge_discarded_command(
    expected_sequence: int,
    predecessor: str,
    record: RecoveredRecord,
    discarded: dict[int, str],
) -> tuple[int, str]:
    del predecessor
    discarded_hash = discarded.get(expected_sequence)
    if (
        record.stored.sequence != expected_sequence + 1
        or discarded_hash is None
        or record.opened.header.predecessor_hash != discarded_hash
    ):
        raise RecoveryError("durable record sequence contains an unexplained gap")
    return record.stored.sequence, discarded_hash


def _head_matches_record(head: Head, records: list[RecoveredRecord]) -> bool:
    if head.sequence == 0:
        return head.record_hash == GENESIS_HASH
    matching = next((item for item in records if item.stored.sequence == head.sequence), None)
    return matching is not None and matching.opened.record_hash == head.record_hash


def _recover_transitions(session: Session, *, repair: bool) -> None:
    for command in tuple(session.commands()):
        actions = _actions_for(session.records, command)
        state = "pending"
        for action in actions:
            state = _next_state(state, action)
        if state == "discarded":
            if not repair:
                raise RecoveryError("discard recovery is required")
            session.remove(command)
        elif state != command.stored.directory:
            if not repair:
                raise RecoveryError("durable transition recovery is required")
            session.move(command, cast(DirectoryName, state))


def _actions_for(
    records: list[RecoveredRecord],
    command: RecoveredRecord,
) -> tuple[str, ...]:
    actions: list[str] = []
    for record in records:
        action = _action_for(record, command)
        if action is not None:
            actions.append(action)
    return tuple(actions)


def _action_for(record: RecoveredRecord, command: RecoveredRecord) -> str | None:
    record_type = record.opened.header.record_type
    if record_type == "accepted_receipt":
        accepted = _payload(record, AcceptedReceipt)
        if accepted.command_sequence == command.stored.sequence:
            _verify_command_binding(command, accepted.command_hash)
            if accepted.command_id != command_payload(command).command_id:
                raise RecoveryError("accepted receipt binds a different command ID")
            if accepted.response_digest != digest_json({"response": accepted.response}):
                raise RecoveryError("accepted receipt response digest does not match")
            return "accepted"
    elif record_type == "quarantine_receipt":
        quarantined = _payload(record, QuarantineReceipt)
        if quarantined.command_sequence == command.stored.sequence:
            _verify_command_binding(command, quarantined.command_hash)
            return "quarantined"
    elif record_type == "disposition":
        disposition = _payload(record, Disposition)
        if disposition.command_sequence == command.stored.sequence:
            _verify_command_binding(command, disposition.command_hash)
            return disposition.action
    return None


def _next_state(state: str, action: str) -> str:
    transitions = {
        ("pending", "accepted"): "accepted",
        ("pending", "quarantined"): "quarantine",
        ("quarantine", "retry"): "pending",
        ("quarantine", "discard"): "discarded",
    }
    try:
        return transitions[(state, action)]
    except KeyError as error:
        raise RecoveryError("durable transition history is invalid") from error


def _verify_command_binding(command: RecoveredRecord, command_hash: str) -> None:
    if command.opened.record_hash != command_hash:
        raise RecoveryError("receipt/disposition binds a different command record")


def _validate_location(stored: StoredFile) -> None:
    expected: dict[str, frozenset[DirectoryName]] = {
        "command": frozenset({"pending", "accepted", "quarantine"}),
        "accepted_receipt": frozenset({"accepted"}),
        "quarantine_receipt": frozenset({"quarantine"}),
        "disposition": frozenset({"quarantine"}),
        "anchor": frozenset({"anchors"}),
    }
    if stored.directory not in expected[stored.kind]:
        raise RecoveryError("durable record is in the wrong state directory")


def _payload[Payload: BaseModel](
    record: RecoveredRecord,
    model: type[Payload],
) -> Payload:
    try:
        return model.model_validate_json(canonical_json(record.opened.payload), strict=True)
    except ValidationError as error:
        raise RecoveryError("durable record payload schema is unknown or invalid") from error


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("timestamp is not canonical UTC")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed.astimezone(UTC)
