"""Daemonless Docker Compose rendering for the two CP3-D host projects."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

from tools.cp3d_packet.models import HostBinding, PacketBindings, RootOwnedFile

__all__ = ["ComposeRenderError", "render_compose_config"]

Role = Literal["primary", "standby"]
JsonObject = dict[str, Any]


class ComposeRenderError(RuntimeError):
    """Docker Compose could not produce a safe local configuration."""


def render_compose_config(
    compose_path: Path,
    role: Role,
    bindings: PacketBindings,
) -> JsonObject:
    """Run only `docker compose config` and parse its deterministic JSON."""
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(compose_path.parent),
        "-f",
        str(compose_path),
        "--profile",
        "operator-start-only",
        "config",
        "--format",
        "json",
    ]
    environment = {"PATH": os.environ.get("PATH", "")}
    environment.update(_compose_environment(role, bindings))
    try:
        result = subprocess.run(  # noqa: S603 - fixed Docker CLI, never a shell command
            command,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ComposeRenderError("docker compose config was unavailable") from error
    if result.returncode != 0:
        raise ComposeRenderError(
            f"docker compose config rejected the {role} project (exit {result.returncode})"
        )
    try:
        value = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ComposeRenderError("docker compose config returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ComposeRenderError("docker compose config did not return an object")
    return cast("JsonObject", value)


def _compose_environment(role: Role, bindings: PacketBindings) -> dict[str, str]:
    host = bindings.primary if role == "primary" else bindings.standby
    values = {
        "CTOWER_COMPOSE_PROJECT": f"ctower-cp3d-{role}",
        "CTOWER_POSTGRES_IMAGE": bindings.postgres.image,
        "CTOWER_POSTGRES_UID": str(bindings.postgres.uid),
        "CTOWER_POSTGRES_GID": str(bindings.postgres.gid),
        "CTOWER_POSTGRES_PORT": str(bindings.postgres.port),
        "CTOWER_HOST_PRIVATE_IP": host.private_ip,
        "CTOWER_PRIMARY_PRIVATE_IP": bindings.primary.private_ip,
        "CTOWER_DATA_DIRECTORY": host.data_directory,
        "CTOWER_POSTGRES_CONFIG": host.postgres_config.path,
        "CTOWER_HBA_CONFIG": host.hba_config.path,
        "CTOWER_TLS_CA": host.tls_ca.path,
        "CTOWER_TLS_CERTIFICATE": host.tls_certificate.path,
        "CTOWER_TLS_KEY": host.tls_key.path,
        "CTOWER_PROVIDER": host.provider,
        "CTOWER_REGION": host.region,
        "CTOWER_ZONE": host.zone,
        "CTOWER_HOST_ID": host.host_id,
        "CTOWER_FAILURE_DOMAIN": host.failure_domain,
        "CTOWER_OPERATOR_DOMAIN": host.operator_domain,
        "CTOWER_WORKLOAD_IDENTITY": _workload_identity(role, bindings),
    }
    if role == "standby":
        passfile = _standby_passfile(host)
        values["CTOWER_REPLICATION_PASSFILE"] = passfile.path
    return values


def _workload_identity(role: Role, bindings: PacketBindings) -> str:
    if role == "primary":
        return bindings.workload_identities.primary
    return bindings.workload_identities.standby


def _standby_passfile(host: HostBinding) -> RootOwnedFile:
    passfile = host.replication_passfile
    if passfile is None:
        raise ComposeRenderError("standby replication passfile reference is missing")
    return passfile
