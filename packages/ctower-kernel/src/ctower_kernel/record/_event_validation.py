"""Shared strictness helpers every canonical event payload validates through."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

__all__ = ["_bounded", "_require_uuid_fields", "_require_uuid_tuple", "_validate_timestamp"]


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("event timestamps must be datetimes")
    if value.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")


def _bounded(label: str, value: object, *, minimum: int, maximum: int | None = None) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise ValueError(f"{label} is outside the authored event contract")


def _require_uuid_fields(value: object, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(getattr(value, name), UUID):
            raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, UUID) for item in value):
        raise TypeError(f"{label} must be a UUID tuple")
