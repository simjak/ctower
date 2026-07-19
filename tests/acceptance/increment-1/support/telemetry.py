"""Strict telemetry header fixture for direct HTTP Adapter tests."""

from __future__ import annotations

import json
import secrets
from uuid import UUID, uuid4

__all__: tuple[str, ...] = ()


def telemetry_headers(
    command_id: UUID | None = None, *, ticket_id: UUID | None = None
) -> dict[str, str]:
    command = command_id or uuid4()
    payload: dict[str, object] = {
        "schema": "ctower.telemetry-context/v1",
        "trace_id": secrets.token_hex(16),
        "span_id": secrets.token_hex(8),
        "trace_flags": 1,
        "correlation_id": str(command),
        "causation_id": str(command),
        "tenant_id": "unresolved",
        "actor_id": "unresolved",
        "command_id": str(command),
    }
    if ticket_id is not None:
        payload["ticket_id"] = str(ticket_id)
    return {
        "X-Ctower-Telemetry-Context": json.dumps(payload, separators=(",", ":"), sort_keys=True)
    }
