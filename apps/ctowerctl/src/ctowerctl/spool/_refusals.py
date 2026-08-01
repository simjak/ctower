"""Private allowlist of the authored refusal names a receipt may durably keep."""

from __future__ import annotations

import re
from typing import Final, get_args

from ctower_client.models import Problem

__all__ = [
    "AUTHORED_REFUSALS",
    "REFUSAL_NAME_PATTERN",
    "UNRECOGNIZED_PREFIX",
    "refusal_name",
]

UNRECOGNIZED_PREFIX: Final = "unrecognized_refusal:"
REFUSAL_NAME_PATTERN: Final = r"^([a-z][a-z0-9_]{0,63}|unrecognized_refusal:[a-z0-9_]{1,64})$"

_UNNAMED: Final = "unnamed"
_AUTHORED_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SEPARATOR = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SEPARATOR.sub("_", value.casefold())[:64].strip("_")


def _authored_refusals() -> frozenset[str]:
    """Take the allowlist from the authored contract the server itself is bound to."""

    names = (_slug(code) for code in get_args(Problem.model_fields["code"].annotation))
    return frozenset(name for name in names if _AUTHORED_NAME.match(name))


AUTHORED_REFUSALS: Final[frozenset[str]] = _authored_refusals()


def refusal_name(code: str) -> str:
    """Name a refusal only from the allowlist; keep a slug of anything unrecognized."""

    slug = _slug(code.removeprefix(UNRECOGNIZED_PREFIX))
    if slug in AUTHORED_REFUSALS:
        return slug
    return f"{UNRECOGNIZED_PREFIX}{slug or _UNNAMED}"
