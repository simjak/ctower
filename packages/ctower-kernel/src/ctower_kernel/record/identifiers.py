"""Shared RFC 9562 identity construction for Record-owned aggregates."""

from __future__ import annotations

import secrets
from datetime import datetime
from uuid import UUID

__all__ = ["uuid7"]


def uuid7(now: datetime) -> UUID:
    """Return one UUIDv7 using the supplied authoritative time."""

    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
