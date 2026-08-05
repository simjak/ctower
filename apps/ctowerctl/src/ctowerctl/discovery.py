"""Local, env-free discovery of the ctower instance base URL for the public CLI.

`--base-url` remains authoritative when passed explicitly. When it is omitted, the CLI
resolves it from exactly one declared instance in this owner-only catalog file, never from an
environment variable. Zero declared instances and two-or-more declared instances both refuse
by name instead of guessing.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ctowerctl._argument_types import _safe_base_url

__all__ = [
    "CliInstance",
    "CliInstanceCatalog",
    "DiscoveryError",
    "catalog_path",
    "resolve_base_url",
    "write_catalog",
]

_NAME = r"^[a-z][a-z0-9-]{0,63}$"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CliInstance(_StrictModel):
    """One named, discoverable ctower instance."""

    name: str = Field(pattern=_NAME)
    base_url: str

    @field_validator("base_url")
    @classmethod
    def _valid_base_url(cls, value: str) -> str:
        try:
            return _safe_base_url(value)
        except argparse.ArgumentTypeError as error:
            raise ValueError(str(error)) from error


class CliInstanceCatalog(_StrictModel):
    """The complete set of instances this box's CLI can resolve without `--base-url`."""

    schema_id: Literal["ctower.cli-instances/v1"] = Field(alias="schema")
    instances: tuple[CliInstance, ...]


class DiscoveryError(ValueError):
    """One instance-discovery failure with a stable, user-facing reason."""

    def __init__(self, reason: Literal["missing", "ambiguous", "invalid"], message: str) -> None:
        super().__init__(message)
        self.reason = reason


def catalog_path() -> Path:
    return _config_home() / "ctower" / "cli-instances.json"


def resolve_base_url() -> str:
    """Resolve the one configured base URL, or refuse by exact name."""

    path = catalog_path()
    if not path.is_file():
        raise DiscoveryError(
            "missing",
            f"no ctower instance is configured at {path}; "
            "run 'ctower-private-vps expose-cli' or pass --base-url explicitly",
        )
    try:
        catalog = CliInstanceCatalog.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise DiscoveryError(
            "invalid", f"{path} is not a valid instance catalog: {error}"
        ) from error
    if not catalog.instances:
        raise DiscoveryError(
            "missing",
            f"{path} declares no instance; run 'ctower-private-vps expose-cli' "
            "or pass --base-url explicitly",
        )
    if len(catalog.instances) > 1:
        names = ", ".join(instance.name for instance in catalog.instances)
        raise DiscoveryError(
            "ambiguous",
            f"{path} declares {len(catalog.instances)} instances ({names}); "
            "pass --base-url explicitly",
        )
    return catalog.instances[0].base_url


def write_catalog(catalog: CliInstanceCatalog) -> Path:
    """Durably write the owner-only instance catalog and return its path."""

    path = catalog_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(catalog.model_dump_json(by_alias=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)
    return path


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
