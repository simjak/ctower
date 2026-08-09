"""Test-only mappings for the byte-frozen #377 regression traces."""

from modules.integrations._legacy_gitlab_shims.adapter import GitLabHttpAdapter
from modules.integrations._legacy_gitlab_shims.postgres import (
    PostgresGitLabIntegrationStore,
)
from modules.integrations._legacy_gitlab_shims.runtime import GitLabRuntimeRevision
from modules.integrations._legacy_gitlab_shims.service import GitLabIssueSync
from modules.integrations._legacy_gitlab_shims.values import (
    GitLabCloseCommand,
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIntegrationStore,
    GitLabIssue,
    GitLabIssueAdapter,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabReporter,
    GitLabSyncBatch,
    GitLabSyncBinding,
    GitLabSyncClaim,
    GitLabSyncError,
)

__all__ = [
    "GitLabCloseCommand",
    "GitLabCloseReceipt",
    "GitLabCursor",
    "GitLabHttpAdapter",
    "GitLabIntegrationStore",
    "GitLabIssue",
    "GitLabIssueAdapter",
    "GitLabIssueLink",
    "GitLabIssuePage",
    "GitLabIssueSync",
    "GitLabReporter",
    "GitLabRuntimeRevision",
    "GitLabSyncBatch",
    "GitLabSyncBinding",
    "GitLabSyncClaim",
    "GitLabSyncError",
    "PostgresGitLabIntegrationStore",
]
