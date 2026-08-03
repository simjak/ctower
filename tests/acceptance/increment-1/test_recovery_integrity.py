"""Recovery chain grounding, signature binding, and immutable replay matrix."""

from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from support.acceptance import accept_command
from support.recovery import (
    NOW,
    accepted_roots,
    backup,
    installation,
    inventory,
    inventory_with_sources,
    signature_verification,
)
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.record.postgres_recovery import PostgresRecovery
from ctower_kernel.record.recovery import (
    AcceptedRoot,
    AnchorRecord,
    BackupVerificationReceipt,
    RecoveryPolicy,
    RecoveryReplayConflictError,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

__all__: tuple[str, ...] = ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("digest", "sha256:" + "0" * 64),
        ("signature", "signature-from-another-receipt"),
        ("signing_key_reference", "kms-ref:other/signing"),
        ("signing_key_version", "v2"),
        ("public_key_sha256", "sha256:" + "9" * 64),
        ("signed_at", NOW + timedelta(seconds=2)),
    ],
)
def test_recovery_boundary_rejects_each_mismatched_signature_receipt_field(
    tenant: TenantFixture,
    field: str,
    value: object,
) -> None:
    identity = installation(tenant.tenant_id)
    verification = signature_verification(identity).model_copy(update={field: value})

    with pytest.raises(ValueError, match="not bound"):
        PostgresRecovery(tenant.database.admin_dsn).record_installation(
            identity,
            verification=verification,
        )


@pytest.mark.parametrize(
    "field",
    ["installation_id", "tenant_id", "identity_ref", "issued_at"],
)
def test_installation_signature_rejects_every_semantic_rebind_before_sql_mutation(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
    field: str,
) -> None:
    identity = installation(tenant.tenant_id)
    original_verification = signature_verification(identity)
    values: dict[str, object] = {
        "installation_id": uuid4(),
        "tenant_id": second_tenant.tenant_id,
        "identity_ref": "installation-ref:test/rebound",
        "issued_at": NOW + timedelta(seconds=1),
    }
    rebound = identity.model_copy(update={field: values[field]})

    with pytest.raises(ValueError, match="not bound"):
        PostgresRecovery(tenant.database.admin_dsn).record_installation(
            rebound,
            verification=original_verification,
        )

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        persisted = connection.execute(
            "SELECT count(*) FROM installation_identities WHERE installation_id = %s",
            (rebound.installation_id,),
        ).fetchone()
    assert persisted is not None
    assert persisted[0] == 0


def test_installation_signature_must_be_verified_before_sql_mutation(
    tenant: TenantFixture,
) -> None:
    identity = installation(tenant.tenant_id)

    with pytest.raises(ValueError, match="signature verification failed"):
        PostgresRecovery(tenant.database.admin_dsn).record_installation(
            identity,
            verification=signature_verification(identity, verified=False),
        )

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        persisted = connection.execute(
            "SELECT count(*) FROM installation_identities WHERE installation_id = %s",
            (identity.installation_id,),
        ).fetchone()
    assert persisted is not None
    assert persisted[0] == 0


def test_synthetic_all_true_no_run_input_cannot_reach_backup_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[BackupVerificationReceipt] = []
    monkeypatch.setattr(
        "ctower_kernel.record.postgres_recovery.insert_backup",
        lambda _dsn, receipt: persisted.append(receipt),
    )
    synthetic = cast(
        BackupVerificationReceipt,
        {
            "backup_id": uuid4(),
            "tenant_id": uuid4(),
            "manifest_sha256": "sha256:" + "1" * 64,
            "base_verified": True,
            "wal_verified": True,
            "logical_dump_verified": True,
            "objects_verified": True,
            "key_reference_verified": True,
        },
    )

    with pytest.raises(TypeError, match="run-bound verification receipt"):
        PostgresRecovery("unused").record_backup(synthetic)
    assert persisted == []


def test_every_recovery_receipt_requires_complete_exact_replay(
    tenant: TenantFixture,
) -> None:
    recovery = PostgresRecovery(tenant.database.admin_dsn)
    _assert_backup_replay(recovery, tenant)
    _assert_installation_replay(recovery, tenant)
    _create_accepted_ticket(tenant)
    _assert_inventory_replay(recovery, tenant)
    _assert_anchor_replay(recovery, tenant)


def _assert_backup_replay(
    recovery: PostgresRecovery,
    tenant: TenantFixture,
) -> None:
    receipt = backup(uuid4(), tenant.tenant_id)
    recovery.record_backup(receipt)
    recovery.record_backup(receipt)
    for update in (
        {"repository_ref": "backup-ref:test/changed"},
        {"repository_object_version": "version-2"},
        {"pgbackrest_sha256": "sha256:" + "b" * 64},
        {"completed_at": NOW + timedelta(minutes=2)},
    ):
        changed = receipt.model_copy(
            update={"manifest": receipt.manifest.model_copy(update=update)}
        )
        with pytest.raises(RecoveryReplayConflictError):
            recovery.record_backup(changed)


def _assert_installation_replay(
    recovery: PostgresRecovery,
    tenant: TenantFixture,
) -> None:
    identity = installation(tenant.tenant_id)
    recovery.record_installation(identity, verification=signature_verification(identity))
    recovery.record_installation(identity, verification=signature_verification(identity))
    for update in (
        {"identity_ref": "installation-ref:test/changed"},
        {"signature": "different-installation-signature"},
        {"issued_at": NOW + timedelta(seconds=1)},
    ):
        changed_identity = identity.model_copy(update=update)
        with pytest.raises(RecoveryReplayConflictError):
            recovery.record_installation(
                changed_identity,
                verification=signature_verification(changed_identity),
            )


