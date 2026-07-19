"""Canonical generated-client acceptance through a separate API process."""

from __future__ import annotations

import io
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from support.postgres import DatabaseFixture
from support.server import running_api
from support.tenant_fixture import provision_credential

from ctower_client import (
    BootstrapRequest,
    CtowerClient,
    CustodyTransferRequest,
    Priority,
    SourceReference,
    TicketCreateRequest,
)
from ctower_kernel.record.postgres import (
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)

__all__: tuple[str, ...] = ()

TRANSFERRED_VERSION = 2


def test_generated_client_crosses_real_process_for_complete_ticket_slice(
    database: DatabaseFixture,
) -> None:
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn)
    capability = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.migrator_dsn,
        capability_input=io.StringIO(f"{capability}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    with running_api(database.runtime_dsn) as base_url, CtowerClient(base_url) as client:
        receipt = client.bootstrap_first_tenant(
            BootstrapRequest(
                commander_name="Ctower Commander",
                commander_vault_ref="vault-ref:ctower/commander",
                operator_credential_ref="credential-ref:ctower/operator",
                operator_name="First Operator",
                operator_vault_ref="vault-ref:ctower/operator",
                tenant_name="Ctower",
                tenant_slug="ctower",
            ),
            command_id=uuid4(),
            capability=capability,
        )

        credential = secrets.token_urlsafe(32)
        provision_credential(database.admin_dsn, receipt.tenant_id, receipt.operator_id, credential)
        with CtowerClient(base_url, credential=credential) as authorized:
            created = authorized.create_ticket(
                TicketCreateRequest(
                    initial_custodian_id=receipt.commander_id,
                    priority=Priority.P1,
                    source=SourceReference(kind="process", ref="generated-client"),
                    title="Separate-process ticket",
                ),
                command_id=uuid4(),
            )
            shown = authorized.get_ticket(created.ticket.ticket_id)
            timeline = authorized.get_ticket_timeline(created.ticket.ticket_id)
            transferred = authorized.transfer_ticket_custody(
                created.ticket.ticket_id,
                CustodyTransferRequest(
                    expected_version=1,
                    from_custodian_id=receipt.commander_id,
                    protected_transfer=True,
                    reason="Generated-client acceptance",
                    to_custodian_id=receipt.operator_id,
                ),
                command_id=uuid4(),
            )

    assert shown == created.ticket
    assert [event.kind for event in timeline.events] == ["ticket.created"]
    assert transferred.ticket.version == TRANSFERRED_VERSION
    assert transferred.ticket.custodian_id == receipt.operator_id
