"""Typed progress persistence and fail-closed health for the development finalizer."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DevelopmentFinalizerHealth",
    "DevelopmentFinalizerProgress",
    "finalizer_progress_path",
    "load_finalizer_progress",
    "observe_finalizer_health",
    "write_finalizer_progress",
]

_FINALIZER_STALL_AFTER = timedelta(seconds=10)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DevelopmentFinalizerProgress(_StrictModel):
    """Last completed or failed ordinary-finalizer scan, persisted by the worker."""

    schema_id: Literal["ctower.development-finalizer-progress/v1"] = Field(alias="schema")
    sequence: int = Field(ge=1)
    observed_at: datetime
    scan_status: Literal["completed", "failed"]
    attempted: int = Field(ge=0)
    accepted: int = Field(ge=0)
    pending: int = Field(ge=0)
    refused: int = Field(ge=0)
    quarantined: int = Field(default=0, ge=0)
    detail_code: Literal["finalizer-exception"] | None

    @field_validator("observed_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("finalizer progress time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _conserves_attempts(self) -> Self:
        if self.attempted != self.accepted + self.pending + self.refused:
            raise ValueError("finalizer progress counts must conserve attempts")
        if self.quarantined > self.refused:
            raise ValueError("quarantined finalizer attempts must be refused")
        if self.scan_status == "completed" and self.detail_code is not None:
            raise ValueError("completed finalizer progress cannot carry a failure detail")
        if self.scan_status == "failed" and self.detail_code != "finalizer-exception":
            raise ValueError("failed finalizer progress requires its typed detail")
        return self


class DevelopmentFinalizerHealth(_StrictModel):
    """Fail-closed liveness conclusion derived from worker state and scan progress."""

    schema_id: Literal["ctower.development-finalizer-health/v1"] = Field(alias="schema")
    status: Literal["HEALTHY", "DEGRADED"]
    reason: Literal[
        "progress_observed",
        "progress_unknown",
        "progress_stalled",
        "finalizer_refused",
        "finalizer_failed",
        "worker_inactive",
    ]
    sequence: int | None
    last_progress_at: datetime | None
    attempted: int | None
    accepted: int | None
    pending: int | None
    refused: int | None
    quarantined: int | None = None


def finalizer_progress_path() -> Path:
    return _state_home() / "ctower" / "development-finalizer-progress.json"


def load_finalizer_progress() -> DevelopmentFinalizerProgress:
    return DevelopmentFinalizerProgress.model_validate_json(
        finalizer_progress_path().read_text(encoding="utf-8")
    )


def write_finalizer_progress(progress: DevelopmentFinalizerProgress) -> None:
    _write_owner_only(
        finalizer_progress_path(),
        progress.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def observe_finalizer_health(
    worker_state: str, *, now: datetime | None = None
) -> DevelopmentFinalizerHealth:
    """Treat missing, malformed, failed, refused, stale, or inactive progress as degraded."""

    observed_now = now or datetime.now(UTC)
    try:
        progress = load_finalizer_progress()
    except (OSError, ValueError):
        return _finalizer_health("DEGRADED", "progress_unknown", None)
    degraded_reason = _finalizer_degradation_reason(worker_state, progress, observed_now)
    if degraded_reason is not None:
        return _finalizer_health("DEGRADED", degraded_reason, progress)
    return _finalizer_health("HEALTHY", "progress_observed", progress)


def _finalizer_health(
    status: Literal["HEALTHY", "DEGRADED"],
    reason: Literal[
        "progress_observed",
        "progress_unknown",
        "progress_stalled",
        "finalizer_refused",
        "finalizer_failed",
        "worker_inactive",
    ],
    progress: DevelopmentFinalizerProgress | None,
) -> DevelopmentFinalizerHealth:
    return DevelopmentFinalizerHealth(
        schema="ctower.development-finalizer-health/v1",
        status=status,
        reason=reason,
        sequence=None if progress is None else progress.sequence,
        last_progress_at=None if progress is None else progress.observed_at,
        attempted=None if progress is None else progress.attempted,
        accepted=None if progress is None else progress.accepted,
        pending=None if progress is None else progress.pending,
        refused=None if progress is None else progress.refused,
        quarantined=None if progress is None else progress.quarantined,
    )


def _finalizer_degradation_reason(
    worker_state: str,
    progress: DevelopmentFinalizerProgress,
    observed_now: datetime,
) -> (
    Literal[
        "progress_stalled",
        "finalizer_refused",
        "finalizer_failed",
        "worker_inactive",
    ]
    | None
):
    if worker_state != "active":
        return "worker_inactive"
    if progress.scan_status == "failed":
        return "finalizer_failed"
    if progress.refused:
        return "finalizer_refused"
    age = observed_now - progress.observed_at
    if age < timedelta(0) or age > _FINALIZER_STALL_AFTER:
        return "progress_stalled"
    return None


def _write_owner_only(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
