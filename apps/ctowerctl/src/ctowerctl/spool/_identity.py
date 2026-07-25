"""Private keyed enqueue-credential identity binding."""

from __future__ import annotations

import hashlib
import hmac
from typing import Final

from ctowerctl.spool._crypto import KeySet

__all__ = ["credential_binding", "same_binding"]

_BINDING_DOMAIN: Final = b"ctower-spool/v1/enqueue-credential\0"
_MAX_CREDENTIAL_BYTES = 32 * 1024


def credential_binding(keys: KeySet, credential: str) -> str:
    """Derive an opaque domain-separated identity without retaining the credential."""

    encoded = credential.encode("utf-8")
    if not encoded or len(encoded) > _MAX_CREDENTIAL_BYTES:
        raise ValueError("a bounded credential identity is required")
    return hmac.new(
        keys.credential_binding,
        _BINDING_DOMAIN + encoded,
        hashlib.sha256,
    ).hexdigest()


def same_binding(left: str, right: str) -> bool:
    """Compare opaque credential bindings without timing-dependent equality."""

    return hmac.compare_digest(left, right)
