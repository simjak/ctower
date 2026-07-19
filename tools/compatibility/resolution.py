"""Canonical dependency-lock parsing at compatibility evidence boundaries."""

from __future__ import annotations

import re

from .models_core import CompatibilityError

__all__ = ["canonicalize_freeze", "validate_canonical_lock"]

_FREEZE_ENTRY = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"==(?P<version>[0-9][A-Za-z0-9.!+]*)$"
)
_NAME_SEPARATOR = re.compile(r"[-_.]+")


def canonicalize_freeze(value: str) -> tuple[str, ...]:
    """Parse pip freeze output into sorted, unique PEP 503 package pins."""

    entries: dict[str, str] = {}
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _FREEZE_ENTRY.fullmatch(line)
        if match is None:
            raise CompatibilityError(
                "dependency freeze contains a noncanonical package==version entry"
            )
        name = _NAME_SEPARATOR.sub("-", match.group("name").lower())
        entry = f"{name}=={match.group('version')}"
        if name in entries:
            raise CompatibilityError(f"dependency freeze repeats canonical package {name}")
        entries[name] = entry
    if not entries:
        raise CompatibilityError("dependency freeze is empty")
    return tuple(sorted(entries.values()))


def validate_canonical_lock(lock: tuple[str, ...]) -> None:
    """Reject report locks that are not already canonical parser output."""

    try:
        canonical = canonicalize_freeze("\n".join(lock))
    except CompatibilityError as error:
        raise ValueError(str(error)) from error
    if lock != canonical:
        raise ValueError("dependency lock must be sorted canonical package==version entries")
