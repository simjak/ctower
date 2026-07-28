"""Crash-resumable first-tenant bootstrap lifecycle."""

from __future__ import annotations

import io
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from ctower_api.development_config import (
    DevelopmentBootstrapCheckpoint,
    DevelopmentConfig,
    DevelopmentState,
    bootstrap_checkpoint_path,
    delete_bootstrap_checkpoint,
    delete_secret,
    development_dsn,
    load_bootstrap_checkpoint,
    load_config,
    load_secret,
    load_state,
    put_secret,
    state_path,
    write_bootstrap_checkpoint,
    write_state,
)
from ctower_client import BootstrapRequest, CtowerClient
from ctower_kernel.record.postgres import (
    provision_bootstrap,
    provision_principal_credential,
)

__all__ = ["bootstrap_instance"]

_CAPABILITY_REF: Literal["secret-service:ctower-development/bootstrap-capability"] = (
    "secret-service:ctower-development/bootstrap-capability"
)


def bootstrap_instance(tenant_name: str, tenant_slug: str) -> None:
    """Create or resume the first tenant and activate the complete shadow target."""

    if state_path().exists():
        load_state()
        _activate_full_target()
        _clear_checkpoint()
        return
    config = load_config()
    checkpoint = _checkpoint(tenant_name, tenant_slug)
    capability = load_secret(checkpoint.capability_ref)
    provision_bootstrap(
        development_dsn(config, "ctower_migrator"),
        capability_input=io.StringIO(capability + "\n"),
        allowed_origin=config.api_host,
        expires_at=checkpoint.expires_at,
    )
    with CtowerClient(f"http://{config.api_host}:{config.api_port}") as client:
        receipt = client.bootstrap_first_tenant(
            BootstrapRequest(
                commander_name="Development Commander",
                commander_vault_ref="vault-ref:ctower/development/commander",
                operator_credential_ref="credential-ref:ctower/development/operator",
                operator_name="Development Operator",
                operator_vault_ref="vault-ref:ctower/development/operator",
                tenant_name=tenant_name,
                tenant_slug=tenant_slug,
            ),
            command_id=checkpoint.command_id,
            capability=capability,
        )
    _bind_credentials(config, receipt.tenant_id, receipt.operator_id, receipt.commander_id)
    write_state(
        DevelopmentState(
            schema="ctower.development-state/v1",
            tenant_id=receipt.tenant_id,
            operator_id=receipt.operator_id,
            commander_id=receipt.commander_id,
        )
    )
    _activate_full_target()
    _clear_checkpoint()


def _checkpoint(tenant_name: str, tenant_slug: str) -> DevelopmentBootstrapCheckpoint:
    if bootstrap_checkpoint_path().exists():
        checkpoint = load_bootstrap_checkpoint()
        if (checkpoint.tenant_name, checkpoint.tenant_slug) != (tenant_name, tenant_slug):
            raise RuntimeError("bootstrap retry differs from the persisted tenant identity")
        if checkpoint.expires_at <= datetime.now(UTC):
            checkpoint = checkpoint.model_copy(
                update={"expires_at": datetime.now(UTC) + timedelta(minutes=5)}
            )
            write_bootstrap_checkpoint(checkpoint)
        return checkpoint
    checkpoint = DevelopmentBootstrapCheckpoint(
        schema="ctower.development-bootstrap-checkpoint/v1",
        command_id=uuid4(),
        capability_ref=_CAPABILITY_REF,
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    put_secret(checkpoint.capability_ref, secrets.token_urlsafe(48))
    write_bootstrap_checkpoint(checkpoint)
    return checkpoint


def _bind_credentials(
    config: DevelopmentConfig,
    tenant_id: UUID,
    operator_id: UUID,
    commander_id: UUID,
) -> None:
    provision_principal_credential(
        development_dsn(config, "ctower_migrator"),
        tenant_id,
        operator_id,
        credential_input=io.StringIO(load_secret(config.operator_secret_ref) + "\n"),
    )
    provision_principal_credential(
        development_dsn(config, "ctower_migrator"),
        tenant_id,
        commander_id,
        credential_input=io.StringIO(load_secret(config.commander_secret_ref) + "\n"),
    )


def _activate_full_target() -> None:
    _systemctl(
        "enable",
        "ctower-development-worker.service",
        "ctower-development.target",
    )
    _systemctl("restart", "ctower-development-worker.service")
    _systemctl("start", "ctower-development.target")


def _clear_checkpoint() -> None:
    if not bootstrap_checkpoint_path().exists():
        return
    checkpoint = load_bootstrap_checkpoint()
    delete_secret(checkpoint.capability_ref)
    delete_bootstrap_checkpoint()


def _systemctl(*arguments: str) -> None:
    subprocess.run(  # noqa: S603 - fixed systemctl path and bounded owned unit arguments
        ["/usr/bin/systemctl", "--user", *arguments],
        check=True,
    )
