"""Protected #377 GitLab HTTP seam backed by the extracted connector."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import TracebackType
from typing import Self

import httpx

from ctower_api.connectors.gitlab.adapter import GitLabCursor as ConnectorGitLabCursor
from ctower_api.connectors.gitlab.adapter import GitLabIssueConnector
from ctower_api.connectors.gitlab.config import GitLabConnectorConfig
from ctower_kernel.integrations import (
    AmbiguousWrite,
    CloseExternalIssue,
    CloseFailure,
    ConnectorRetryExecutor,
    FetchFailure,
    FetchIssuePage,
    GitLabCloseCommand,
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabSyncBinding,
    GitLabSyncError,
)
from ctower_kernel.integrations.gitlab import (
    _cursor_token,
    _gitlab_issue,
    _gitlab_receipt,
)

__all__ = ["GitLabHttpAdapter"]

_MAX_CREDENTIAL_LENGTH = 2048


class GitLabHttpAdapter:
    """Expose the #377 operation shapes without duplicating provider transport."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        GitLabConnectorConfig(base_url=base_url, project_id=1)
        if not token or len(token) > _MAX_CREDENTIAL_LENGTH:
            raise ValueError("GitLab credential is unavailable")
        self._base_url = base_url
        self._token = token
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._owns_client = client is None
        self._monotonic = monotonic
        self._retry = ConnectorRetryExecutor(
            sleep=sleep,
            monotonic=monotonic,
            jitter=jitter,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_issues(self, binding: GitLabSyncBinding, cursor: GitLabCursor) -> GitLabIssuePage:
        connector = self._connector(binding.project_id)
        result = self._retry.fetch(
            connector,
            FetchIssuePage(cursor=_cursor_token(cursor), page_size=binding.page_size),
        )
        if isinstance(result, FetchFailure):
            diagnostic = connector.diagnostic
            if result.retry_class == "retryable":
                diagnostic = "GitLab GET retry exhausted"
            raise GitLabSyncError(diagnostic or "GitLab GET request failed")
        issues = tuple(_gitlab_issue(issue) for issue in result.issues)
        decoded = ConnectorGitLabCursor.decode(result.next_cursor)
        return GitLabIssuePage(issues, None if result.exhausted else decoded.page)

    def comment_and_close(
        self, link: GitLabIssueLink, command: GitLabCloseCommand
    ) -> GitLabCloseReceipt:
        connector = self._connector(link.project_id)
        result = self._retry.close(
            connector,
            CloseExternalIssue(
                external_ref=link.source_ref,
                command_id=command.delivery_id,
                marker=command.marker,
                comment=command.comment,
            ),
        )
        if isinstance(result, (CloseFailure, AmbiguousWrite)):
            diagnostic = connector.diagnostic or f"GitLab close failed: {result.kind}"
            if "wrong marker" in diagnostic:
                diagnostic = "GitLab note creation returned the wrong delivery marker"
            if "did not return closed state" in diagnostic:
                diagnostic = "GitLab issue close did not return the closed state"
            raise GitLabSyncError(diagnostic)
        return _gitlab_receipt(result)

    def _connector(self, project_id: int) -> GitLabIssueConnector:
        return GitLabIssueConnector(
            GitLabConnectorConfig(base_url=self._base_url, project_id=project_id),
            token=self._token,
            client=self._client,
            monotonic=self._monotonic,
        )
