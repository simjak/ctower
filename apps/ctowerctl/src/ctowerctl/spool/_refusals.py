"""Private closed set of the refusal names a receipt may durably keep."""

from __future__ import annotations

import re
from typing import Annotated, Final, get_args

from pydantic import AfterValidator

from ctower_client.models import Problem

__all__ = [
    "AUTHORED_REFUSALS",
    "PERSISTABLE_REFUSALS",
    "UNRECOGNIZED_REFUSAL",
    "RefusalName",
    "refusal_name",
]

UNRECOGNIZED_REFUSAL: Final = "unrecognized_refusal"

_AUTHORED_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SEPARATOR = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SEPARATOR.sub("_", value.casefold())[:64].strip("_")


def _authored_refusals() -> frozenset[str]:
    """Take the allowlist from the authored contract the server itself is bound to."""

    names = (_slug(code) for code in get_args(Problem.model_fields["code"].annotation))
    return frozenset(name for name in names if _AUTHORED_NAME.match(name))


AUTHORED_REFUSALS: Final[frozenset[str]] = _authored_refusals()
PERSISTABLE_REFUSALS: Final[frozenset[str]] = AUTHORED_REFUSALS | {UNRECOGNIZED_REFUSAL}


def refusal_name(code: str) -> str:
    """Name a refusal from the allowlist; anything else is the content-free sentinel."""

    slug = _slug(code)
    return slug if slug in AUTHORED_REFUSALS else UNRECOGNIZED_REFUSAL


def _authored_only(value: str) -> str:
    if value not in PERSISTABLE_REFUSALS:
        raise ValueError("refusal name is neither authored nor the unrecognized sentinel")
    return value


RefusalName = Annotated[str, AfterValidator(_authored_only)]
