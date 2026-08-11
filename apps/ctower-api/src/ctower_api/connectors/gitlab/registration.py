"""Catalog parsing and static factory for the GitLab issue connector."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ctower_api.connectors.gitlab.adapter import GitLabCursor, GitLabIssueConnector
from ctower_api.connectors.gitlab.config import GitLabConnectorConfig
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import (
    ConnectorCursorToken,
    ConnectorLabelMapping,
    ConnectorRegistration,
)

__all__ = ["GitLabRuntimeRegistration"]


class _GitLabSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    base_url: str
    project_id: int = Field(ge=1)
    import_updated_after: datetime
    page_size: int = Field(ge=1, le=100)
    poll_interval_seconds: int = Field(ge=15, le=3600)


class _CtowerSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_key: str
    initial_custodian_id: UUID


class _LabelMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    gitlab: str
    ctower: str


class _IntegrationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_: Literal["ctower.integration/v2"] = Field(alias="schema")
    key: str
    adapter: Literal["gitlab-issues"]
    authority: Literal["co_source"]
    execution: Literal["standing_sync"]
    gitlab: _GitLabSection
    ctower: _CtowerSection
    label_map: tuple[_LabelMapping, ...] = Field(max_length=100)
    token_binding: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")


@dataclass(frozen=True, slots=True)
class GitLabRuntimeRegistration:
    """Validated provider config plus provider-neutral core registration."""

    adapter_kind: ClassVar[str] = "gitlab-issues"
    schema_ref: ClassVar[str] = "ctower.integration/v2"

    config: GitLabConnectorConfig
    token_binding: str
    registration: ConnectorRegistration

    @classmethod
    def from_catalog(
        cls,
        payload: dict[str, JsonValue],
        *,
        revision_id: UUID,
        revision_digest: str,
    ) -> GitLabRuntimeRegistration:
        parsed = _IntegrationPayload.model_validate_json(json.dumps(payload))
        gitlab = parsed.gitlab
        ctower = parsed.ctower
        config = GitLabConnectorConfig(
            base_url=gitlab.base_url,
            project_id=gitlab.project_id,
        )
        return cls(
            config=config,
            token_binding=parsed.token_binding,
            registration=ConnectorRegistration(
                registration_key=parsed.key,
                revision_id=revision_id,
                revision_digest=revision_digest,
                connector_kind="gitlab-issue",
                source_display_name="GitLab",
                project_key=ctower.project_key,
                initial_custodian_id=ctower.initial_custodian_id,
                initial_cursor=ConnectorCursorToken(
                    value=GitLabCursor(
                        updated_after=gitlab.import_updated_after,
                        page=1,
                    ).encode()
                ),
                page_size=gitlab.page_size,
                poll_interval=timedelta(seconds=gitlab.poll_interval_seconds),
                label_map=tuple(
                    ConnectorLabelMapping(source=item.gitlab, target=item.ctower)
                    for item in parsed.label_map
                ),
            ),
        )

    def build(self, resolve_secret: Callable[[str], str]) -> GitLabIssueConnector:
        return GitLabIssueConnector(self.config, token=resolve_secret(self.token_binding))
