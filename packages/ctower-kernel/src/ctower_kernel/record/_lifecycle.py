"""Shared Record-owned ticket lifecycle semantics."""

from __future__ import annotations

__all__: tuple[str, ...] = ()

TERMINAL_TICKET_STATES = frozenset({"cancelled", "closed"})
