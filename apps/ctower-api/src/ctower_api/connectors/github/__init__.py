"""Narrow exports for the first-party GitHub App Issue connector."""

from ctower_api.connectors.github.adapter import GitHubCursor, GitHubIssueConnector
from ctower_api.connectors.github.auth import GitHubAppAuth, GitHubAuthError
from ctower_api.connectors.github.config import GitHubConnectorConfig
from ctower_api.connectors.github.registration import GitHubRuntimeRegistration

__all__ = [
    "GitHubAppAuth",
    "GitHubAuthError",
    "GitHubConnectorConfig",
    "GitHubCursor",
    "GitHubIssueConnector",
    "GitHubRuntimeRegistration",
]
