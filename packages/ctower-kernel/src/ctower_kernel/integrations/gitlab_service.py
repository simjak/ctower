"""Protected #377 service facade backed by the provider-neutral connector core."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from ctower_kernel.integrations.gitlab import (
    GitLabIntegrationStore,
    GitLabIssueAdapter,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabSyncBatch,
    GitLabSyncBinding,
    GitLabSyncError,
    _close_command,
    _connector_claim,
    _connector_link,
    _connector_receipt,
    _cursor_token,
    _external_identity,
    _external_issue,
    _gitlab_claim,
    _gitlab_cursor,
    _gitlab_issue,
    _gitlab_link,
    _gitlab_receipt,
    _registration,
)
from ctower_kernel.integrations.interface import (
    CloseExternalIssue,
    CloseExternalIssueResult,
    ConnectorAttempt,
    ConnectorClaim,
    ConnectorCursorToken,
    ConnectorLink,
    ConnectorReceipt,
    ConnectorRegistration,
    ConnectorSyncError,
    ExternalIssue,
    ExternalIssuePage,
    FetchIssuePage,
    FetchIssuePageResult,
)
from ctower_kernel.integrations.service import IssueConnectorService
from ctower_kernel.record import Actor

__all__ = ["GitLabIssueSync"]


class _GitLabConnectorFacade:
    def __init__(
        self,
        adapter: GitLabIssueAdapter,
        store: GitLabIntegrationStore,
        actor: Actor,
        binding: GitLabSyncBinding,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._actor = actor
        self._binding = binding
        self.error: GitLabSyncError | None = None

    def fetch_page(
        self, request: FetchIssuePage, _attempt: ConnectorAttempt
    ) -> FetchIssuePageResult:
        try:
            cursor = _gitlab_cursor(request.cursor, 0)
            page = self._adapter.list_issues(self._binding, cursor)
            _require_bound_project(page, self._binding)
            watermark = max(
                (issue.updated_at for issue in page.issues),
                default=cursor.updated_after,
            )
            if page.next_page is None and page.issues:
                watermark = max(
                    watermark + timedelta(microseconds=1),
                    cursor.updated_after + timedelta(microseconds=1),
                )
            next_cursor = _cursor_token(
                type(cursor)(
                    updated_after=watermark,
                    page=page.next_page or 1,
                    project_event_cursor=0,
                )
            )
            return ExternalIssuePage(
                issues=tuple(_external_issue(issue) for issue in page.issues),
                next_cursor=next_cursor,
                exhausted=page.next_page is None,
            )
        except GitLabSyncError as error:
            self.error = error
            raise

    def comment_and_close(
        self, command: CloseExternalIssue, _attempt: ConnectorAttempt
    ) -> CloseExternalIssueResult:
        try:
            _project_id, issue_iid = _external_identity(command.external_ref)
            link = self._store.issue_link(self._actor, self._binding, issue_iid)
            link = _require_link(link)
            receipt = self._adapter.comment_and_close(link, _close_command(command))
            return _connector_receipt(receipt)
        except GitLabSyncError as error:
            self.error = error
            raise


class _GitLabStoreFacade:
    def __init__(self, store: GitLabIntegrationStore, binding: GitLabSyncBinding) -> None:
        self._store = store
        self._binding = binding

    def claim(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        *,
        owner_id: UUID,
        now: datetime,
    ) -> ConnectorClaim | None:
        del registration
        claim = self._store.claim(actor, self._binding, owner_id=owner_id, now=now)
        return _connector_claim(claim) if claim is not None else None

    def issue_link(
        self, actor: Actor, registration: ConnectorRegistration, external_ref: str
    ) -> ConnectorLink | None:
        _project_id, issue_iid = _external_identity(external_ref)
        del registration
        link = self._store.issue_link(actor, self._binding, issue_iid)
        return _connector_link(link) if link is not None else None

    def ticket_link(
        self, actor: Actor, registration: ConnectorRegistration, ticket_id: UUID
    ) -> ConnectorLink | None:
        del registration
        link = self._store.ticket_link(actor, self._binding, ticket_id)
        return _connector_link(link) if link is not None else None

    def latest_issue(
        self, actor: Actor, registration: ConnectorRegistration, external_ref: str
    ) -> ExternalIssue | None:
        _project_id, issue_iid = _external_identity(external_ref)
        del registration
        issue = self._store.latest_issue(actor, self._binding, issue_iid)
        return _external_issue(issue) if issue is not None else None

    def record_issue(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        ticket_id: UUID,
        thread_id: UUID,
        observed_at: datetime,
    ) -> None:
        del registration
        self._store.record_issue(
            actor,
            self._binding,
            _gitlab_issue(issue),
            ticket_id=ticket_id,
            thread_id=thread_id,
            observed_at=observed_at,
        )

    def record_observation(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        observed_at: datetime,
    ) -> None:
        del registration
        self._store.record_observation(
            actor,
            self._binding,
            _gitlab_issue(issue),
            observed_at=observed_at,
        )

    def delivered(
        self, actor: Actor, registration: ConnectorRegistration, command_id: UUID
    ) -> bool:
        del registration
        return self._store.delivered(actor, self._binding, command_id)

    def record_delivery(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        link: ConnectorLink,
        receipt: ConnectorReceipt,
        *,
        delivered_at: datetime,
    ) -> None:
        del registration
        self._store.record_delivery(
            actor,
            self._binding,
            _gitlab_link(link),
            _gitlab_receipt(receipt),
            delivered_at=delivered_at,
        )

    def complete(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        cursor: ConnectorCursorToken,
        project_event_cursor: int,
        *,
        now: datetime,
    ) -> None:
        del registration
        self._store.complete(
            actor,
            self._binding,
            _gitlab_claim(claim),
            _gitlab_cursor(cursor, project_event_cursor),
            now=now,
        )

    def fail(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        *,
        now: datetime,
    ) -> None:
        del registration
        self._store.fail(actor, self._binding, _gitlab_claim(claim), now=now)


class GitLabIssueSync:
    """Keep the #377 calling seam while executing the extracted neutral service."""

    def __init__(
        self,
        adapter: GitLabIssueAdapter,
        store: GitLabIntegrationStore,
        intake: object,
        comments: object,
        event_audit: object,
        board_context: object,
        *,
        clock: Callable[[], datetime] | None = None,
        claim_owner: UUID | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._intake = intake
        self._comments = comments
        self._event_audit = event_audit
        self._board_context = board_context
        self._clock = clock
        self._claim_owner = claim_owner

    def tick(self, actor: Actor, binding: GitLabSyncBinding) -> GitLabSyncBatch:
        connector = _GitLabConnectorFacade(self._adapter, self._store, actor, binding)
        service = IssueConnectorService(
            connector,
            _GitLabStoreFacade(self._store, binding),
            self._intake,  # type: ignore[arg-type]
            self._comments,  # type: ignore[arg-type]
            self._event_audit,  # type: ignore[arg-type]
            self._board_context,  # type: ignore[arg-type]
            clock=self._clock,
            claim_owner=self._claim_owner,
        )
        try:
            result = service.tick(actor, _registration(binding))
        except ConnectorSyncError as error:
            if connector.error is not None:
                raise connector.error from error
            raise GitLabSyncError(str(error)) from error
        return GitLabSyncBatch(
            claimed=result.claimed,
            issues_seen=result.issues_seen,
            tickets_created=result.tickets_created,
            ticket_updates=result.ticket_updates,
            closures_delivered=result.closures_delivered,
        )


def _require_bound_project(page: GitLabIssuePage, binding: GitLabSyncBinding) -> None:
    if any(issue.project_id != binding.project_id for issue in page.issues):
        raise GitLabSyncError("GitLab Adapter returned an issue from another project")


def _require_link(link: GitLabIssueLink | None) -> GitLabIssueLink:
    if link is None:
        raise GitLabSyncError("GitLab close command has no custody link")
    return link
