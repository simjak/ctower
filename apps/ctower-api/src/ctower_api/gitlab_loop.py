"""Catalog-pinned standing composition for GitLab issue synchronization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ctower_api.gitlab_adapter import GitLabHttpAdapter
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import GitLabIssueSync, GitLabSyncBatch, GitLabSyncBinding
from ctower_kernel.integrations.postgres import PostgresGitLabIntegrationStore
from ctower_kernel.record import Actor
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Intake

__all__ = ["GitLabRuntimeRevision", "GitLabSyncLoop", "build_gitlab_sync_loop"]


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
class GitLabRuntimeRevision:
    """Validated Catalog revision plus an unresolved deployment secret reference."""

    base_url: str
    token_binding: str
    binding: GitLabSyncBinding

    @classmethod
    def from_catalog(
        cls,
        payload: dict[str, JsonValue],
        *,
        revision_id: UUID,
        revision_digest: str,
    ) -> GitLabRuntimeRevision:
        """Turn one already-published Catalog payload into typed runtime configuration."""

        parsed = _IntegrationPayload.model_validate_json(json.dumps(payload))
        gitlab = parsed.gitlab
        ctower = parsed.ctower
        return cls(
            base_url=gitlab.base_url,
            token_binding=parsed.token_binding,
            binding=GitLabSyncBinding(
                integration_key=parsed.key,
                revision_id=revision_id,
                revision_digest=revision_digest,
                project_id=gitlab.project_id,
                project_key=ctower.project_key,
                initial_custodian_id=ctower.initial_custodian_id,
                import_updated_after=gitlab.import_updated_after,
                page_size=gitlab.page_size,
                poll_interval=timedelta(seconds=gitlab.poll_interval_seconds),
                label_map=tuple((item.gitlab, item.ctower) for item in parsed.label_map),
            ),
        )


@dataclass(frozen=True, slots=True)
class GitLabSyncLoop:
    """One standing worker loop pinned to one immutable integration revision."""

    sync: GitLabIssueSync
    actor: Actor
    binding: GitLabSyncBinding

    def tick(self) -> GitLabSyncBatch:
        return self.sync.tick(self.actor, self.binding)


def build_gitlab_sync_loop(
    revision: GitLabRuntimeRevision,
    *,
    resolved_token: str,
    actor: Actor,
    runtime_dsn: str,
) -> GitLabSyncLoop:
    """Resolve a secret outside Catalog and compose the real standing Adapter path."""

    record = PostgresRecord(runtime_dsn)
    sync = GitLabIssueSync(
        GitLabHttpAdapter(revision.base_url, token=resolved_token),
        PostgresGitLabIntegrationStore(runtime_dsn),
        Intake(record),
        record,
        record.event_audit,
        BoardContextFacts(PostgresBoardContextFacts(runtime_dsn)),
    )
    return GitLabSyncLoop(sync, actor, revision.binding)
