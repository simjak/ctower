"""Strict GitLab configuration owned by the GitLab connector."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["GitLabConnectorConfig"]


class GitLabConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    base_url: str = Field(min_length=1, max_length=2048)
    project_id: int = Field(ge=1)

    @model_validator(mode="after")
    def _origin_is_https(self) -> GitLabConnectorConfig:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("GitLab base URL must be an absolute HTTPS origin")
        return self
