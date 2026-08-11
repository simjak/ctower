"""Catalog parsing and static factory for the GitHub App Issue connector."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ctower_api.connectors.github.adapter import GitHubCursor, GitHubIssueConnector
from ctower_api.connectors.github.auth import GitHubAppAuth
from ctower_api.connectors.github.config import GitHubConnectorConfig
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import (
    ConnectorCursorToken,
    ConnectorLabelMapping,
    ConnectorRegistration,
)

__all__ = ["GitHubRuntimeRegistration"]


class _StrictValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _Permissions(_StrictValue):
    issues: Literal["write"]
    metadata: Literal["read"]


class _GitHubSection(_StrictValue):
    app_client_id: str
    installation_id: int = Field(ge=1)
    repository_id: int = Field(ge=1)
    repository_owner: str
    repository_name: str
    private_key_binding_revision: str
    repository_selection: Literal["selected"]
    permissions: _Permissions
    import_updated_after: datetime
    page_size: int = Field(ge=1, le=100)
    poll_interval_seconds: int = Field(ge=15, le=3600)


class _CtowerSection(_StrictValue):
    project_key: str
    initial_custodian_id: UUID


class _LabelMapping(_StrictValue):
    github: str
    ctower: str


class _IntegrationPayload(_StrictValue):
    schema_: Literal["ctower.integration/v3"] = Field(alias="schema")
    key: str
    adapter: Literal["github-issues"]
    authority: Literal["co_source"]
    execution: Literal["standing_sync"]
    github: _GitHubSection
    ctower: _CtowerSection
    label_map: tuple[_LabelMapping, ...] = Field(max_length=100)
    private_key_binding: str


@dataclass(frozen=True, slots=True)
class GitHubRuntimeRegistration:
    """Validated provider config plus the unchanged provider-neutral registration."""

    adapter_kind: ClassVar[str] = "github-issues"
    schema_ref: ClassVar[str] = "ctower.integration/v3"

    config: GitHubConnectorConfig
    private_key_binding: str
    registration: ConnectorRegistration

    @property
    def token_binding(self) -> str:
        """Expose the one deployment secret reference through the frozen registry protocol."""

        return self.private_key_binding

    @classmethod
    def from_catalog(
        cls,
        payload: dict[str, JsonValue],
        *,
        revision_id: UUID,
        revision_digest: str,
    ) -> GitHubRuntimeRegistration:
        parsed = _IntegrationPayload.model_validate_json(json.dumps(payload))
        github = parsed.github
        ctower = parsed.ctower
        config = GitHubConnectorConfig(
            app_client_id=github.app_client_id,
            installation_id=github.installation_id,
            repository_id=github.repository_id,
            repository_owner=github.repository_owner,
            repository_name=github.repository_name,
            private_key_binding=parsed.private_key_binding,
            private_key_binding_revision=github.private_key_binding_revision,
        )
        return cls(
            config=config,
            private_key_binding=parsed.private_key_binding,
            registration=ConnectorRegistration(
                registration_key=parsed.key,
                revision_id=revision_id,
                revision_digest=revision_digest,
                connector_kind="github-issue",
                source_display_name="GitHub",
                project_key=ctower.project_key,
                initial_custodian_id=ctower.initial_custodian_id,
                initial_cursor=ConnectorCursorToken(
                    value=GitHubCursor(
                        updated_at=github.import_updated_after,
                        issue_id=0,
                        page=1,
                    ).encode()
                ),
                page_size=github.page_size,
                poll_interval=timedelta(seconds=github.poll_interval_seconds),
                label_map=tuple(
                    ConnectorLabelMapping(source=item.github, target=item.ctower)
                    for item in parsed.label_map
                ),
            ),
        )

    def build(self, resolve_secret: Callable[[str], str]) -> GitHubIssueConnector:
        auth = GitHubAppAuth(
            self.config,
            resolve_private_key=lambda binding, revision: resolve_secret(
                _revision_secret_reference(binding, revision)
            ),
        )
        return GitHubIssueConnector(self.config, auth=auth)


def _revision_secret_reference(binding: str, revision: str) -> str:
    """Resolve one exact deployment key revision without accepting an old binding value."""

    return f"{binding}__SHA256_{revision.removeprefix('sha256:').upper()}"
