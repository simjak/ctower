"""Closed ruling additions consumed by the HTTP inventory oracle."""

from __future__ import annotations

__all__: tuple[str, ...] = ()

RULING_OPERATION_METADATA: dict[str, tuple[object, bool, str, object, bool]] = {
    "appendRuling": ("ruling append", True, "allowed", None, False),
    "getRuling": ("ruling get", False, "forbidden", None, False),
    "listRulings": ("ruling list", False, "forbidden", None, False),
}
RULING_PROBLEM_CODES = {
    "invalid-ruling",
    "ruling-already-superseded",
    "ruling-not-found",
    "ruling-project-unavailable",
    "ruling-seat-not-found",
}
