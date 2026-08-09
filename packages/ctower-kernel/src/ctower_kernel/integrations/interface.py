"""Strict provider-neutral values and the small IssueConnector protocol."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ctower_kernel.record import Actor

__all__ = [
    "AmbiguousWrite",
    "CloseExternalIssue",
    "CloseExternalIssueResult",
    "CloseFailure",
    "ConnectorAttempt",
    "ConnectorClaim",
    "ConnectorCursorToken",
    "ConnectorLabelMapping",
    "ConnectorLink",
    "ConnectorReceipt",
    "ConnectorRegistration",
    "ConnectorStore",
    "ConnectorSyncBatch",
    "ConnectorSyncError",
    "ExternalIssue",
    "ExternalIssuePage",
    "FailureReason",
    "FetchFailure",
    "FetchIssuePage",
    "FetchIssuePageResult",
    "IssueConnector",
    "RetryClass",
    "WriteDisposition",
]

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_KEY_PATTERN = r"^[a-z][a-z0-9.-]{2,127}$"
_LABEL_PATTERN = r"^[a-z][a-z0-9._-]{1,95}$"
_PROJECT_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
_MAX_CURSOR_LENGTH = 4096
_MAX_DESCRIPTION_LENGTH = 60_000
_MAX_CONNECTOR_KIND_LENGTH = 64
_MAX_EXTERNAL_REF_LENGTH = 256
_MAX_LABELS = 100
_MAX_LABEL_LENGTH = 255
_MAX_PAGE_SIZE = 100
_MAX_POLL_SECONDS = 3600
_MIN_POLL_SECONDS = 15

RetryClass = Literal["retryable", "terminal"]
RetryableReason = Literal[
    "timeout",
    "transport_connect",
    "transport_read",
    "transport_protocol",
    "throttled",
    "provider_5xx",
]
TerminalReason = Literal[
    "authentication",
    "authorization",
    "ordinary_4xx",
    "invalid_payload",
    "unsupported_item",
    "contract_violation",
]
FailureReason = RetryableReason | TerminalReason
WriteDisposition = Literal["not_written", "reconciled_absent"]

_RETRYABLE_REASONS = {
    "timeout",
    "transport_connect",
    "transport_read",
    "transport_protocol",
    "throttled",
    "provider_5xx",
}
_TERMINAL_REASONS = {
    "authentication",
    "authorization",
    "ordinary_4xx",
    "invalid_payload",
    "unsupported_item",
    "contract_violation",
}


class _StrictValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ConnectorCursorToken(_StrictValue):
    """Provider-owned, non-secret, bounded opaque progress value."""

    value: str = Field(min_length=1, max_length=_MAX_CURSOR_LENGTH)


class ConnectorAttempt(_StrictValue):
    """Core-owned immutable budget snapshot for exactly one invocation."""

    attempt_number: int = Field(ge=1, le=4)
    max_attempts: Literal[4]
    deadline_remaining_milliseconds: int = Field(ge=1, le=10_000)

    @model_validator(mode="after")
    def _attempt_is_available(self) -> ConnectorAttempt:
        if self.attempt_number > self.max_attempts:
            raise ValueError("connector attempt exceeds the core-owned maximum")
        return self


class FetchIssuePage(_StrictValue):
    cursor: ConnectorCursorToken
    page_size: int = Field(ge=1, le=_MAX_PAGE_SIZE)


class ExternalIssue(_StrictValue):
    """The complete provider-neutral issue value admitted into connector core."""

    connector_kind: str = Field(pattern=_KEY_PATTERN, max_length=_MAX_CONNECTOR_KIND_LENGTH)
    external_ref: str = Field(min_length=1, max_length=_MAX_EXTERNAL_REF_LENGTH)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=_MAX_DESCRIPTION_LENGTH)
    source_labels: tuple[str, ...] = Field(max_length=_MAX_LABELS)
    reporter_reference: str = Field(min_length=1, max_length=256)
    reporter_display_name: str = Field(min_length=1, max_length=255)
    external_state: Literal["opened", "closed"]
    updated_at: datetime
    display_url: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def _strict_external_value(self) -> ExternalIssue:
        if len(set(self.source_labels)) != len(self.source_labels) or any(
            not 1 <= len(label) <= _MAX_LABEL_LENGTH for label in self.source_labels
        ):
            raise ValueError("connector source labels are outside the bounded contract")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("connector issue updated_at must be timezone-aware")
        parsed = urlsplit(self.display_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("connector issue display URL must be absolute HTTPS")
        return self

    def to_mapping(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class ExternalIssuePage(_StrictValue):
    kind: Literal["page"] = "page"
    issues: tuple[ExternalIssue, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: ConnectorCursorToken
    exhausted: bool


class FetchFailure(_StrictValue):
    kind: Literal["fetch_failure"] = "fetch_failure"
    retry_class: RetryClass
    reason: FailureReason

    @model_validator(mode="after")
    def _reason_matches_class(self) -> FetchFailure:
        _validate_failure_pair(self.retry_class, self.reason)
        return self


class CloseExternalIssue(_StrictValue):
    external_ref: str = Field(min_length=1, max_length=_MAX_EXTERNAL_REF_LENGTH)
    command_id: UUID
    marker: str = Field(min_length=1, max_length=200)
    comment: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _marker_is_deterministic(self) -> CloseExternalIssue:
        if self.marker != f"<!-- ctower-sync:{self.command_id} -->" or not self.comment.strip():
            raise ValueError("connector close marker or comment is outside the authored contract")
        return self


class ConnectorReceipt(_StrictValue):
    kind: Literal["receipt"] = "receipt"
    command_id: UUID
    marker_present: Literal[True] = True
    issue_closed: Literal[True] = True
    comment_created: bool


class CloseFailure(_StrictValue):
    kind: Literal["close_failure"] = "close_failure"
    retry_class: RetryClass
    reason: FailureReason
    write_disposition: WriteDisposition

    @model_validator(mode="after")
    def _reason_matches_class(self) -> CloseFailure:
        _validate_failure_pair(self.retry_class, self.reason)
        return self


class AmbiguousWrite(_StrictValue):
    kind: Literal["ambiguous_write"] = "ambiguous_write"
    operation: Literal["comment_and_close"] = "comment_and_close"
    reason: Literal["write_outcome_unknown"] = "write_outcome_unknown"
    write_disposition: Literal["reconciliation_inconclusive"] = "reconciliation_inconclusive"


FetchIssuePageResult = Annotated[ExternalIssuePage | FetchFailure, Field(discriminator="kind")]
CloseExternalIssueResult = Annotated[
    ConnectorReceipt | CloseFailure | AmbiguousWrite,
    Field(discriminator="kind"),
]


class IssueConnector(Protocol):
    """The frozen two-method connector plug point; no persistence or authority enters it."""

    def fetch_page(
        self, request: FetchIssuePage, attempt: ConnectorAttempt
    ) -> FetchIssuePageResult: ...

    def comment_and_close(
        self, command: CloseExternalIssue, attempt: ConnectorAttempt
    ) -> CloseExternalIssueResult: ...


class ConnectorLabelMapping(_StrictValue):
    source: str = Field(min_length=1, max_length=_MAX_LABEL_LENGTH)
    target: str = Field(pattern=_LABEL_PATTERN)


class ConnectorRegistration(_StrictValue):
    """One immutable Catalog registration plus provider-neutral core policy."""

    registration_key: str = Field(pattern=_KEY_PATTERN)
    revision_id: UUID
    revision_digest: str = Field(pattern=_DIGEST_PATTERN)
    connector_kind: str = Field(pattern=_KEY_PATTERN, max_length=_MAX_CONNECTOR_KIND_LENGTH)
    source_display_name: str = Field(min_length=1, max_length=64)
    project_key: str = Field(pattern=_PROJECT_PATTERN)
    initial_custodian_id: UUID
    initial_cursor: ConnectorCursorToken
    page_size: int = Field(ge=1, le=_MAX_PAGE_SIZE)
    poll_interval: timedelta
    label_map: tuple[ConnectorLabelMapping, ...] = Field(max_length=_MAX_LABELS)

    @model_validator(mode="after")
    def _registration_is_bounded(self) -> ConnectorRegistration:
        seconds = self.poll_interval.total_seconds()
        if not _MIN_POLL_SECONDS <= seconds <= _MAX_POLL_SECONDS:
            raise ValueError("connector poll interval must be between 15 and 3600 seconds")
        sources = tuple(item.source for item in self.label_map)
        if len(set(sources)) != len(sources):
            raise ValueError("connector label mappings must be source-unique")
        return self

    def label_key(self, source: str) -> str | None:
        return next((item.target for item in self.label_map if item.source == source), None)

    def to_mapping(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class ConnectorClaim(_StrictValue):
    cursor: ConnectorCursorToken
    project_event_cursor: int = Field(ge=0)
    owner_id: UUID
    fence: int = Field(ge=1)
    expires_at: datetime

    @model_validator(mode="after")
    def _expiry_is_aware(self) -> ConnectorClaim:
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("connector claim expiry must be timezone-aware")
        return self


class ConnectorLink(_StrictValue):
    tenant_id: UUID
    registration_key: str = Field(pattern=_KEY_PATTERN)
    revision_digest: str = Field(pattern=_DIGEST_PATTERN)
    connector_kind: str = Field(pattern=_KEY_PATTERN, max_length=_MAX_CONNECTOR_KIND_LENGTH)
    external_ref: str = Field(min_length=1, max_length=_MAX_EXTERNAL_REF_LENGTH)
    ticket_id: UUID
    thread_id: UUID
    display_url: str


class ConnectorSyncBatch(_StrictValue):
    claimed: bool
    issues_seen: int = Field(default=0, ge=0, le=_MAX_PAGE_SIZE)
    tickets_created: int = Field(default=0, ge=0, le=_MAX_PAGE_SIZE)
    ticket_updates: int = Field(default=0, ge=0, le=_MAX_PAGE_SIZE)
    closures_delivered: int = Field(default=0, ge=0, le=_MAX_PAGE_SIZE)


class ConnectorSyncError(RuntimeError):
    """One provider, persistence, or authoritative-command tick failure."""


class ConnectorStore(Protocol):
    """Provider-neutral progress, custody, observations, and delivery receipts."""

    def claim(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        *,
        owner_id: UUID,
        now: datetime,
    ) -> ConnectorClaim | None: ...

    def issue_link(
        self, actor: Actor, registration: ConnectorRegistration, external_ref: str
    ) -> ConnectorLink | None: ...

    def ticket_link(
        self, actor: Actor, registration: ConnectorRegistration, ticket_id: UUID
    ) -> ConnectorLink | None: ...

    def latest_issue(
        self, actor: Actor, registration: ConnectorRegistration, external_ref: str
    ) -> ExternalIssue | None: ...

    def record_issue(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        ticket_id: UUID,
        thread_id: UUID,
        observed_at: datetime,
    ) -> None: ...

    def record_observation(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        observed_at: datetime,
    ) -> None: ...

    def delivered(
        self, actor: Actor, registration: ConnectorRegistration, command_id: UUID
    ) -> bool: ...

    def record_delivery(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        link: ConnectorLink,
        receipt: ConnectorReceipt,
        *,
        delivered_at: datetime,
    ) -> None: ...

    def complete(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        cursor: ConnectorCursorToken,
        project_event_cursor: int,
        *,
        now: datetime,
    ) -> None: ...

    def fail(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        *,
        now: datetime,
    ) -> None: ...


def _validate_failure_pair(retry_class: RetryClass, reason: FailureReason) -> None:
    if (retry_class == "retryable" and reason not in _RETRYABLE_REASONS) or (
        retry_class == "terminal" and reason not in _TERMINAL_REASONS
    ):
        raise ValueError("connector failure reason does not match its retry class")
