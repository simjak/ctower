"""Telemetry binding for spawn record events at the record boundary."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from os import urandom
from typing import cast
from uuid import UUID

from ctower_kernel.telemetry import TelemetryContext

__all__ = ["spawn_event_telemetry"]


def spawn_event_telemetry(
    telemetry: object | None,
    principal_id: UUID,
    tenant_id: UUID,
    command_id: UUID,
) -> TelemetryContext:
    """Bind command identity to caller telemetry or create the house default."""

    if telemetry is not None:
        return cast(TelemetryContext, telemetry).bind(
            tenant_id=str(tenant_id),
            actor_id=str(principal_id),
            command_id=str(command_id),
        )
    trace = hashlib.sha256(command_id.bytes + b"trace").hexdigest()
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=trace[:32],
        span_id=trace[32:48],
        trace_flags=1,
        correlation_id=str(_uuid7(datetime.now(UTC))),
        causation_id=str(command_id),
        tenant_id=str(tenant_id),
        actor_id=str(principal_id),
        command_id=str(command_id),
    )


def _uuid7(now: datetime) -> UUID:
    unix_ms = int(now.timestamp() * 1000)
    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= int.from_bytes(urandom(10), "big")
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    return UUID(int=value)
