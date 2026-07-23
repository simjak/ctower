"""Private fail-closed secure operating-system keyring adapter."""

from __future__ import annotations

import base64
import hmac
import importlib
import os
from typing import Protocol, cast
from uuid import UUID

_SERVICE = "ctower-spool-v1"
_MASTER_KEY_BYTES = 32
_ALLOWED_BACKENDS = frozenset(
    {
        ("keyring.backends.SecretService", "Keyring"),
        ("keyring.backends.macOS", "Keyring"),
        ("keyring.backends.Windows", "Keyring"),
        ("keyring.backends.Windows", "WinVaultKeyring"),
    }
)


class KeyringError(RuntimeError):
    """No verified secure OS credential store is available."""


class _Backend(Protocol):
    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...


def create_master_key(spool_uuid: UUID) -> bytes:
    """Create one random master key in an allowlisted secure backend."""

    backend = _secure_backend()
    username = str(spool_uuid)
    try:
        existing = backend.get_password(_SERVICE, username)
    except Exception as error:
        raise KeyringError("secure OS keyring is unavailable or locked") from error
    if existing is not None:
        raise KeyringError("keyring already contains this spool identity")
    master_key = os.urandom(_MASTER_KEY_BYTES)
    try:
        backend.set_password(_SERVICE, username, base64.b64encode(master_key).decode("ascii"))
        stored = _decode(backend.get_password(_SERVICE, username))
    except Exception as error:
        raise KeyringError("secure OS keyring refused the spool key") from error
    if not hmac.compare_digest(stored, master_key):
        raise KeyringError("secure OS keyring did not persist the exact spool key")
    return master_key


def load_master_key(spool_uuid: UUID) -> bytes:
    """Load an existing master key or fail without touching ciphertext."""

    backend = _secure_backend()
    try:
        value = backend.get_password(_SERVICE, str(spool_uuid))
    except Exception as error:
        raise KeyringError("secure OS keyring is unavailable or locked") from error
    if value is None:
        raise KeyringError("secure OS keyring is missing the spool key")
    return _decode(value)


def _secure_backend() -> _Backend:
    try:
        keyring_module = importlib.import_module("keyring")
        get_keyring = keyring_module.get_keyring
        backend = cast(_Backend, get_keyring())
    except (AttributeError, ImportError, RuntimeError) as error:
        raise KeyringError("an allowlisted secure OS keyring is required") from error
    identity = (backend.__class__.__module__, backend.__class__.__name__)
    try:
        approved = identity in _ALLOWED_BACKENDS and backend.priority > 0
    except (AttributeError, TypeError) as error:
        raise KeyringError("the selected keyring backend is not securely identifiable") from error
    if not approved:
        raise KeyringError("the selected keyring backend is not allowlisted as secure")
    return backend


def _decode(value: str | None) -> bytes:
    if value is None:
        raise KeyringError("secure OS keyring is missing the spool key")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as error:
        raise KeyringError("secure OS keyring returned an invalid spool key") from error
    if len(decoded) != _MASTER_KEY_BYTES:
        raise KeyringError("secure OS keyring returned a non-256-bit spool key")
    return decoded
