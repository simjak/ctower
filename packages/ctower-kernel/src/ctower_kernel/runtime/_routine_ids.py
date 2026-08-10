"""Deterministic UUIDv7 identity helper for Routine persistence."""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

__all__: tuple[str, ...] = ()


def stable_uuid7(now: datetime, *identity: bytes) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    digest = hashlib.sha256(b"\x00".join(identity)).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
