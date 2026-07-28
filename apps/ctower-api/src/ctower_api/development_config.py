"""Strict, secret-reference-only configuration for the E2 shadow runtime."""

from __future__ import annotations

import hmac
import importlib
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, Self, cast
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DevelopmentBootstrapCheckpoint",
    "DevelopmentConfig",
    "DevelopmentFinalizerHealth",
    "DevelopmentFinalizerProgress",
    "DevelopmentState",
    "SecretReferenceMissingError",
    "bootstrap_checkpoint_path",
    "config_path",
    "delete_bootstrap_checkpoint",
    "delete_secret",
    "development_dsn",
    "finalizer_progress_path",
    "load_bootstrap_checkpoint",
    "load_config",
    "load_finalizer_progress",
    "load_secret",
    "load_state",
    "observe_finalizer_health",
    "put_secret",
    "state_path",
    "unlock_development_keyring",
    "write_bootstrap_checkpoint",
    "write_config",
    "write_finalizer_progress",
    "write_state",
]

_SERVICE = "ctower-development-runtime-v1"
_ALLOWED_BACKENDS = frozenset(
    {
        ("keyring.backends.SecretService", "Keyring"),
        ("keyring.backends.macOS", "Keyring"),
        ("keyring.backends.Windows", "Keyring"),
        ("keyring.backends.Windows", "WinVaultKeyring"),
    }
)
_REFERENCE = re.compile(r"^secret-service:ctower-development/[a-z0-9-]{3,64}$")
_FINALIZER_STALL_AFTER = timedelta(seconds=10)


class SecretReferenceMissingError(RuntimeError):
    """The allowlisted backend is available but one exact reference is absent."""


class _Backend(Protocol):
    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DevelopmentConfig(_StrictModel):
    """One local-only deployment description containing references, never values."""

    schema_id: Literal["ctower.development-runtime/v1"] = Field(alias="schema")
    label: Literal["SHADOW_ONLY_CP3_D_NOT_PROVEN"]
    api_host: Literal["127.0.0.1"]
    api_port: int = Field(ge=1024, le=65535)
    database_host: Literal["127.0.0.1"]
    database_name: Literal["ctower"]
    primary_port: int = Field(ge=1024, le=65535)
    standby_port: int = Field(ge=1024, le=65535)
    postgres_image: str
    postgres_admin_secret_ref: str
    migrator_secret_ref: str
    runtime_secret_ref: str
    projection_secret_ref: str
    operator_secret_ref: str
    commander_secret_ref: str

    @field_validator(
        "postgres_admin_secret_ref",
        "migrator_secret_ref",
        "runtime_secret_ref",
        "projection_secret_ref",
        "operator_secret_ref",
        "commander_secret_ref",
    )
    @classmethod
    def _secret_reference(cls, value: str) -> str:
        if _REFERENCE.fullmatch(value) is None:
            raise ValueError("development secrets must be Secret Service references")
        return value

    @field_validator("postgres_image")
    @classmethod
    def _pinned_postgres(cls, value: str) -> str:
        if re.fullmatch(r"postgres@sha256:[0-9a-f]{64}", value) is None:
            raise ValueError("development PostgreSQL image must use one immutable digest")
        return value


class DevelopmentState(_StrictModel):
    """Non-secret identities produced by first-tenant bootstrap."""

    schema_id: Literal["ctower.development-state/v1"] = Field(alias="schema")
    tenant_id: UUID
    operator_id: UUID
    commander_id: UUID


class DevelopmentBootstrapCheckpoint(_StrictModel):
    """Non-secret replay identity for a crash-resumable first-tenant bootstrap."""

    schema_id: Literal["ctower.development-bootstrap-checkpoint/v1"] = Field(alias="schema")
    command_id: UUID
    capability_ref: Literal["secret-service:ctower-development/bootstrap-capability"]
    tenant_name: str = Field(min_length=1, max_length=120)
    tenant_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def _expiry_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bootstrap checkpoint expiry must be timezone-aware")
        return value


