"""Narrow exports for the first-party GitLab issue connector."""

from ctower_api.connectors.gitlab.adapter import GitLabCursor, GitLabIssueConnector
from ctower_api.connectors.gitlab.config import GitLabConnectorConfig
from ctower_api.connectors.gitlab.registration import GitLabRuntimeRegistration

__all__ = [
    "GitLabConnectorConfig",
    "GitLabCursor",
    "GitLabIssueConnector",
    "GitLabRuntimeRegistration",
]
