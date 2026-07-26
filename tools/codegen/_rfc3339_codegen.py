"""Validate the one authored RFC 3339 profile consumed by both client generators."""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["require_rfc3339_profile"]

_PROFILE_KEY = "x-ctower-rfc3339-profile"
_EXPECTED_PROFILE: Mapping[str, object] = {
    "calendar": "proleptic-gregorian",
    "date-time-separator": "T",
    "fractional-second-digits": [1, 6],
    "leap-seconds": "rejected",
    "numeric-offset-range": "00:00-23:59",
    "timezone": "required",
    "unknown-local-offset": "rejected",
    "year-range": [1, 9999],
    "zero-offset": "Z-or-plus-00:00",
}


def require_rfc3339_profile(document: Mapping[str, object]) -> None:
    """Fail generation unless the authored profile matches implemented semantics exactly."""

    if document.get(_PROFILE_KEY) != _EXPECTED_PROFILE:
        raise ValueError(f"{_PROFILE_KEY} must declare the exact supported RFC 3339 subset")
