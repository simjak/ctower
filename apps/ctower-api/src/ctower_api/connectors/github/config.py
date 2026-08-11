"""Strict, origin-free GitHub App configuration for one selected repository."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["GitHubConnectorConfig"]

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_BINDING_PATTERN = r"^[A-Z][A-Z0-9_]{2,127}$"
_OWNER_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
_REPOSITORY_PATTERN = r"^[A-Za-z0-9._-]{1,100}$"


class GitHubConnectorConfig(BaseModel):
    """Non-secret GitHub App and immutable repository identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    app_client_id: str = Field(min_length=1, max_length=255)
    installation_id: int = Field(ge=1)
    repository_id: int = Field(ge=1)
    repository_owner: str = Field(pattern=_OWNER_PATTERN)
    repository_name: str = Field(pattern=_REPOSITORY_PATTERN)
    private_key_binding: str = Field(pattern=_BINDING_PATTERN)
    private_key_binding_revision: str = Field(pattern=_DIGEST_PATTERN)

    @property
    def repository_full_name(self) -> str:
        return f"{self.repository_owner}/{self.repository_name}"
