"""Validate the one authored lossless JSON integer profile used by generated clients."""

from __future__ import annotations

from collections.abc import Mapping

__all__ = [
    "JSON_INTEGER_MAXIMUM",
    "JSON_INTEGER_MINIMUM",
    "require_json_integer_profile",
]

JSON_INTEGER_MAXIMUM = 9_007_199_254_740_991
JSON_INTEGER_MINIMUM = -JSON_INTEGER_MAXIMUM
_PROFILE_KEY = "x-ctower-json-integer-profile"
_EXPECTED_PROFILE: Mapping[str, object] = {
    "maximum": JSON_INTEGER_MAXIMUM,
    "minimum": JSON_INTEGER_MINIMUM,
    "semantics": "exact-integer-interoperability",
}


def require_json_integer_profile(document: Mapping[str, object]) -> None:
    """Fail generation unless authored integers have exact cross-client semantics."""

    if document.get(_PROFILE_KEY) != _EXPECTED_PROFILE:
        raise ValueError(f"{_PROFILE_KEY} must declare the exact lossless JSON integer range")
