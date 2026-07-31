"""Small public Interface for the encrypted owner-only mutation spool."""

from __future__ import annotations

import hashlib
import importlib
import ipaddress
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, cast
from urllib.parse import SplitResult, quote, unquote, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ctowerctl.spool import _keyring
from ctowerctl.spool._corruption import (
    CorruptDispositionError,
    dispose_corrupt,
    require_no_artifact_digest,
)
from ctowerctl.spool._crypto import RecordType
from ctowerctl.spool._identity import credential_binding, same_binding
from ctowerctl.spool._recovery import (
    CommandEnvelope,
    Disposition,
    RecoveredRecord,
    RecoveryError,
    Session,
    command_payload,
    recover_session,
    utc_text,
)
from ctowerctl.spool._redaction import (
    JsonObject,
    SecretMaterialError,
    ServerRefusal,
    SpoolDoctorReport,
    SpoolEntry,
    SpoolState,
    SpoolStatus,
    canonical_json,
    corrupt_entry,
    digest_json,
    discarded_entry,
    doctor_failure,
    entry_order,
    reason_digest,
    spool_entry,
    spool_status,
    torn_entry,
    unknown_status,
)
from ctowerctl.spool._replay import (
    DrainReport,
    ReplayExecutor,
    ReplayResponse,
    SpoolCommand,
    drain_session,
)
from ctowerctl.spool._retention import compact_accepted
from ctowerctl.spool._store import LockTimeoutError, SafeTree, StorageError

__all__ = [
    "DrainReport",
    "ReplayExecutor",
    "ReplayResponse",
    "ServerRefusal",
    "Spool",
    "SpoolCommand",
    "SpoolConfig",
    "SpoolDoctorReport",
    "SpoolEntry",
    "SpoolError",
    "SpoolState",
    "SpoolStatus",
]

_RECORD_OVERHEAD_RESERVE = 4096
_MAX_DISPOSITION_REASON = 500
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_EXPECTED_LOCAL_FAILURES = (
    _keyring.KeyringError,
    LockTimeoutError,
    RecoveryError,
    SecretMaterialError,
    StorageError,
    ValueError,
)


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SpoolConfig(_BoundaryModel):
    """Bounded local policy; values may tighten but never exceed hard caps."""

    state_path: Path | None = None
    max_command_bytes: Annotated[int, Field(ge=64 * 1024, le=1024 * 1024)] = 1024 * 1024
    max_live_bytes: Annotated[int, Field(ge=1024 * 1024, le=100 * 1024 * 1024)] = 100 * 1024 * 1024
    max_live_commands: Annotated[int, Field(ge=1, le=10_000)] = 10_000
    pending_horizon_days: Annotated[int, Field(ge=1, le=30)] = 30
    accepted_horizon_days: Annotated[int, Field(ge=1, le=30)] = 30
    lock_timeout_seconds: Annotated[float, Field(ge=0.01, le=30.0)] = 5.0
    max_scan_entries: Annotated[int, Field(ge=100, le=30_000)] = 20_000

    @model_validator(mode="after")
    def _validate_capacity(self) -> SpoolConfig:
        if self.max_live_bytes < self.max_command_bytes:
            raise ValueError("live byte capacity cannot be smaller than one command")
        if self.max_scan_entries < self.max_live_commands:
            raise ValueError("scan bound cannot be smaller than live command capacity")
        return self


