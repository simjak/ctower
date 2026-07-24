"""One intentionally non-spooled bootstrap command."""

from __future__ import annotations

import argparse
from typing import TextIO, cast
from uuid import UUID

from ctower_client import CtowerClient
from ctower_client.models import BootstrapReceipt, BootstrapRequest
from ctowerctl._auth import read_authority

__all__: tuple[str, ...] = ()


def execute(
    base_url: str,
    arguments: argparse.Namespace,
    authority_stream: TextIO,
) -> BootstrapReceipt:
    """Invoke the one-shot bootstrap capability without ever spooling it."""

    request = BootstrapRequest(
        commander_name=cast(str, arguments.commander_name),
        commander_vault_ref=cast(str, arguments.commander_vault_ref),
        operator_credential_ref=cast(str, arguments.operator_credential_ref),
        operator_name=cast(str, arguments.operator_name),
        operator_vault_ref=cast(str, arguments.operator_vault_ref),
        tenant_name=cast(str, arguments.tenant_name),
        tenant_slug=cast(str, arguments.tenant_slug),
    )
    with CtowerClient(base_url) as client:
        return client.bootstrap_first_tenant(
            request,
            command_id=cast(UUID, arguments.command_id),
            capability=read_authority(authority_stream),
        )
