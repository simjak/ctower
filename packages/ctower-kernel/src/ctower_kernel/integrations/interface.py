"""Strict values and small Interfaces for the GitLab issue integration Seam."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from ctower_kernel.record import Actor

__all__ = [
    "GitLabCloseCommand",
    "GitLabCloseReceipt",
    "GitLabCursor",
    "GitLabIntegrationStore",
    "GitLabIssue",
    "GitLabIssueAdapter",
    "GitLabIssueLink",
    "GitLabIssuePage",
    "GitLabReporter",
    "GitLabSyncBatch",
    "GitLabSyncBinding",
    "GitLabSyncClaim",
    "GitLabSyncError",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_INTEGRATION_KEY = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_LABEL_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{1,255}$")
_MAX_BODY_LENGTH = 60_000
_MAX_CLOSE_COMMENT_LENGTH = 4000
_MAX_LABELS = 100
_MAX_LABEL_LENGTH = 255
_MAX_PAGE_SIZE = 100
_MAX_POLL_SECONDS = 3600
_MAX_REPORTER_NAME_LENGTH = 255
_MAX_TITLE_LENGTH = 200
_MIN_POLL_SECONDS = 15
_SECOND_PAGE = 2


class GitLabSyncError(RuntimeError):
    """One provider, persistence, or authoritative-command sync failure."""


@dataclass(frozen=True, slots=True)
class GitLabReporter:
    username: str
    name: str

    def __post_init__(self) -> None:
        if (
            _USERNAME.fullmatch(self.username) is None
            or not 1 <= len(self.name) <= _MAX_REPORTER_NAME_LENGTH
        ):
            raise ValueError("GitLab reporter is outside the authored contract")

    def to_mapping(self) -> dict[str, str]:
        return {"username": self.username, "name": self.name}


@dataclass(frozen=True, slots=True)
class GitLabIssue:
    """Normalized provider issue; no provider-only fields cross the Seam."""

    project_id: int
    iid: int
    title: str
    body: str
    labels: tuple[str, ...]
    reporter: GitLabReporter
    state: str
    web_url: str
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_issue_identity(self)
        _validate_issue_content(self)
        _validate_issue_labels(self.labels)
        _validate_issue_source(self)

    @property
    def source_ref(self) -> str:
        return f"gitlab:{self.project_id}:{self.iid}"

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": "ctower.gitlab-issue/v1",
            "project_id": self.project_id,
            "iid": self.iid,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
            "reporter": self.reporter.to_mapping(),
            "state": self.state,
            "web_url": self.web_url,
            "updated_at": self.updated_at.isoformat(),
        }


def _validate_issue_identity(issue: GitLabIssue) -> None:
    if isinstance(issue.project_id, bool) or issue.project_id < 1:
        raise ValueError("GitLab project identity is outside the authored contract")
    if isinstance(issue.iid, bool) or issue.iid < 1:
        raise ValueError("GitLab issue identity is outside the authored contract")


def _validate_issue_content(issue: GitLabIssue) -> None:
    if not 1 <= len(issue.title) <= _MAX_TITLE_LENGTH or len(issue.body) > _MAX_BODY_LENGTH:
        raise ValueError("GitLab issue content is outside the authored contract")
    if issue.state not in {"opened", "closed"}:
        raise ValueError("GitLab issue state is outside the authored contract")


def _validate_issue_labels(labels: tuple[str, ...]) -> None:
    if (
        len(labels) > _MAX_LABELS
        or len(set(labels)) != len(labels)
        or any(not 1 <= len(label) <= _MAX_LABEL_LENGTH for label in labels)
    ):
        raise ValueError("GitLab labels are outside the authored contract")


def _validate_issue_source(issue: GitLabIssue) -> None:
    url = urlsplit(issue.web_url)
    if url.scheme != "https" or not url.hostname:
        raise ValueError("GitLab issue URL must be absolute HTTPS")
    if issue.updated_at.tzinfo is None or issue.updated_at.utcoffset() is None:
        raise ValueError("GitLab issue updated_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class GitLabSyncBinding:
    """One immutable Catalog integration revision, with no resolved secret value."""

    integration_key: str
    revision_id: UUID
    revision_digest: str
    project_id: int
    project_key: str
    initial_custodian_id: UUID
    import_updated_after: datetime
    page_size: int
    poll_interval: timedelta
    label_map: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _validate_binding_identity(self)
        _validate_binding_cursor(self)
        _validate_label_map(self.label_map)

    def label_key(self, source: str) -> str | None:
        return dict(self.label_map).get(source)

    def to_mapping(self) -> dict[str, object]:
        return {
            "integration_key": self.integration_key,
            "revision_id": str(self.revision_id),
            "revision_digest": self.revision_digest,
            "project_id": self.project_id,
            "project_key": self.project_key,
            "initial_custodian_id": str(self.initial_custodian_id),
            "import_updated_after": self.import_updated_after.isoformat(),
            "page_size": self.page_size,
            "poll_interval_seconds": int(self.poll_interval.total_seconds()),
            "label_map": [
                {"gitlab": source, "ctower": target} for source, target in self.label_map
            ],
        }


def _validate_binding_identity(binding: GitLabSyncBinding) -> None:
    if _INTEGRATION_KEY.fullmatch(binding.integration_key) is None:
        raise ValueError("GitLab integration key is outside the authored contract")
    if not isinstance(binding.revision_id, UUID):
        raise TypeError("GitLab integration revision identity must be a UUID")
    if _DIGEST.fullmatch(binding.revision_digest) is None:
        raise ValueError("GitLab integration revision must be content addressed")
    if isinstance(binding.project_id, bool) or binding.project_id < 1:
        raise ValueError("GitLab project identity is outside the authored contract")
    if _PROJECT_KEY.fullmatch(binding.project_key) is None:
        raise ValueError("GitLab ctower project key is outside the authored contract")


def _validate_binding_cursor(binding: GitLabSyncBinding) -> None:
    if binding.import_updated_after.tzinfo is None:
        raise ValueError("GitLab import cursor must be timezone-aware")
    if not 1 <= binding.page_size <= _MAX_PAGE_SIZE:
        raise ValueError("GitLab page size must be between 1 and 100")
    if not _MIN_POLL_SECONDS <= binding.poll_interval.total_seconds() <= _MAX_POLL_SECONDS:
        raise ValueError("GitLab poll interval must be between 15 and 3600 seconds")


def _validate_label_map(label_map: tuple[tuple[str, str], ...]) -> None:
    gitlab_labels = tuple(source for source, _target in label_map)
    if len(label_map) > _MAX_LABELS or len(set(gitlab_labels)) != len(gitlab_labels):
        raise ValueError("GitLab label mappings must be bounded and source-unique")
    if any(
        not 1 <= len(source) <= _MAX_LABEL_LENGTH or _LABEL_KEY.fullmatch(target) is None
        for source, target in label_map
    ):
        raise ValueError("GitLab label mapping is outside the authored contract")


@dataclass(frozen=True, slots=True)
class GitLabCursor:
    updated_after: datetime
    page: int
    project_event_cursor: int

    def __post_init__(self) -> None:
        if self.updated_after.tzinfo is None or self.updated_after.utcoffset() is None:
            raise ValueError("GitLab cursor must be timezone-aware")
        if self.page < 1 or self.project_event_cursor < 0:
            raise ValueError("GitLab cursor positions must be non-negative")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": "ctower.gitlab-issue-cursor/v1",
            "updated_after": self.updated_after.isoformat(),
            "page": self.page,
            "project_event_cursor": self.project_event_cursor,
        }


@dataclass(frozen=True, slots=True)
class GitLabSyncClaim:
    """One durable owner/fence lease over a cursor snapshot."""

    cursor: GitLabCursor
    owner_id: UUID
    fence: int
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, UUID) or self.fence < 1:
            raise ValueError("GitLab claim owner and fence are invalid")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("GitLab claim expiry must be timezone-aware")


@dataclass(frozen=True, slots=True)
class GitLabIssuePage:
    issues: tuple[GitLabIssue, ...]
    next_page: int | None

    def __post_init__(self) -> None:
        if self.next_page is not None and self.next_page < _SECOND_PAGE:
            raise ValueError("GitLab next page must advance")


@dataclass(frozen=True, slots=True)
class GitLabIssueLink:
    tenant_id: UUID
    integration_key: str
    revision_digest: str
    project_id: int
    issue_iid: int
    ticket_id: UUID
    thread_id: UUID
    web_url: str

    @property
    def source_ref(self) -> str:
        return f"gitlab:{self.project_id}:{self.issue_iid}"


@dataclass(frozen=True, slots=True)
class GitLabCloseCommand:
    delivery_id: UUID
    comment: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.comment) <= _MAX_CLOSE_COMMENT_LENGTH or not self.comment.strip():
            raise ValueError("GitLab close comment is outside the authored contract")

    @property
    def marker(self) -> str:
        return f"<!-- ctower-sync:{self.delivery_id} -->"

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": "ctower.gitlab-close-command/v1",
            "delivery_id": str(self.delivery_id),
            "comment": self.comment,
        }


@dataclass(frozen=True, slots=True)
class GitLabCloseReceipt:
    delivery_id: UUID
    comment_created: bool
    issue_closed: bool

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": "ctower.gitlab-close-receipt/v1",
            "delivery_id": str(self.delivery_id),
            "comment_created": self.comment_created,
            "issue_closed": self.issue_closed,
        }


@dataclass(frozen=True, slots=True)
class GitLabSyncBatch:
    claimed: bool
    issues_seen: int = 0
    tickets_created: int = 0
    ticket_updates: int = 0
    closures_delivered: int = 0


class GitLabIssueAdapter(Protocol):
    """Provider Seam implemented by one real HTTP Adapter and test fakes."""

    def list_issues(self, binding: GitLabSyncBinding, cursor: GitLabCursor) -> GitLabIssuePage: ...

    def comment_and_close(
        self, link: GitLabIssueLink, command: GitLabCloseCommand
    ) -> GitLabCloseReceipt: ...


class GitLabIntegrationStore(Protocol):
    """Durable links, observations, delivery receipts, and bounded cursor coordination."""

    def claim(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        *,
        owner_id: UUID,
        now: datetime,
    ) -> GitLabSyncClaim | None: ...

    def issue_link(
        self, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssueLink | None: ...

    def ticket_link(
        self, actor: Actor, binding: GitLabSyncBinding, ticket_id: UUID
    ) -> GitLabIssueLink | None: ...

    def latest_issue(
        self, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssue | None: ...

    def record_issue(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        issue: GitLabIssue,
        *,
        ticket_id: UUID,
        thread_id: UUID,
        observed_at: datetime,
    ) -> None: ...

    def record_observation(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        issue: GitLabIssue,
        *,
        observed_at: datetime,
    ) -> None: ...

    def delivered(self, actor: Actor, binding: GitLabSyncBinding, event_id: UUID) -> bool: ...

    def record_delivery(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        link: GitLabIssueLink,
        receipt: GitLabCloseReceipt,
        *,
        delivered_at: datetime,
    ) -> None: ...

    def complete(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        claim: GitLabSyncClaim,
        cursor: GitLabCursor,
        *,
        now: datetime,
    ) -> None: ...

    def fail(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        claim: GitLabSyncClaim,
        *,
        now: datetime,
    ) -> None: ...