class SpoolError(RuntimeError):
    """Stable redacted local failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Spool:
    """Per-origin encrypted command spool."""

    def __init__(
        self,
        origin_digest: str,
        config: SpoolConfig,
        tree: SafeTree,
        path: Path,
        identity_binding: str | None = None,
    ) -> None:
        self._origin_digest = origin_digest
        self._config = config
        self._tree = tree
        self._path = path
        self._identity_binding = identity_binding

    @classmethod
    def for_origin(cls, origin: str, config: SpoolConfig | None = None) -> Spool:
        """Resolve one secure hashed-origin state tree without persisting the raw URL."""

        policy = config or SpoolConfig()
        normalized = _normalize_origin(origin)
        origin_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        state_root = policy.state_path or _platform_state_path()
        path = state_root / "spool" / "v1" / origin_digest
        return cls(
            origin_digest,
            policy,
            SafeTree(path, scan_limit=policy.max_scan_entries),
            path,
        )

    def bind_credential(self, credential: str) -> Spool:
        """Return a clone retaining only a keyed opaque identity for enqueue/replay."""

        try:
            with self._session() as session:
                binding = credential_binding(session.keys, credential)
        except _EXPECTED_LOCAL_FAILURES as error:
            raise _spool_error(error) from error
        return Spool(
            self._origin_digest,
            self._config,
            self._tree,
            self._path,
            binding,
        )

    def enqueue(self, command: SpoolCommand) -> SpoolEntry:
        """Durably append a stable command before any caller may send it."""

        try:
            with self._session() as session:
                binding = self._require_identity_binding()
                existing = _find_command_id(session, command.command_id)
                semantic_digest = _semantic_digest(command)
                if existing is not None:
                    return _idempotent_entry(
                        existing,
                        session,
                        semantic_digest,
                        binding,
                    )
                envelope = _new_envelope(
                    command,
                    self._origin_digest,
                    self._config.pending_horizon_days,
                    semantic_digest,
                    binding,
                )
                _check_command_size(envelope, self._config.max_command_bytes)
                _check_capacity(
                    session,
                    self._config,
                    _payload_size(envelope) + _RECORD_OVERHEAD_RESERVE,
                )
                return spool_entry(
                    session.append(RecordType.COMMAND, "pending", envelope),
                    session,
                )
        except SpoolError:
            raise
        except _EXPECTED_LOCAL_FAILURES as error:
            raise _spool_error(error) from error

    def status(self) -> SpoolStatus:
        """Return redacted counts and health, recovering deterministic crash state."""

        try:
            with self._session() as session:
                return spool_status(session, self._origin_digest)
        except _EXPECTED_LOCAL_FAILURES as error:
            return unknown_status(
                self._origin_digest,
                _error_code(error),
                keyring_available=not isinstance(error, _keyring.KeyringError),
            )

    def doctor(self) -> SpoolDoctorReport:
        """Verify without initializing, repairing, moving, or deleting durable state."""

        if not os.path.lexists(self._path):
            return SpoolDoctorReport(
                healthy=True,
                state="uninitialized",
                checks=("path_absent",),
                findings=(),
            )
        try:
            with self._tree.locked(self._config.lock_timeout_seconds, create=False) as store:
                _require_metadata(exists=store.exists_control("metadata"))
                session = recover_session(
                    store,
                    self._origin_digest,
                    maximum_record_bytes=self._config.max_command_bytes,
                    repair=False,
                )
                session.verify_doctor_state()
                _verify_existing_capacity(session, self._config)
        except _keyring.KeyringError:
            return doctor_failure("state_unknown", "keyring_unavailable")
        except (LockTimeoutError, RecoveryError, StorageError, ValueError) as error:
            return doctor_failure("degraded", _error_code(error))
        return SpoolDoctorReport(
            healthy=True,
            state="healthy",
            checks=(
                "permissions",
                "local_filesystem",
                "keyring",
                "metadata_mac",
                "head_mac",
                "record_chain",
                "capacity",
            ),
            findings=(),
        )

    def list_entries(
        self,
        state: SpoolState | None = None,
        *,
        limit: Annotated[int, Field(ge=1)] = 1000,
    ) -> tuple[SpoolEntry, ...]:
        """List only redacted identities/state; content never leaves."""

        if not 1 <= limit <= self._config.max_scan_entries:
            raise SpoolError("scan_limit", "requested spool list exceeds bounded policy")
        try:
            with self._session() as session:
                entries = [spool_entry(item, session) for item in session.commands()]
                entries.extend(corrupt_entry(item) for item in session.corrupt_records)
                if state is not None:
                    entries = [item for item in entries if item.state == state]
                if state in {None, SpoolState.QUARANTINE} and session.torn_evidence:
                    entries.append(torn_entry(session.torn_evidence))
                return tuple(sorted(entries, key=entry_order)[:limit])
        except _EXPECTED_LOCAL_FAILURES as error:
            raise _spool_error(error) from error

    def drain(self, executor: ReplayExecutor) -> DrainReport:
        """Replay globally in order and stop at the first durable barrier."""

        try:
            with self._session() as session:
                return drain_session(
                    session,
                    executor,
                    self._require_identity_binding(),
                )
        except _EXPECTED_LOCAL_FAILURES as error:
            raise _spool_error(error) from error

    def retry(self, sequence: int, reason: str) -> SpoolEntry:
        """Explicitly requeue one quarantined immutable command and ID."""

        return self._disposition(sequence, "retry", reason)

    def discard(
        self,
        sequence: int,
        reason: str,
        *,
        artifact_digest: str | None = None,
    ) -> None:
        """Write a durable disposition tombstone before body removal."""

        self._disposition(sequence, "discard", reason, artifact_digest=artifact_digest)

    def compact(self) -> int:
        """Replace a wholly old accepted chain with one authenticated anchor."""

        try:
            with self._session() as session:
                return compact_accepted(
                    session,
                    now=datetime.now(UTC),
                    horizon=timedelta(days=self._config.accepted_horizon_days),
                )
        except _EXPECTED_LOCAL_FAILURES as error:
            raise _spool_error(error) from error

    def _disposition(
        self,
        sequence: int,
        action: Literal["retry", "discard"],
        reason: str,
        *,
        artifact_digest: str | None = None,
    ) -> SpoolEntry:
        if not 1 <= len(reason) <= _MAX_DISPOSITION_REASON:
            raise SpoolError("invalid_disposition", "disposition reason must be 1..500 characters")
        try:
            with self._session() as session:
                corrupt = session.corrupt_command(sequence)
                if corrupt is not None:
                    return dispose_corrupt(
                        session,
                        corrupt,
                        action,
                        reason,
                        artifact_digest,
                    )
                require_no_artifact_digest(artifact_digest)
                command = _require_quarantined(session.command(sequence))
                disposition = Disposition(
                    schema_version=2,
                    command_sequence=sequence,
                    command_hash=command.opened.record_hash,
                    command_predecessor_hash=(
                        command.opened.header.predecessor_hash if action == "discard" else None
                    ),
                    action=action,
                    reason_digest=reason_digest(reason),
                    recorded_at=utc_text(),
                )
                session.append(RecordType.DISPOSITION, "quarantine", disposition)
                if action == "discard":
                    session.remove(command)
                    return discarded_entry(sequence)
                return spool_entry(session.move(command, "pending"), session)
        except SpoolError:
            raise
        except CorruptDispositionError as error:
            raise SpoolError("invalid_disposition", str(error)) from error
        except _EXPECTED_LOCAL_FAILURES as error:
            raise _spool_error(error) from error

    def _require_identity_binding(self) -> str:
        if self._identity_binding is None:
            raise SpoolError(
                "credential_identity_required",
                "enqueue and replay require an ephemeral credential identity binding",
            )
        return self._identity_binding

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with self._tree.locked(self._config.lock_timeout_seconds) as store:
            yield recover_session(
                store,
                self._origin_digest,
                maximum_record_bytes=self._config.max_command_bytes,
            )


def _new_envelope(
    command: SpoolCommand,
    origin_digest: str,
    horizon_days: int,
    semantic_digest: str,
    identity_binding: str,
) -> CommandEnvelope:
    now = datetime.now(UTC)
    return CommandEnvelope(
        schema_version=2,
        operation_id=command.operation_id,
        path_parameters=command.path_parameters,
        request_body=command.request_body,
        command_id=str(command.command_id),
        origin_digest=origin_digest,
        enqueued_at=utc_text(now),
        expires_at=utc_text(now + timedelta(days=horizon_days)),
        semantic_request_digest=semantic_digest,
        credential_binding=identity_binding,
    )


def _semantic_digest(command: SpoolCommand) -> str:
    return digest_json(
        {
            "operation_id": command.operation_id,
            "path_parameters": command.path_parameters,
            "request_body": command.request_body,
        }
    )


def _find_command_id(session: Session, command_id: UUID) -> RecoveredRecord | None:
    return next(
        (
            record
            for record in session.commands()
            if command_payload(record).command_id == str(command_id)
        ),
        None,
    )


def _idempotent_entry(
    record: RecoveredRecord,
    session: Session,
    semantic_digest: str,
    identity_binding: str,
) -> SpoolEntry:
    payload = command_payload(record)
    if payload.semantic_request_digest != semantic_digest:
        raise SpoolError("command_id_conflict", "command ID already binds a different request")
    if payload.credential_binding is None or not same_binding(
        payload.credential_binding, identity_binding
    ):
        raise SpoolError(
            "credential_identity_mismatch",
            "command ID belongs to another enqueue credential identity",
        )
    return spool_entry(record, session)


def _check_command_size(command: CommandEnvelope, maximum: int) -> None:
    if _payload_size(command) > maximum - _RECORD_OVERHEAD_RESERVE:
        raise SpoolError("command_too_large", "command exceeds the encrypted 1 MiB record policy")


def _check_capacity(session: Session, config: SpoolConfig, incoming_size: int) -> None:
    live_commands = tuple(
        item for item in session.commands() if item.stored.directory in {"pending", "quarantine"}
    )
    live_count = len(live_commands) + len(session.corrupt_records)
    live_bytes = sum(item.stored.size for item in live_commands) + sum(
        item.stored.size for item in session.corrupt_records
    )
    if live_count >= config.max_live_commands:
        raise SpoolError("capacity_count", "live spool command capacity is exhausted")
    if live_bytes + incoming_size > config.max_live_bytes:
        raise SpoolError("capacity_bytes", "live spool byte capacity is exhausted")


def _verify_existing_capacity(session: Session, config: SpoolConfig) -> None:
    live_commands = tuple(
        item for item in session.commands() if item.stored.directory in {"pending", "quarantine"}
    )
    live_count = len(live_commands) + len(session.corrupt_records)
    live_bytes = sum(item.stored.size for item in live_commands) + sum(
        item.stored.size for item in session.corrupt_records
    )
    if live_count > config.max_live_commands:
        raise StorageError("live spool exceeds configured command capacity")
    if live_bytes > config.max_live_bytes:
        raise StorageError("live spool exceeds configured byte capacity")


def _payload_size(payload: BaseModel) -> int:
    return len(canonical_json(cast(JsonObject, payload.model_dump(mode="json"))))


def _normalize_origin(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
    except ValueError as error:
        raise SpoolError("invalid_origin", "origin URL syntax is invalid") from error
    _validate_origin_shape(parsed)
    host, port = _origin_authority(parsed)
    path = _normalized_base_path(parsed.path)
    bracketed_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{bracketed_host}:{port}{path}"


def _validate_origin_shape(parsed: SplitResult) -> None:
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SpoolError("invalid_origin", "origin must be an absolute HTTP(S) URL")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SpoolError(
            "invalid_origin", "origin must not contain credentials, query, or fragment"
        )


def _origin_authority(parsed: SplitResult) -> tuple[str, int]:
    try:
        host = cast(str, parsed.hostname).encode("idna").decode("ascii").casefold()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (UnicodeError, ValueError) as error:
        raise SpoolError("invalid_origin", "origin host or port is invalid") from error
    if parsed.scheme == "http" and not _is_loopback(host):
        raise SpoolError("invalid_origin", "cleartext HTTP is permitted only for loopback")
    return host, port


def _normalized_base_path(raw_path: str) -> str:
    if _INVALID_PERCENT_ESCAPE.search(raw_path):
        raise SpoolError("invalid_origin", "origin base path has an invalid percent escape")
    try:
        decoded = unquote(raw_path or "/", errors="strict")
    except UnicodeError as error:
        raise SpoolError("invalid_origin", "origin base path is not valid UTF-8") from error
    path = PurePosixPath(decoded)
    if any(part in {".", ".."} for part in path.parts) or not decoded.startswith("/"):
        raise SpoolError("invalid_origin", "origin base path is not canonical")
    normalized = "/" + "/".join(part for part in path.parts if part != "/")
    return quote(normalized.rstrip("/") or "/", safe="/:@-._~")


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _platform_state_path() -> Path:
    try:
        module = importlib.import_module("platformdirs")
        resolver = module.user_state_path
        return Path(cast(str | Path, resolver("ctower", appauthor=False)))
    except (AttributeError, ImportError, OSError, TypeError) as error:
        raise SpoolError(
            "platform_state_unavailable",
            "platformdirs owner state path is required",
        ) from error


def _spool_error(error: Exception) -> SpoolError:
    if isinstance(error, SpoolError):
        return error
    return SpoolError(_error_code(error), "local encrypted spool failed closed")


def _error_code(error: Exception) -> str:
    if isinstance(error, _keyring.KeyringError):
        return "keyring_unavailable"
    if isinstance(error, LockTimeoutError):
        return "lock_timeout"
    if isinstance(error, SecretMaterialError):
        return "secret_material"
    if isinstance(error, RecoveryError):
        return error.code
    if isinstance(error, StorageError):
        return "storage_integrity"
    return "local_failure"


def _require_metadata(*, exists: bool) -> None:
    if not exists:
        raise RecoveryError("spool metadata is missing")


def _require_quarantined(command: RecoveredRecord | None) -> RecoveredRecord:
    if command is None or command.stored.directory != "quarantine":
        raise SpoolError(
            "invalid_disposition",
            "disposition requires one quarantined command sequence",
        )
    return command
