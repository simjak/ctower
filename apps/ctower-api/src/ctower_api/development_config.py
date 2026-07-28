"""Strict, secret-reference-only configuration for the E2 shadow runtime."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "DevelopmentBootstrapCheckpoint",
    "DevelopmentConfig",
    "DevelopmentState",
    "bootstrap_checkpoint_path",
    "config_path",
    "delete_bootstrap_checkpoint",
    "load_bootstrap_checkpoint",
    "load_config",
    "load_state",
    "state_path",
    "write_bootstrap_checkpoint",
    "write_config",
    "write_state",
]

_REFERENCE = re.compile(r"^secret-service:ctower-development/[a-z0-9-]{3,64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DevelopmentConfig(_StrictModel):
    """One local-only deployment description containing references, never values."""

    schema_id: Literal["ctower.development-runtime/v1"] = Field(alias="schema")
    label: Literal["SHADOW_ONLY_CP3_D_NOT_PROVEN"]
    api_host: Literal["127.0.0.1"]
    api_port: int = Field(ge=1024, le=65535)
    database_host: Literal["127.0.0.1"]
    database_name: Literal["ctower"]
    primary_port: int = Field(ge=1024, le=65535)
    standby_port: int = Field(ge=1024, le=65535)
    postgres_image: str
    postgres_admin_secret_ref: str
    migrator_secret_ref: str
    runtime_secret_ref: str
    projection_secret_ref: str
    operator_secret_ref: str
    commander_secret_ref: str

    @field_validator(
        "postgres_admin_secret_ref",
        "migrator_secret_ref",
        "runtime_secret_ref",
        "projection_secret_ref",
        "operator_secret_ref",
        "commander_secret_ref",
    )
    @classmethod
    def _secret_reference(cls, value: str) -> str:
        if _REFERENCE.fullmatch(value) is None:
            raise ValueError("development secrets must be Secret Service references")
        return value

    @field_validator("postgres_image")
    @classmethod
    def _pinned_postgres(cls, value: str) -> str:
        if re.fullmatch(r"postgres@sha256:[0-9a-f]{64}", value) is None:
            raise ValueError("development PostgreSQL image must use one immutable digest")
        return value


class DevelopmentState(_StrictModel):
    """Non-secret identities produced by first-tenant bootstrap."""

    schema_id: Literal["ctower.development-state/v1"] = Field(alias="schema")
    tenant_id: UUID
    operator_id: UUID
    commander_id: UUID


class DevelopmentBootstrapCheckpoint(_StrictModel):
    """Non-secret replay identity for a crash-resumable first-tenant bootstrap."""

    schema_id: Literal["ctower.development-bootstrap-checkpoint/v1"] = Field(alias="schema")
    command_id: UUID
    capability_ref: Literal["secret-service:ctower-development/bootstrap-capability"]
    tenant_name: str = Field(min_length=1, max_length=120)
    tenant_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def _expiry_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bootstrap checkpoint expiry must be timezone-aware")
        return value


def config_path() -> Path:
    return _config_home() / "ctower" / "development-runtime.json"


def bootstrap_checkpoint_path() -> Path:
    return _state_home() / "ctower" / "development-bootstrap-checkpoint.json"


def state_path() -> Path:
    return _state_home() / "ctower" / "development-runtime-state.json"


def load_config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate_json(config_path().read_text(encoding="utf-8"))


def write_config(config: DevelopmentConfig) -> None:
    _write_owner_only(
        config_path(),
        config.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def load_bootstrap_checkpoint() -> DevelopmentBootstrapCheckpoint:
    return DevelopmentBootstrapCheckpoint.model_validate_json(
        bootstrap_checkpoint_path().read_text(encoding="utf-8")
    )


def write_bootstrap_checkpoint(checkpoint: DevelopmentBootstrapCheckpoint) -> None:
    _write_owner_only(
        bootstrap_checkpoint_path(),
        checkpoint.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def delete_bootstrap_checkpoint() -> None:
    bootstrap_checkpoint_path().unlink(missing_ok=True)


def load_state() -> DevelopmentState:
    return DevelopmentState.model_validate_json(state_path().read_text(encoding="utf-8"))


def write_state(state: DevelopmentState) -> None:
    _write_owner_only(
        state_path(),
        state.model_dump_json(by_alias=True, indent=2) + "\n",
    )


def _write_owner_only(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
