"""Private authenticated head, chain, and deterministic crash recovery."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from ctowerctl.spool import _keyring
from ctowerctl.spool._chain import (
    ChainError,
    CorruptRecord,
    RecoveredRecord,
    validate_record_chain,
)
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
    CorruptDisposition,
    Disposition,
    Head,
    Metadata,
    QuarantineReceipt,
    RecoveryCursor,
)
from ctowerctl.spool._redaction import JsonObject, canonical_json, digest_json
from ctowerctl.spool._store import DirectoryName, LockedStore, StorageError, StoredFile

__all__ = [
    "AcceptedReceipt",
    "CommandEnvelope",
    "CompactionAnchor",
    "CorruptDisposition",
    "CorruptRecord",
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

    def __init__(self, message: str, *, code: str = "chain_integrity") -> None:
        super().__init__(message)
        self.code = code


class Session:
    """One fully verified, flock-protected mutable spool session."""

    def __init__(
        self,
        store: LockedStore,
        metadata: Metadata,
        head: Head,
        keys: KeySet,
        records: list[RecoveredRecord],
        corrupt_records: tuple[CorruptRecord, ...],
        recovery_cursor: RecoveryCursor | None,
        *,
        maximum_record_bytes: int,
        torn_evidence: int,
    ) -> None:
        self.store = store
        self.metadata = metadata
        self.head = head
        self.keys = keys
        self.records = records
        self.corrupt_records = corrupt_records
        self.recovery_cursor = recovery_cursor
        self._commands_by_id: dict[str, RecoveredRecord] | None = None
        self._quarantine_receipts: dict[int, RecoveredRecord] | None = None
        self.maximum_record_bytes = maximum_record_bytes
        self.torn_evidence = torn_evidence

    def append(
        self,
        record_type: RecordType,
        directory: DirectoryName,
        payload: BaseModel,
    ) -> RecoveredRecord:
        if self.corrupt_records and record_type != RecordType.CORRUPT_DISPOSITION:
            raise RecoveryError("corrupt quarantine requires explicit disposition")
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
        self._commands_by_id = None
        self._quarantine_receipts = None
        self.head = next_head
        return recovered

    def move(self, record: RecoveredRecord, destination: DirectoryName) -> RecoveredRecord:
        moved = RecoveredRecord(
            stored=self.store.move(record.stored, destination),
            opened=record.opened,
        )
        self.records[self.records.index(record)] = moved
        self._commands_by_id = None
        self._quarantine_receipts = None
        return moved

    def remove(self, record: RecoveredRecord) -> None:
        self.store.remove(record.stored)
        self.records.remove(record)
        self._commands_by_id = None
        self._quarantine_receipts = None

    def commands(self) -> tuple[RecoveredRecord, ...]:
        return tuple(item for item in self.records if item.opened.header.record_type == "command")

    def command(self, sequence: int) -> RecoveredRecord | None:
        return next((item for item in self.commands() if item.stored.sequence == sequence), None)

    def command_by_id(self, command_id: str) -> RecoveredRecord | None:
        """Return one command from the verified identity index."""

        if self._commands_by_id is None:
            commands: dict[str, RecoveredRecord] = {}
            for record in self.commands():
                value = record.opened.payload.get("command_id")
                if not isinstance(value, str):
                    raise RecoveryError("command payload schema is unknown or invalid")
                if value in commands:
                    raise RecoveryError("multiple durable commands share one command ID")
                commands[value] = record
            self._commands_by_id = commands
        return self._commands_by_id.get(command_id)

    def corrupt_command(self, sequence: int) -> CorruptRecord | None:
        return next(
            (item for item in self.corrupt_records if item.stored.sequence == sequence),
            None,
        )

    def quarantine_receipt(self, command_sequence: int) -> RecoveredRecord | None:
        """Return the latest verified receipt without rescanning history per command."""

        if self._quarantine_receipts is None:
            receipts: dict[int, RecoveredRecord] = {}
            for record in self.records:
                if record.opened.header.record_type != "quarantine_receipt":
                    continue
                sequence = record.opened.payload.get("command_sequence")
                if not isinstance(sequence, int) or isinstance(sequence, bool):
                    raise RecoveryError("durable record payload schema is unknown or invalid")
                receipts[sequence] = record
            self._quarantine_receipts = receipts
        return self._quarantine_receipts.get(command_sequence)

    def verify_corrupt_artifact(self, corrupt: CorruptRecord) -> None:
        data = self.store.read_file(corrupt.stored, maximum=self.maximum_record_bytes)
        if (
            len(data) != corrupt.stored.size
            or hashlib.sha256(data).hexdigest() != corrupt.artifact_digest
        ):
            raise RecoveryError("corrupt artifact changed before disposition")

    def verify_doctor_state(self) -> None:
        """Require evidence-free state for the non-mutating doctor result."""

        if self.torn_evidence:
            raise RecoveryError("torn-write evidence requires explicit disposition")
        if self.corrupt_records:
            raise RecoveryError("corrupt quarantine requires explicit disposition")

    def checkpoint_recovery(self) -> None:
        """Advance the authenticated cursor only after transition moves are durable."""

        cursor = RecoveryCursor(
            format_version=FORMAT_VERSION,
            sequence=self.head.sequence,
            record_hash=self.head.record_hash,
            state_digest=_state_digest(self.records),
        )
        if cursor == self.recovery_cursor:
            return
        self.store.write_control(
            "recovery",
            sign_document(
                cast(JsonObject, cursor.model_dump(mode="json")),
                self.keys.metadata_mac,
            ),
        )
        self.recovery_cursor = cursor


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
    recovered, discovered_corrupt = _open_records(
        store,
        metadata,
        keys,
        maximum_record_bytes,
        repair=repair,
    )
    recovered = _recover_compaction(store, recovered, repair=repair)
    head, active_corrupt, logical_hashes = _validate_chain(
        store,
        keys,
        head,
        recovered,
        discovered_corrupt,
        repair=repair,
    )
    recovery_cursor = _load_recovery_cursor(
        store,
        keys,
        head,
        recovered,
        logical_hashes,
    )
    session = Session(
        store,
        metadata,
        head,
        keys,
        recovered,
        active_corrupt,
        recovery_cursor,
        maximum_record_bytes=maximum_record_bytes,
        torn_evidence=store.quarantine_evidence_count() + (0 if repair else temporary_count),
    )
    if not _cursor_covers_current_state(recovery_cursor, head, recovered):
        _recover_transitions(session, repair=repair)
    if repair:
        session.checkpoint_recovery()
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
) -> tuple[list[RecoveredRecord], list[CorruptRecord]]:
    recovered: list[RecoveredRecord] = []
    corrupt: list[CorruptRecord] = []
    for stored in store.scan_records():
        result = _open_stored_record(
            store,
            stored,
            metadata,
            keys,
            maximum_record_bytes,
            repair=repair,
        )
        if isinstance(result, CorruptRecord):
            corrupt.append(result)
        else:
            recovered.append(result)
    return recovered, corrupt


def _open_stored_record(
    store: LockedStore,
    stored: StoredFile,
    metadata: Metadata,
    keys: KeySet,
    maximum_record_bytes: int,
    *,
    repair: bool,
) -> RecoveredRecord | CorruptRecord:
    try:
        data = store.read_file(stored, maximum=maximum_record_bytes)
    except StorageError as error:
        raise RecoveryError("spool record cannot be read safely") from error
    try:
        opened = open_record(data, keys, metadata.key_id)
    except CryptoError as error:
        return _corrupt_record(store, stored, data, error, repair=repair)
    if opened.header.sequence != stored.sequence or opened.header.record_type != stored.kind:
        raise RecoveryError("record filename does not match its authenticated header")
    _validate_location(stored)
    return RecoveredRecord(stored=stored, opened=opened)


def _corrupt_record(
    store: LockedStore,
    stored: StoredFile,
    data: bytes,
    cause: CryptoError,
    *,
    repair: bool,
) -> CorruptRecord:
    if stored.kind != "command" or stored.directory not in {"pending", "quarantine"}:
        raise RecoveryError("non-command spool record is corrupt; recovery is blocked") from cause
    if repair and stored.directory == "pending":
        stored = store.move(stored, "quarantine")
    return CorruptRecord(
        stored=stored,
        artifact_digest=hashlib.sha256(data).hexdigest(),
    )


def _validate_chain(
    store: LockedStore,
    keys: KeySet,
    head: Head,
    records: list[RecoveredRecord],
    corrupt: list[CorruptRecord],
    *,
    repair: bool,
) -> tuple[Head, tuple[CorruptRecord, ...], dict[int, str]]:
    if not records and not corrupt:
        return _empty_chain(head)
    try:
        validation = validate_record_chain(records, corrupt, head)
    except ChainError as error:
        raise RecoveryError(str(error), code=error.code) from error
    last_sequence = max(
        [item.stored.sequence for item in records] + [item.stored.sequence for item in corrupt]
    )
    head = _recover_head(
        store,
        keys,
        head,
        validation.logical_hashes,
        last_sequence,
        repair=repair,
    )
    return head, validation.active_corrupt, validation.logical_hashes


def _empty_chain(head: Head) -> tuple[Head, tuple[CorruptRecord, ...], dict[int, str]]:
    if head.sequence != 0 or head.record_hash != GENESIS_HASH:
        raise RecoveryError("spool head names a missing durable record")
    return head, (), {}


def _load_recovery_cursor(
    store: LockedStore,
    keys: KeySet,
    head: Head,
    records: list[RecoveredRecord],
    logical_hashes: dict[int, str],
) -> RecoveryCursor | None:
    if not store.exists_control("recovery"):
        return None
    try:
        cursor = RecoveryCursor.model_validate(
            verify_signed_document(store.read_control("recovery"), keys.metadata_mac),
            strict=True,
        )
    except (CryptoError, ValidationError) as error:
        raise RecoveryError("spool recovery cursor is invalid or unauthenticated") from error
    if cursor.sequence > head.sequence:
        raise RecoveryError("spool recovery cursor is ahead of the durable head")
    expected_hash = GENESIS_HASH if cursor.sequence == 0 else logical_hashes.get(cursor.sequence)
    if expected_hash is None:
        expected_hash = _compacted_cursor_hash(records, cursor.sequence)
    if expected_hash != cursor.record_hash:
        raise RecoveryError("spool recovery cursor does not match the durable chain")
    return cursor


def _compacted_cursor_hash(records: list[RecoveredRecord], sequence: int) -> str | None:
    anchor = next(
        (record for record in records if record.opened.header.record_type == "anchor"),
        None,
    )
    if anchor is None:
        return None
    payload = _payload(anchor, CompactionAnchor)
    return payload.terminal_hash if payload.covered_through == sequence else None


def _cursor_covers_current_state(
    cursor: RecoveryCursor | None,
    head: Head,
    records: list[RecoveredRecord],
) -> bool:
    return (
        cursor is not None
        and cursor.sequence == head.sequence
        and cursor.record_hash == head.record_hash
        and cursor.state_digest == _state_digest(records)
    )


def _state_digest(records: list[RecoveredRecord]) -> str:
    return digest_json(
        {
            "commands": [
                {
                    "sequence": record.stored.sequence,
                    "state": record.stored.directory,
                }
                for record in records
                if record.opened.header.record_type == "command"
            ]
        }
    )


def _recover_head(
    store: LockedStore,
    keys: KeySet,
    head: Head,
    logical_hashes: dict[int, str],
    last_sequence: int,
    *,
    repair: bool,
) -> Head:
    if head.sequence > last_sequence:
        raise RecoveryError("spool head names a missing durable record")
    if not _head_matches_record(head, logical_hashes):
        raise RecoveryError("spool head does not match its durable record")
    if head.sequence == last_sequence:
        return head
    if not repair:
        raise RecoveryError("spool head recovery is required")
    next_head = Head(
        format_version=FORMAT_VERSION,
        sequence=last_sequence,
        record_hash=logical_hashes[last_sequence],
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


def _head_matches_record(head: Head, logical_hashes: dict[int, str]) -> bool:
    if head.sequence == 0:
        return head.record_hash == GENESIS_HASH
    return logical_hashes.get(head.sequence) == head.record_hash


def _recover_transitions(session: Session, *, repair: bool) -> None:
    commands = {command.stored.sequence: command for command in session.commands()}
    states = dict.fromkeys(commands, "pending")
    for record in session.records:
        transition = _transition_for(record, commands)
        if transition is None:
            continue
        command_sequence, action = transition
        if command_sequence not in states:
            if action == "discard":
                continue
            raise RecoveryError("durable transition targets a missing command")
        states[command_sequence] = _next_state(states[command_sequence], action)
    for sequence, command in tuple(commands.items()):
        state = states[sequence]
        if state == "discarded":
            if not repair:
                raise RecoveryError("discard recovery is required")
            session.remove(command)
        elif state != command.stored.directory:
            if not repair:
                raise RecoveryError("durable transition recovery is required")
            session.move(command, cast(DirectoryName, state))


def _transition_for(
    record: RecoveredRecord,
    commands: dict[int, RecoveredRecord],
) -> tuple[int, str] | None:
    record_type = record.opened.header.record_type
    if record_type == "accepted_receipt":
        accepted = _payload(record, AcceptedReceipt)
        command = _transition_command(commands, accepted.command_sequence)
        _verify_command_binding(command, accepted.command_hash)
        if accepted.command_id != command_payload(command).command_id:
            raise RecoveryError("accepted receipt binds a different command ID")
        if accepted.response_digest != digest_json({"response": accepted.response}):
            raise RecoveryError("accepted receipt response digest does not match")
        return accepted.command_sequence, "accepted"
    if record_type == "quarantine_receipt":
        quarantined = _payload(record, QuarantineReceipt)
        command = _transition_command(commands, quarantined.command_sequence)
        _verify_command_binding(command, quarantined.command_hash)
        return quarantined.command_sequence, "quarantined"
    if record_type == "disposition":
        disposition = _payload(record, Disposition)
        target_command = commands.get(disposition.command_sequence)
        if target_command is not None:
            _verify_command_binding(target_command, disposition.command_hash)
        elif disposition.action != "discard":
            raise RecoveryError("durable transition targets a missing command")
        return disposition.command_sequence, disposition.action
    return None


def _transition_command(
    commands: dict[int, RecoveredRecord],
    sequence: int,
) -> RecoveredRecord:
    try:
        return commands[sequence]
    except KeyError as error:
        raise RecoveryError("durable transition targets a missing command") from error


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
        "corrupt_disposition": frozenset({"quarantine"}),
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
