"""Negative fixture crossing an owner-private boundary."""

from app._private import VALUE


def leaked_value() -> str:
    return VALUE
