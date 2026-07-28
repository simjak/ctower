"""PostgreSQL SCRAM verifier generation without plaintext SQL credentials."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

__all__: tuple[str, ...] = ()

_ITERATIONS = 4096
_SALT_BYTES = 16


def postgres_scram_verifier(password: str) -> str:
    """Derive the verifier PostgreSQL accepts in place of a plaintext password."""

    if not password or not password.isascii() or not password.isprintable():
        raise ValueError("development PostgreSQL credentials must be printable ASCII")
    salt = secrets.token_bytes(_SALT_BYTES)
    salted_password = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("ascii"),
        salt,
        _ITERATIONS,
    )
    client_key = hmac.digest(salted_password, b"Client Key", "sha256")
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.digest(salted_password, b"Server Key", "sha256")
    return (
        f"SCRAM-SHA-256${_ITERATIONS}:{_encoded(salt)}"
        f"${_encoded(stored_key)}:{_encoded(server_key)}"
    )


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")
