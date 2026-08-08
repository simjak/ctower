"""Frozen #377 runtime shape mapped onto the real static registration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ctower_api.connectors.gitlab.adapter import GitLabCursor
from ctower_api.connectors.gitlab.registration import GitLabRuntimeRegistration
from ctower_kernel.catalog.interface import JsonValue
from modules.integrations._legacy_gitlab_shims.values import GitLabSyncBinding

__all__ = ["GitLabRuntimeRevision"]


@dataclass(frozen=True, slots=True)
class GitLabRuntimeRevision:
    """Expose the original revision shape while using the extracted parser."""

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
        runtime = GitLabRuntimeRegistration.from_catalog(
            payload,
            revision_id=revision_id,
            revision_digest=revision_digest,
        )
        registration = runtime.registration
        cursor = GitLabCursor.decode(registration.initial_cursor)
        return cls(
            base_url=runtime.config.base_url,
            token_binding=runtime.token_binding,
            binding=GitLabSyncBinding(
                integration_key=registration.registration_key,
                revision_id=registration.revision_id,
                revision_digest=registration.revision_digest,
                project_id=runtime.config.project_id,
                project_key=registration.project_key,
                initial_custodian_id=registration.initial_custodian_id,
                import_updated_after=cursor.updated_after,
                page_size=registration.page_size,
                poll_interval=registration.poll_interval,
                label_map=tuple(
                    (mapping.source, mapping.target) for mapping in registration.label_map
                ),
            ),
        )
