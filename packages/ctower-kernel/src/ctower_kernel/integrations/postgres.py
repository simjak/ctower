"""PostgreSQL implementation of the GitLab integration Store Interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.integrations import _postgres_sql
from ctower_kernel.integrations.interface import (
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueLink,
    GitLabSyncBinding,
)
from ctower_kernel.record import Actor

__all__ = ["PostgresGitLabIntegrationStore"]


class PostgresGitLabIntegrationStore:
    """Persist immutable custody/receipts plus mutable bounded sync progress."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def claim(
        self, actor: Actor, binding: GitLabSyncBinding, *, now: datetime
    ) -> GitLabCursor | None:
        return _postgres_sql.claim(self._dsn, actor, binding, now=now)

    def issue_link(
        self, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssueLink | None:
        return _postgres_sql.issue_link(self._dsn, actor, binding, issue_iid)

    def ticket_link(
        self, actor: Actor, binding: GitLabSyncBinding, ticket_id: UUID
    ) -> GitLabIssueLink | None:
        return _postgres_sql.ticket_link(self._dsn, actor, binding, ticket_id)

    def latest_issue(
        self, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssue | None:
        return _postgres_sql.latest_issue(self._dsn, actor, binding, issue_iid)

    def record_issue(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        issue: GitLabIssue,
        *,
        ticket_id: UUID,
        thread_id: UUID,
        observed_at: datetime,
    ) -> None:
        _postgres_sql.record_issue(
            self._dsn,
            actor,
            binding,
            issue,
            ticket_id=ticket_id,
            thread_id=thread_id,
            observed_at=observed_at,
        )

    def record_observation(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        issue: GitLabIssue,
        *,
        observed_at: datetime,
    ) -> None:
        _postgres_sql.record_observation(self._dsn, actor, binding, issue, observed_at=observed_at)

    def delivered(self, actor: Actor, binding: GitLabSyncBinding, event_id: UUID) -> bool:
        return _postgres_sql.delivered(self._dsn, actor, binding, event_id)

    def record_delivery(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        link: GitLabIssueLink,
        receipt: GitLabCloseReceipt,
        *,
        delivered_at: datetime,
    ) -> None:
        _postgres_sql.record_delivery(
            self._dsn,
            actor,
            binding,
            link,
            receipt,
            delivered_at=delivered_at,
        )

    def complete(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        cursor: GitLabCursor,
        *,
        now: datetime,
    ) -> None:
        _postgres_sql.complete(self._dsn, actor, binding, cursor, now=now)

    def fail(self, actor: Actor, binding: GitLabSyncBinding, *, now: datetime) -> None:
        _postgres_sql.fail(self._dsn, actor, binding, now=now)