def _assert_inventory_replay(
    recovery: PostgresRecovery,
    tenant: TenantFixture,
) -> None:
    inventory_record = inventory(tenant.tenant_id)
    recovery.record_inventory(
        inventory_record,
        verification=signature_verification(inventory_record),
    )
    recovery.record_inventory(
        inventory_record,
        verification=signature_verification(inventory_record),
    )
    for update in (
        {"object_version": "version-changed"},
        {"signature": "different-inventory-signature"},
    ):
        changed_inventory = inventory_record.model_copy(update=update)
        with pytest.raises(RecoveryReplayConflictError):
            recovery.record_inventory(
                changed_inventory,
                verification=signature_verification(changed_inventory),
            )
    first_source = inventory_record.sources[0].model_copy(
        update={
            "activation": "active",
            "cursor_declaration": "trusted_cursor",
            "source_count": 1,
            "trust_root_ref": "source-ref:test/root",
            "trusted_cursor": "cursor-1",
            "activation_event_ref": "event-ref:test/activation",
        }
    )
    changed_entries = inventory_with_sources(
        inventory_record,
        (first_source, *inventory_record.sources[1:]),
    )
    with pytest.raises(RecoveryReplayConflictError):
        recovery.record_inventory(
            changed_entries,
            verification=signature_verification(changed_entries),
        )


def _assert_anchor_replay(
    recovery: PostgresRecovery,
    tenant: TenantFixture,
) -> None:
    anchor = _anchor(tenant, previous=None)
    recovery.record_anchor(anchor, verification=signature_verification(anchor))
    recovery.record_anchor(anchor, verification=signature_verification(anchor))
    for update in (
        {"object_version": "version-changed"},
        {"signature": "different-anchor-signature"},
        {"anchored_at": NOW + timedelta(seconds=1)},
    ):
        changed_anchor = anchor.model_copy(update=update)
        with pytest.raises(RecoveryReplayConflictError):
            recovery.record_anchor(
                changed_anchor,
                verification=signature_verification(changed_anchor),
            )


def test_anchor_and_inventory_chains_reject_fabrication_gaps_and_forks(
    tenant: TenantFixture,
) -> None:
    recovery = PostgresRecovery(tenant.database.admin_dsn)
    _create_accepted_ticket(tenant)
    roots = accepted_roots(tenant.database.admin_dsn, tenant.tenant_id)
    fabricated = tuple(
        root.model_copy(update={"command_root": "sha256:" + "f" * 64}) if index == 0 else root
        for index, root in enumerate(roots)
    )
    false_anchor = _anchor(tenant, previous=None, roots=fabricated)
    with pytest.raises(ValueError, match="persisted accepted roots"):
        recovery.record_anchor(
            false_anchor,
            verification=signature_verification(false_anchor),
        )

    first_anchor = _anchor(tenant, previous=None, roots=roots)
    recovery.record_anchor(
        first_anchor,
        verification=signature_verification(first_anchor),
    )
    _create_accepted_ticket(tenant)
    next_roots = tuple(
        root
        for root in accepted_roots(tenant.database.admin_dsn, tenant.tenant_id)
        if root.acceptance_position > first_anchor.source_end_position
    )
    fork = _anchor(tenant, previous="sha256:" + "0" * 64, roots=next_roots)
    with pytest.raises(ValueError, match="continuous"):
        recovery.record_anchor(fork, verification=signature_verification(fork))

    first_inventory = inventory(tenant.tenant_id)
    recovery.record_inventory(
        first_inventory,
        verification=signature_verification(first_inventory),
    )
    gap = inventory(
        tenant.tenant_id,
        revision_number=3,
        previous_revision_sha256=first_inventory.revision_sha256,
    )
    with pytest.raises(ValueError, match="continuous"):
        recovery.record_inventory(gap, verification=signature_verification(gap))
    wrong_predecessor = inventory(
        tenant.tenant_id,
        revision_number=2,
        previous_revision_sha256="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="continuous"):
        recovery.record_inventory(
            wrong_predecessor,
            verification=signature_verification(wrong_predecessor),
        )
    second_inventory = inventory(
        tenant.tenant_id,
        revision_number=2,
        previous_revision_sha256=first_inventory.revision_sha256,
    )
    recovery.record_inventory(
        second_inventory,
        verification=signature_verification(second_inventory),
    )


def _anchor(
    tenant: TenantFixture,
    *,
    previous: str | None,
    roots: tuple[AcceptedRoot, ...] | None = None,
) -> AnchorRecord:
    selected = roots or accepted_roots(tenant.database.admin_dsn, tenant.tenant_id)
    digest = RecoveryPolicy().build_anchor(selected, previous_anchor_sha256=previous)
    return AnchorRecord(
        anchor_id=uuid4(),
        tenant_id=tenant.tenant_id,
        source_start_position=selected[0].acceptance_position,
        source_end_position=selected[-1].acceptance_position,
        previous_anchor_sha256=previous,
        anchor_sha256=digest,
        signature="external-anchor-signature",
        signing_key_reference="kms-ref:anchor/signing",
        signing_key_version="v1",
        public_key_sha256="sha256:" + "c" * 64,
        object_key=f"operations/anchors/{selected[-1].acceptance_position}.json",
        object_version=f"version-{selected[-1].acceptance_position}",
        anchored_at=NOW,
    )


def _create_accepted_ticket(tenant: TenantFixture) -> None:
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            project_key="ctower",
            source=SourceReference("test", f"test:recovery-integrity:{uuid4()}"),
            title="Recovery integrity acceptance",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )
