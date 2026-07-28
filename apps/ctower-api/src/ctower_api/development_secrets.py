"""Secret-reference resolution and keyring authority for the E2 shadow runtime."""

from __future__ import annotations

import hmac
import importlib
import re
from typing import Protocol, cast
from urllib.parse import quote

from ctower_api.development_config import DevelopmentConfig

__all__ = [
    "SecretReferenceMissingError",
    "delete_secret",
    "development_dsn",
    "load_secret",
    "put_secret",
    "unlock_development_keyring",
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


class SecretReferenceMissingError(RuntimeError):
    """The allowlisted backend is available but one exact reference is absent."""


class _Backend(Protocol):
    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def development_dsn(config: DevelopmentConfig, role: str, *, standby: bool = False) -> str:
    """Resolve one supported role through an exact keyring reference."""

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