class DevelopmentFinalizerProgress(_StrictModel):
    """Last completed or failed ordinary-finalizer scan, persisted by the worker."""

    schema_id: Literal["ctower.development-finalizer-progress/v1"] = Field(alias="schema")
    sequence: int = Field(ge=1)
    observed_at: datetime
    scan_status: Literal["completed", "failed"]
    attempted: int = Field(ge=0)
    accepted: int = Field(ge=0)
    pending: int = Field(ge=0)
    refused: int = Field(ge=0)
    detail_code: Literal["finalizer-exception"] | None

    @field_validator("observed_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("finalizer progress time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _conserves_attempts(self) -> Self:
        if self.attempted != self.accepted + self.pending + self.refused:
            raise ValueError("finalizer progress counts must conserve attempts")
        if self.scan_status == "completed" and self.detail_code is not None:
            raise ValueError("completed finalizer progress cannot carry a failure detail")
        if self.scan_status == "failed" and self.detail_code != "finalizer-exception":
            raise ValueError("failed finalizer progress requires its typed detail")
        return self


class DevelopmentFinalizerHealth(_StrictModel):
    """Fail-closed liveness conclusion derived from worker state and scan progress."""

    schema_id: Literal["ctower.development-finalizer-health/v1"] = Field(alias="schema")
    status: Literal["HEALTHY", "DEGRADED"]
    reason: Literal[
        "progress_observed",
        "progress_unknown",
        "progress_stalled",
        "finalizer_refused",
        "finalizer_failed",
        "worker_inactive",
    ]
    sequence: int | None
    last_progress_at: datetime | None
    attempted: int | None
    accepted: int | None
    pending: int | None
    refused: int | None


def config_path() -> Path:
    return _config_home() / "ctower" / "development-runtime.json"


def bootstrap_checkpoint_path() -> Path:
    return _state_home() / "ctower" / "development-bootstrap-checkpoint.json"


def state_path() -> Path:
    return _state_home() / "ctower" / "development-runtime-state.json"


def finalizer_progress_path() -> Path:
    return _state_home() / "ctower" / "development-finalizer-progress.json"


def load_config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate_json(config_path().read_text(encoding="utf-8"))


def write_config(config: DevelopmentConfig) -> None:
    _write_owner_only(
        config_path(),
        config.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def load_bootstrap_checkpoint() -> DevelopmentBootstrapCheckpoint:
    return DevelopmentBootstrapCheckpoint.model_validate_json(
        bootstrap_checkpoint_path().read_text(encoding="utf-8")
    )


def write_bootstrap_checkpoint(checkpoint: DevelopmentBootstrapCheckpoint) -> None:
    _write_owner_only(
        bootstrap_checkpoint_path(),
        checkpoint.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def delete_bootstrap_checkpoint() -> None:
    bootstrap_checkpoint_path().unlink(missing_ok=True)


def load_state() -> DevelopmentState:
    return DevelopmentState.model_validate_json(state_path().read_text(encoding="utf-8"))


def write_state(state: DevelopmentState) -> None:
    _write_owner_only(
        state_path(),
        state.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def load_finalizer_progress() -> DevelopmentFinalizerProgress:
    return DevelopmentFinalizerProgress.model_validate_json(
        finalizer_progress_path().read_text(encoding="utf-8")
    )


def write_finalizer_progress(progress: DevelopmentFinalizerProgress) -> None:
    _write_owner_only(
        finalizer_progress_path(),
        progress.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def observe_finalizer_health(
    worker_state: str, *, now: datetime | None = None
) -> DevelopmentFinalizerHealth:
    """Treat missing, malformed, failed, refused, stale, or inactive progress as degraded."""

    observed_now = now or datetime.now(UTC)
    try:
        progress = load_finalizer_progress()
    except (OSError, ValueError):
        return _finalizer_health("DEGRADED", "progress_unknown", None)
    degraded_reason = _finalizer_degradation_reason(worker_state, progress, observed_now)
    if degraded_reason is not None:
        return _finalizer_health("DEGRADED", degraded_reason, progress)
    return _finalizer_health("HEALTHY", "progress_observed", progress)


def development_dsn(config: DevelopmentConfig, role: str, *, standby: bool = False) -> str:
    secret_ref = {
        "postgres": config.postgres_admin_secret_ref,
        "ctower_migrator": config.migrator_secret_ref,
        "ctower_runtime": config.runtime_secret_ref,
        "ctower_projection_runtime": config.projection_secret_ref,
    }.get(role)
    if secret_ref is None:
        raise ValueError("unsupported development database role")
    password = quote(load_secret(secret_ref), safe="")
    port = config.standby_port if standby else config.primary_port
    timeout = "?connect_timeout=1" if standby else ""
    return (
        f"postgresql://{role}:{password}@{config.database_host}:{port}/"
        f"{config.database_name}{timeout}"
    )


def put_secret(reference: str, value: str) -> None:
    if _REFERENCE.fullmatch(reference) is None or not value:
        raise ValueError("invalid development secret reference or value")
    backend = _secure_backend()
    try:
        backend.set_password(_SERVICE, reference, value)
        stored = backend.get_password(_SERVICE, reference)
    except Exception as error:
        raise RuntimeError("secure OS keyring refused the development secret") from error
    if stored is None or not hmac.compare_digest(stored, value):
        raise RuntimeError("secure OS keyring did not persist the exact development secret")


def delete_secret(reference: str) -> None:
    if _REFERENCE.fullmatch(reference) is None:
        raise ValueError("invalid development secret reference")
    backend = _secure_backend()
    try:
        if backend.get_password(_SERVICE, reference) is not None:
            backend.delete_password(_SERVICE, reference)
        stored = backend.get_password(_SERVICE, reference)
    except Exception as error:
        raise RuntimeError("secure OS keyring refused development secret deletion") from error
    if stored is not None:
        raise RuntimeError("secure OS keyring retained a deleted development secret")


def load_secret(reference: str) -> str:
    if _REFERENCE.fullmatch(reference) is None:
        raise ValueError("invalid development secret reference")
    try:
        value = _secure_backend().get_password(_SERVICE, reference)
    except Exception as error:
        raise RuntimeError("secure OS keyring is unavailable or locked") from error
    if value is None:
        raise SecretReferenceMissingError(f"secure OS keyring is missing reference {reference}")
    return value


def unlock_development_keyring() -> None:
    """Unlock the login collection used by this owner-only development account."""

    try:
        secretstorage = importlib.import_module("secretstorage")
        defines = importlib.import_module("secretstorage.defines")
        util = importlib.import_module("secretstorage.util")
        connection = secretstorage.dbus_init()
        session = util.open_session(connection)
        service = util.DBusAddressWrapper(
            defines.SS_PATH,
            "org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface",
            connection,
        )
        service.call(
            "UnlockWithMasterPassword",
            "o(oayays)",
            "/org/freedesktop/secrets/collection/login",
            util.format_secret(session, b"", "text/plain"),
        )
    except Exception as error:
        raise RuntimeError(
            "passwordless development Secret Service collection is unavailable"
        ) from error
    load_secret("secret-service:ctower-development/postgres-admin")


def _finalizer_health(
    status: Literal["HEALTHY", "DEGRADED"],
    reason: Literal[
        "progress_observed",
        "progress_unknown",
        "progress_stalled",
        "finalizer_refused",
        "finalizer_failed",
        "worker_inactive",
    ],
    progress: DevelopmentFinalizerProgress | None,
) -> DevelopmentFinalizerHealth:
    return DevelopmentFinalizerHealth(
        schema="ctower.development-finalizer-health/v1",
        status=status,
        reason=reason,
        sequence=None if progress is None else progress.sequence,
        last_progress_at=None if progress is None else progress.observed_at,
        attempted=None if progress is None else progress.attempted,
        accepted=None if progress is None else progress.accepted,
        pending=None if progress is None else progress.pending,
        refused=None if progress is None else progress.refused,
    )


def _finalizer_degradation_reason(
    worker_state: str,
    progress: DevelopmentFinalizerProgress,
    observed_now: datetime,
) -> (
    Literal[
        "progress_stalled",
        "finalizer_refused",
        "finalizer_failed",
        "worker_inactive",
    ]
    | None
):
    if worker_state != "active":
        return "worker_inactive"
    if progress.scan_status == "failed":
        return "finalizer_failed"
    if progress.refused:
        return "finalizer_refused"
    age = observed_now - progress.observed_at
    if age < timedelta(0) or age > _FINALIZER_STALL_AFTER:
        return "progress_stalled"
    return None


def _secure_backend() -> _Backend:
    try:
        module = importlib.import_module("keyring")
        backend = cast(_Backend, module.get_keyring())
        identity = (backend.__class__.__module__, backend.__class__.__name__)
        approved = identity in _ALLOWED_BACKENDS and backend.priority > 0
    except (AttributeError, ImportError, RuntimeError, TypeError) as error:
        raise RuntimeError("an allowlisted secure OS keyring is required") from error
    if not approved:
        raise RuntimeError("the selected keyring backend is not allowlisted as secure")
    return backend


def _write_owner_only(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
