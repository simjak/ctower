"""Validate the one authored lossless JSON integer profile used by generated clients."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "JSON_INTEGER_MAXIMUM",
    "JSON_INTEGER_MINIMUM",
    "JsonIntegerProfile",
    "require_json_integer_profile",
]

JSON_INTEGER_MAXIMUM = 9_007_199_254_740_991
JSON_INTEGER_MINIMUM = -JSON_INTEGER_MAXIMUM
_PROFILE_KEY = "x-ctower-json-integer-profile"
_INTEGER_GRAMMAR = "minus-zero-or-nonzero-decimal-digits-only"
_EXPECTED_PROFILE: Mapping[str, object] = {
    "maximum": JSON_INTEGER_MAXIMUM,
    "minimum": JSON_INTEGER_MINIMUM,
    "negative-zero": "normalize-to-zero",
    "semantics": "exact-integer-interoperability",
    "token-syntax": _INTEGER_GRAMMAR,
}


@dataclass(frozen=True, slots=True)
class JsonIntegerProfile:
    """Exact immutable integer semantics consumed by both client generators."""

    minimum: int
    maximum: int
    negative_zero: str
    semantics: str
    token_syntax: str


def require_json_integer_profile(document: Mapping[str, object]) -> JsonIntegerProfile:
    """Fail generation unless authored integers have exact cross-client semantics."""

    if document.get(_PROFILE_KEY) != _EXPECTED_PROFILE:
        raise ValueError(f"{_PROFILE_KEY} must declare the exact lossless JSON integer range")
    return JsonIntegerProfile(
        minimum=JSON_INTEGER_MINIMUM,
        maximum=JSON_INTEGER_MAXIMUM,
        negative_zero="normalize-to-zero",
        semantics="exact-integer-interoperability",
        token_syntax=_INTEGER_GRAMMAR,
    )
