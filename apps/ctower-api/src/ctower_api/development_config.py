"""Strict, secret-reference-only configuration for the E2 shadow runtime."""

from __future__ import annotations

import hmac
import importlib
import os
import re
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "DevelopmentConfig",
    "DevelopmentState",
    "config_path",
    "development_dsn",
    "load_config",
    "load_secret",
    "load_state",
    "put_secret",
    "state_path",
    "unlock_development_keyring",
    "write_config",
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


class _Backend(Protocol):
    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...


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


def config_path() -> Path:
    return _config_home() / "ctower" / "development-runtime.json"


def state_path() -> Path:
    return _state_home() / "ctower" / "development-runtime-state.json"


def load_config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate_json(config_path().read_text(encoding="utf-8"))


def write_config(config: DevelopmentConfig) -> None:
    _write_owner_only(
        config_path(),
        config.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def load_state() -> DevelopmentState:
    return DevelopmentState.model_validate_json(state_path().read_text(encoding="utf-8"))


def write_state(state: DevelopmentState) -> None:
    _write_owner_only(
        state_path(),
        state.model_dump_json(by_alias=True, indent=2) + "\n",
    )


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


def load_secret(reference: str) -> str:
    if _REFERENCE.fullmatch(reference) is None:
        raise ValueError("invalid development secret reference")
    try:
        value = _secure_backend().get_password(_SERVICE, reference)
    except Exception as error:
        raise RuntimeError("secure OS keyring is unavailable or locked") from error
    if value is None:
        raise RuntimeError(f"secure OS keyring is missing reference {reference}")
    return value


def unlock_development_keyring() -> None:
    """Unlock the owner-only passwordless development collection without a prompt."""

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
