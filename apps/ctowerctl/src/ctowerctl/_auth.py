"""Ephemeral stdin-only authority handling for ctowerctl."""

from __future__ import annotations

from typing import TextIO

__all__: tuple[str, ...] = ()

_MAX_AUTHORITY_CHARACTERS = 8192


def read_authority(stream: TextIO) -> str:
    """Read one bounded current authority value without persisting or echoing it."""

    authority = stream.readline(_MAX_AUTHORITY_CHARACTERS + 2).rstrip("\r\n")
    if not authority or len(authority) > _MAX_AUTHORITY_CHARACTERS:
        raise ValueError("a bounded authority value is required on stdin")
    return authority
