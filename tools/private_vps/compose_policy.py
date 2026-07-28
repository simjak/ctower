"""Exact normalized authority for the private-VPS development composition."""

from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.tokens import (
    AliasToken,
    AnchorToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
)

from tools.private_vps.manifest import (
    MAX_STRUCTURE_DEPTH,
    MAX_STRUCTURE_TOKENS,
    FileSnapshot,
    PacketError,
)
from tools.private_vps.models import DeploymentBindings, WorkloadIdentity

__all__ = ["verify_compose"]

_TMPFS = "/" + "tmp:rw,noexec,nosuid,nodev,mode=0700"
_RUN_TMPFS = "/run/ctower:rw,noexec,nosuid,nodev,mode=0700"


def verify_compose(snapshot: FileSnapshot, bindings: DeploymentBindings) -> None:
    """Require exactly one bounded YAML document equal to the approved topology."""
    try:
        text = snapshot.data.decode("utf-8")
        yaml = YAML(typ="safe", pure=True)
    except UnicodeError as error:
        raise PacketError("invalid_compose", "configuration.compose") from error
    _verify_yaml_tokens(yaml, text)
    try:
        documents = list(yaml.load_all(text))
    except (MemoryError, RecursionError, YAMLError) as error:
        raise PacketError("invalid_compose", "configuration.compose") from error
    if len(documents) != 1:
        raise PacketError("compose_document_count", "configuration.compose")
    if documents[0] != _expected(bindings):
        raise PacketError("compose_authority_changed", "configuration.compose")


def _verify_yaml_tokens(yaml: YAML, text: str) -> None:
    depth = 0
    count = 0
    starts = (
        BlockMappingStartToken,
        BlockSequenceStartToken,
        FlowMappingStartToken,
        FlowSequenceStartToken,
    )
    ends = (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken)
    try:
        for token in yaml.scan(text):
            count += 1
            _reject_yaml_alias(token)
            depth = _yaml_depth(token, depth, starts=starts, ends=ends)
            _verify_yaml_budget(depth, count)
    except PacketError:
        raise
    except (MemoryError, RecursionError, YAMLError) as error:
        raise PacketError("invalid_compose", "configuration.compose") from error


def _reject_yaml_alias(token: object) -> None:
    if isinstance(token, (AliasToken, AnchorToken)):
        raise PacketError("compose_alias_forbidden", "configuration.compose")


def _yaml_depth(
    token: object,
    depth: int,
    *,
    starts: tuple[type[object], ...],
    ends: tuple[type[object], ...],
) -> int:
    if isinstance(token, starts):
        return depth + 1
    if isinstance(token, ends):
        return depth - 1
    return depth


def _verify_yaml_budget(depth: int, count: int) -> None:
    if depth > MAX_STRUCTURE_DEPTH or count > MAX_STRUCTURE_TOKENS:
        raise PacketError("structure_limit_exceeded", "configuration.compose")


def _expected(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        "name": "ctower-private-vps-development",
        "services": {
            "postgres": _postgres(bindings),
            "role-admin": _role_admin(bindings),
            "migrator": _migrator(bindings),
            "api": _api(bindings),
            "worker": _worker(bindings),
            "collector": _collector(bindings),
            "edge": _edge(bindings),
        },
        "networks": {
            "control": {"internal": True},
            "record": {"internal": True},
        },
        "volumes": {
            "object-data": {},
            "postgres-data": {},
        },
    }


def _postgres(bindings: DeploymentBindings) -> dict[str, Any]:
    identity = bindings.workload_identities.postgres
    password = bindings.database.postgres_admin_password.path
    return {
        **_base(bindings.images.postgres, identity, restart="unless-stopped"),
        "environment": {
            "POSTGRES_DB": "ctower",
            "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256 --auth-local=peer",
            "POSTGRES_PASSWORD_FILE": password,
            "POSTGRES_USER": "ctower_role_admin",
        },
        "healthcheck": {
            "test": ["CMD", "pg_isready", "-U", "ctower_role_admin", "-d", "ctower"],
            "interval": "5s",
            "timeout": "3s",
            "retries": 30,
        },
        "tmpfs": [
            "/run/postgresql:rw,noexec,nosuid,nodev,mode=0750",
            _TMPFS,
        ],
        "volumes": [
            {
                "type": "volume",
                "source": "postgres-data",
                "target": "/var/lib/postgresql/data",
            },
            _bind(password, "/run/ctower/refs/postgres-admin-password"),
        ],
        "networks": ["record"],
    }


def _role_admin(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        **_control_base(
            bindings,
            bindings.workload_identities.role_admin,
            restart="no",
        ),
        "profiles": ["admin"],
        "command": ["python", "-m", "ctower_api._deployment_admin", "provision-roles"],
        "environment": {
            "CTOWER_BOOTSTRAP_OUTPUT": bindings.bootstrap.output.path,
            "CTOWER_ROLE_ADMIN_DSN_FILE": bindings.database.role_admin_dsn.path,
        },
        "depends_on": {"postgres": {"condition": "service_healthy"}},
        "volumes": [
            _bind(
                bindings.database.role_admin_dsn.path,
                "/run/ctower/refs/role-admin-dsn",
            ),
            _bind(bindings.bootstrap.parent.path, "/run/ctower/bootstrap", read_only=False),
        ],
        "networks": ["record"],
    }


