"""Frozen #377 store shape mapped onto the real provider-neutral store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from ctower_kernel.integrations.interface import ConnectorSyncError
from ctower_kernel.integrations.postgres import PostgresConnectorStore
from ctower_kernel.record import Actor
from modules.integrations._legacy_gitlab_shims.values import (
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueLink,
    GitLabSyncBinding,
    GitLabSyncClaim,
    GitLabSyncError,
    _connector_claim,
    _connector_link,
    _connector_receipt,
    _cursor_token,
    _external_issue,
    _gitlab_claim,
    _gitlab_issue,
    _gitlab_link,
    _registration,
)

__all__ = ["PostgresGitLabIntegrationStore"]


class PostgresGitLabIntegrationStore:
    """Translate the frozen trace calls into the real generic persistence interface."""

    def __init__(self, dsn: str) -> None:
        self._store = PostgresConnectorStore(dsn)

    def claim(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        *,
        owner_id: UUID,
        now: datetime,
    ) -> GitLabSyncClaim | None:
        claim = self._call(
            self._store.claim,
            actor,
            _registration(binding),
            owner_id=owner_id,
            now=now,
        )
        return _gitlab_claim(claim) if claim is not None else None

    def active_revision_id(
        self,
        actor: Actor,
        *,
        integration_key: str,
        revision_digest: str,
    ) -> UUID | None:
        return self._call(
            self._store.active_revision_id,
            actor,
            registration_key=integration_key,
            revision_digest=revision_digest,
        )

    def issue_link(
        self, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssueLink | None:
        link = self._call(
            self._store.issue_link,
            actor,
            _registration(binding),
            f"gitlab:{binding.project_id}:{issue_iid}",
        )
        return _gitlab_link(link) if link is not None else None

    def ticket_link(
        self, actor: Actor, binding: GitLabSyncBinding, ticket_id: UUID
    ) -> GitLabIssueLink | None:
        link = self._call(self._store.ticket_link, actor, _registration(binding), ticket_id)
        return _gitlab_link(link) if link is not None else None

    def latest_issue(
        self, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssue | None:
        issue = self._call(
            self._store.latest_issue,
            actor,
            _registration(binding),
            f"gitlab:{binding.project_id}:{issue_iid}",
        )
        return _gitlab_issue(issue) if issue is not None else None

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
        self._call(
            self._store.record_issue,
            actor,
            _registration(binding),
            _external_issue(issue),
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
        self._call(
            self._store.record_observation,
            actor,
            _registration(binding),
            _external_issue(issue),
            observed_at=observed_at,
        )

    def delivered(self, actor: Actor, binding: GitLabSyncBinding, event_id: UUID) -> bool:
        return self._call(self._store.delivered, actor, _registration(binding), event_id)

    def record_delivery(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        link: GitLabIssueLink,
        receipt: GitLabCloseReceipt,
        *,
        delivered_at: datetime,
    ) -> None:
        self._call(
            self._store.record_delivery,
            actor,
            _registration(binding),
            _connector_link(link),
            _connector_receipt(receipt),
            delivered_at=delivered_at,
        )

    def complete(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        claim: GitLabSyncClaim,
        cursor: GitLabCursor,
        *,
        now: datetime,
    ) -> None:
        self._call(
            self._store.complete,
            actor,
            _registration(binding),
            _connector_claim(claim),
            _cursor_token(cursor),
            cursor.project_event_cursor,
            now=now,
        )

    def fail(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        claim: GitLabSyncClaim,
        *,
        now: datetime,
    ) -> None:
        self._call(
            self._store.fail,
            actor,
            _registration(binding),
            _connector_claim(claim),
            now=now,
        )

    @staticmethod
    def _call[**P, R](operation: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return operation(*args, **kwargs)
        except ConnectorSyncError as error:
            raise GitLabSyncError(str(error).replace("connector", "GitLab")) from error
