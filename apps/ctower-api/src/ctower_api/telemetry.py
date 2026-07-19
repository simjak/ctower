"""Failure-isolated application telemetry exporter."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from ctower_kernel.telemetry import TelemetryContext, TelemetryRecord

__all__ = ["TelemetryRecorder"]

Exporter = Callable[[dict[str, object]], None]


class TelemetryRecorder:
    """Emit compatible signals while keeping exporter failure non-authoritative."""

    def __init__(self, exporter: Exporter | None = None) -> None:
        self._exporter = exporter
        self._degraded = False
        self._lock = Lock()

    @property
    def health(self) -> str:
        """Expose truthful exporter health without becoming a command dependency."""

        with self._lock:
            return "degraded" if self._degraded else "healthy"

    def emit(
        self,
        name: str,
        context: TelemetryContext,
        *,
        outcome: str,
        reason: str,
    ) -> None:
        """Export one span, log, and metric view of a redacted stable record."""

        if self._exporter is None:
            return
        for signal in ("span", "log", "metric"):
            record = TelemetryRecord(
                signal=signal,
                name=name,
                context=context,
                outcome=outcome,
                reason=reason,
            )
            try:
                self._exporter(record.to_mapping())
            except (OSError, RuntimeError, TypeError, ValueError):
                with self._lock:
                    self._degraded = True