def _migrator(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        **_control_base(
            bindings,
            bindings.workload_identities.migrator,
            restart="no",
        ),
        "profiles": ["admin"],
        "command": ["python", "-m", "ctower_api._deployment_admin", "migrate"],
        "environment": {
            "CTOWER_MIGRATION_DSN_FILE": bindings.database.migration_dsn.path,
        },
        "depends_on": {"postgres": {"condition": "service_healthy"}},
        "volumes": [
            _bind(
                bindings.database.migration_dsn.path,
                "/run/ctower/refs/migration-dsn",
            ),
        ],
        "networks": ["record"],
    }


def _api(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        **_control_base(
            bindings,
            bindings.workload_identities.api,
            restart="unless-stopped",
        ),
        "command": ["python", "-m", "ctower_api._deployment_server"],
        "environment": {
            "CTOWER_API_DSN_FILE": bindings.database.api_dsn.path,
            "CTOWER_OBJECT_KEY_FILE": bindings.objects.api_key.path,
            "CTOWER_OBJECT_ROOT": bindings.objects.root.path,
        },
        "depends_on": {"postgres": {"condition": "service_healthy"}},
        "volumes": [
            _bind(bindings.database.api_dsn.path, "/run/ctower/refs/api-dsn"),
            _bind(bindings.objects.api_key.path, "/run/ctower/refs/api-object-key"),
            _volume("object-data", bindings.objects.root.path),
        ],
        "networks": ["control", "record"],
    }


def _worker(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        **_control_base(
            bindings,
            bindings.workload_identities.worker,
            restart="unless-stopped",
        ),
        "command": ["ctower-control-worker"],
        "environment": {
            "CTOWER_OBJECT_KEY_FILE": bindings.objects.worker_key.path,
            "CTOWER_OBJECT_ROOT": bindings.objects.root.path,
            "CTOWER_PROJECTION_DSN_FILE": bindings.database.projection_dsn.path,
            "CTOWER_WORKER_DSN_FILE": bindings.database.worker_dsn.path,
        },
        "depends_on": {"postgres": {"condition": "service_healthy"}},
        "volumes": [
            _bind(bindings.database.worker_dsn.path, "/run/ctower/refs/worker-dsn"),
            _bind(
                bindings.database.projection_dsn.path,
                "/run/ctower/refs/projection-dsn",
            ),
            _bind(
                bindings.objects.worker_key.path,
                "/run/ctower/refs/worker-object-key",
            ),
            _volume("object-data", bindings.objects.root.path),
        ],
        "networks": ["control", "record"],
    }


def _collector(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        **_base(
            bindings.images.collector,
            bindings.workload_identities.collector,
            restart="unless-stopped",
        ),
        "command": ["--config=/etc/otelcol-contrib/config.yaml"],
        "environment": {
            "CTOWER_TELEMETRY_EXPORTER_FILE": bindings.telemetry.exporter.path,
        },
        "tmpfs": [_TMPFS],
        "volumes": [
            _bind("./otel-collector.yaml", "/etc/otelcol-contrib/config.yaml"),
            _bind(
                bindings.telemetry.exporter.path,
                "/run/ctower/refs/telemetry-exporter",
            ),
        ],
        "networks": ["control"],
    }


def _edge(bindings: DeploymentBindings) -> dict[str, Any]:
    return {
        **_base(
            bindings.images.edge,
            bindings.workload_identities.edge,
            restart="unless-stopped",
        ),
        "cap_add": ["NET_BIND_SERVICE"],
        "command": [
            "caddy",
            "run",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        ],
        "depends_on": {"api": {"condition": "service_started"}},
        "ports": [f"{bindings.bind_address}:443:443"],
        "tmpfs": [
            "/config:rw,noexec,nosuid,nodev,mode=0700",
            "/data:rw,noexec,nosuid,nodev,mode=0700",
            _TMPFS,
        ],
        "volumes": [
            _bind("./Caddyfile", "/etc/caddy/Caddyfile"),
            _bind(
                bindings.tls.certificate.path,
                "/run/ctower/refs/tls-certificate",
            ),
            _bind(
                bindings.tls.private_key.path,
                "/run/ctower/refs/tls-private-key",
            ),
        ],
        "networks": ["control"],
    }


def _control_base(
    bindings: DeploymentBindings,
    identity: WorkloadIdentity,
    *,
    restart: str,
) -> dict[str, Any]:
    return {
        **_base(bindings.images.control, identity, restart=restart),
        "tmpfs": [_TMPFS, _RUN_TMPFS],
    }


def _base(
    image: str,
    identity: WorkloadIdentity,
    *,
    restart: str,
) -> dict[str, Any]:
    return {
        "image": image,
        "user": f"{identity.uid}:{identity.gid}",
        "read_only": True,
        "init": True,
        "privileged": False,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "restart": restart,
    }


def _bind(source: str, target: str, *, read_only: bool = True) -> dict[str, Any]:
    return {
        "type": "bind",
        "source": source,
        "target": target,
        "read_only": read_only,
        "bind": {"create_host_path": False},
    }


def _volume(source: str, target: str) -> dict[str, str]:
    return {
        "type": "volume",
        "source": source,
        "target": target,
    }
