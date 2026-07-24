"""Real-Postgres CP3-C object, backup, inventory, and restore faults."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from support.acceptance import accept_command
from support.recovery import (
    accepted_roots,
    backup,
    installation,
    inventory,
    signature_verification,
)
from support.tenant_fixture import TenantFixture

from ctower_api.restore import CheckEvidence, RestoreEvidence, RestoreGate, RestoreVerifier
from ctower_kernel.proof import (
    Criterion,
    FreezeCriteria,
    Proof,
    ProofActor,
    ProofMutation,
    RecordEvidence,
)
from ctower_kernel.proof.objects import (
    ObjectIntegrityError,
    StoredObject,
    digest_bytes,
    verify_digest,
)
from ctower_kernel.proof.postgres import PostgresProof
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
    AnchorRecord,
    BackupVerificationReceipt,
    InstallationIdentity,
    InventoryRevision,
    RecoveryPolicy,
    RecoveryReplayConflictError,
    RestoreReport,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
_RECOVERY_ROLE_COUNT = 4
__all__: tuple[str, ...] = ()


class DeterministicEncryptedStore:
    """Test implementation behind the real Proof object capability."""

    def __init__(self) -> None:
        self.objects: dict[tuple[UUID, str, str], bytes] = {}
        self.key_available = True
        self.wrong_key = False
        self.last_receipt: StoredObject | None = None

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        verify_digest(content, artifact_digest)
        ciphertext = b"ciphertext:" + content[::-1]
        version = f"version-{artifact_digest[-12:]}"
        receipt = StoredObject(
            artifact_digest=artifact_digest,
            object_key=f"tenants/{tenant_id}/objects/{artifact_digest}",
            object_version=version,
            ciphertext_sha256=digest_bytes(ciphertext),
            key_reference=key_reference,
            key_version="v1",
            wrapped_key_sha256="sha256:" + "f" * 64,
            uploaded_at=NOW,
            verified_at=NOW,
        )
        self.objects[(tenant_id, receipt.object_key, version)] = ciphertext
        self.last_receipt = receipt
        return receipt

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        if not self.key_available:
            raise ObjectIntegrityError("key reference unavailable")
        if self.wrong_key:
            raise ObjectIntegrityError("wrong key reference")
        ciphertext = self.objects.get((tenant_id, receipt.object_key, receipt.object_version))
        if ciphertext is None:
            raise ObjectIntegrityError("object version missing")
        if digest_bytes(ciphertext) != receipt.ciphertext_sha256:
            raise ObjectIntegrityError("ciphertext corrupt")
        content = ciphertext.removeprefix(b"ciphertext:")[::-1]
        verify_digest(content, receipt.artifact_digest)
        return content

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        self.objects.pop((tenant_id, receipt.object_key, receipt.object_version), None)


def test_cp3c_migrations_are_additive_and_roles_are_least_privilege(
    tenant: TenantFixture,
) -> None:
    expected_tables = {
        "backup_manifests",
        "backup_verification_receipts",
        "expected_source_inventory_entries",
        "expected_source_inventory_revisions",
        "installation_identities",
        "object_backfill_receipts",
        "object_erasure_intents",
        "object_erasure_tombstones",
        "object_upload_receipts",
        "record_anchor_receipts",
        "restore_enablement_receipts",
        "restore_findings",
        "restore_runs",
        "restore_steps",
    }
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        }
        roles = connection.execute(
            """
            SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                rolinherit, rolreplication, rolbypassrls
            FROM pg_roles WHERE rolname IN (
                'ctower_object', 'ctower_backup', 'ctower_anchor', 'ctower_restore'
            ) ORDER BY rolname
            """
        ).fetchall()
        privileges = connection.execute(
            """
            SELECT
                has_table_privilege('ctower_svc', 'restore_runs', 'INSERT'),
                has_table_privilege('ctower_projection', 'restore_runs', 'INSERT'),
                has_table_privilege('ctower_backup', 'backup_manifests', 'INSERT'),
                has_table_privilege('ctower_backup', 'backup_manifests', 'UPDATE'),
                pg_has_role('ctower_runtime', 'ctower_restore', 'MEMBER'),
                has_schema_privilege('ctower_backup', 'public', 'USAGE')
            """
        ).fetchone()

    assert expected_tables <= tables
    assert len(roles) == _RECOVERY_ROLE_COUNT
    assert all(not any(bool(value) for value in row[1:]) for row in roles)
    assert privileges == (False, False, True, False, False, True)


def test_external_object_backfill_restore_and_erasure_fail_closed(
    tenant: TenantFixture,
) -> None:
    content, artifact_digest = _record_inline_object(tenant)
    external = DeterministicEncryptedStore()
    object_store = PostgresProof(
        tenant.database.runtime_dsn,
        object_store=external,
        object_key_reference="kms-ref:objects/tenant",
        clock=lambda: NOW,
    )
    assert object_store.backfill_objects(tenant.tenant_id) == 1
    assert object_store.backfill_objects(tenant.tenant_id) == 0
    assert object_store.read_object(tenant.tenant_id, artifact_digest) == content

    receipt = external.last_receipt
    assert receipt is not None
    locator = (tenant.tenant_id, receipt.object_key, receipt.object_version)
    _assert_external_object_faults(
        object_store,
        external,
        tenant.tenant_id,
        artifact_digest,
        content,
        locator,
    )


def _record_inline_object(tenant: TenantFixture) -> tuple[bytes, str]:
    ticket_id = _ticket(tenant)
    proof = Proof(
        writer=PostgresProof(tenant.database.runtime_dsn),
        clock=lambda: NOW,
    )
    actor = ProofActor(tenant.commander_id, tenant.tenant_id, "commander")
    candidate = "sha256:" + "a" * 64
    frozen = proof.execute(
        actor,
        ProofMutation(
            client_command_id=uuid4(),
            ticket_id=ticket_id,
            expected_version=0,
            command=FreezeCriteria(
                candidate_digest=candidate,
                candidate_author_id=tenant.commander_id,
                criteria=(
                    Criterion(
                        key="current",
                        description="Object bytes are current.",
                        candidate_dependent=True,
                        requires_verdict=False,
                    ),
                ),
            ),
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(frozen, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        frozen.command_id,
    )
    content = b"encrypted restore evidence"
    artifact_digest = digest_bytes(content)
    recorded = proof.execute(
        actor,
        ProofMutation(
            client_command_id=uuid4(),
            ticket_id=ticket_id,
            expected_version=1,
            command=RecordEvidence(
                evidence_id=uuid4(),
                criterion_key="current",
                candidate_digest=candidate,
                artifact_digest=artifact_digest,
                content=content,
            ),
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(recorded, RecordProblem)
    return content, artifact_digest


def _assert_external_object_faults(
    object_store: PostgresProof,
    external: DeterministicEncryptedStore,
    tenant_id: UUID,
    artifact_digest: str,
    content: bytes,
    locator: tuple[UUID, str, str],
) -> None:
    saved_ciphertext = external.objects.pop(locator)
    with pytest.raises(ObjectIntegrityError, match="missing"):
        object_store.read_object(tenant_id, artifact_digest)
    external.objects[locator] = saved_ciphertext
    external.objects[locator] = b"corrupt"
    with pytest.raises(ObjectIntegrityError, match="corrupt"):
        object_store.read_object(tenant_id, artifact_digest)
    external.objects[locator] = b"ciphertext:" + content[::-1]
    external.key_available = False
    with pytest.raises(ObjectIntegrityError, match="unavailable"):
        object_store.read_object(tenant_id, artifact_digest)
    external.key_available = True
    external.wrong_key = True
    with pytest.raises(ObjectIntegrityError, match="wrong key"):
        object_store.read_object(tenant_id, artifact_digest)
    external.wrong_key = False


def test_restore_quarantine_requires_exact_enablement_receipt(
    tenant: TenantFixture,
) -> None:
    recovery = PostgresRecovery(tenant.database.admin_dsn)
    backup, installation, inventory, accepted_position = _record_restore_prerequisites(
        recovery,
        tenant,
    )
    restore_run_id = uuid4()
    report, report_sha256 = _verify_restore(
        RestoreVerifier(recovery),
        tenant.tenant_id,
        installation,
        backup,
        inventory,
        restore_run_id,
        accepted_position,
    )
    replayed_report, replayed_digest = _verify_restore(
        RestoreVerifier(recovery),
        tenant.tenant_id,
        installation,
        backup,
        inventory,
        restore_run_id,
        accepted_position,
    )
    assert report.enablement_eligible is True
    assert replayed_report == report
    assert replayed_digest == report_sha256
    changed_steps = (
        report.steps[0].model_copy(update={"detail": "changed replay detail"}),
        *report.steps[1:],
    )
    with pytest.raises(RecoveryReplayConflictError, match="completed report"):
        recovery.complete_restore(report.model_copy(update={"steps": changed_steps}))
    with pytest.raises(RecoveryReplayConflictError, match="restore run"):
        recovery.begin_restore(
            restore_run_id=restore_run_id,
            tenant_id=tenant.tenant_id,
            installation_id=installation.installation_id,
            backup_id=backup.manifest.backup_id,
            inventory_revision_id=inventory.inventory_revision_id,
            accepted_source_position=accepted_position,
            restored_acceptance_position=accepted_position,
            artifact_rpo_seconds=61,
            started_at=NOW,
        )
    _assert_enablement_gate(
        tenant,
        installation,
        report,
        report_sha256,
    )


def _record_restore_prerequisites(
    recovery: PostgresRecovery,
    tenant: TenantFixture,
) -> tuple[BackupVerificationReceipt, InstallationIdentity, InventoryRevision, int]:
    _ticket(tenant)
    tenant_id = tenant.tenant_id
    backup_record = backup(uuid4(), tenant_id)
    recovery.record_backup(backup_record)
    installation_record = installation(tenant_id)
    recovery.record_installation(
        installation_record,
        verification=signature_verification(installation_record),
    )
    inventory_record = inventory(tenant_id)
    with pytest.raises(ValueError, match="signature"):
        recovery.record_inventory(
            inventory_record,
            verification=signature_verification(inventory_record, verified=False),
        )
    recovery.record_inventory(
        inventory_record,
        verification=signature_verification(inventory_record),
    )
    roots = accepted_roots(tenant.database.admin_dsn, tenant_id)
    anchor_digest = RecoveryPolicy().build_anchor(
        roots,
        previous_anchor_sha256=None,
    )
    anchor = AnchorRecord(
        anchor_id=uuid4(),
        tenant_id=tenant_id,
        source_start_position=roots[0].acceptance_position,
        source_end_position=roots[-1].acceptance_position,
        previous_anchor_sha256=None,
        anchor_sha256=anchor_digest,
        signature="external-anchor-signature",
        signing_key_reference="kms-ref:anchor/signing",
        signing_key_version="v1",
        public_key_sha256="sha256:" + "c" * 64,
        object_key=f"operations/anchors/{roots[-1].acceptance_position}.json",
        object_version=f"version-{roots[-1].acceptance_position}",
        anchored_at=NOW,
    )
    with pytest.raises(ValueError, match="signature"):
        recovery.record_anchor(
            anchor,
            verification=signature_verification(anchor, verified=False),
        )
    recovery.record_anchor(anchor, verification=signature_verification(anchor))
    recovery.record_anchor(anchor, verification=signature_verification(anchor))
    return (
        backup_record,
        installation_record,
        inventory_record,
        roots[-1].acceptance_position,
    )


def _assert_enablement_gate(
    tenant: TenantFixture,
    installation: InstallationIdentity,
    report: RestoreReport,
    report_sha256: str,
) -> None:
    restarted = PostgresRecovery(tenant.database.admin_dsn)
    gate = RestoreGate(
        restarted,
        tenant_id=tenant.tenant_id,
        installation_id=installation.installation_id,
        report_sha256=report_sha256,
    )
    with pytest.raises(PermissionError, match="quarantine"):
        gate.require_ordinary_reads()
    with pytest.raises(ValueError, match="denied"):
        restarted.enable(
            enablement_id=uuid4(),
            restore_run_id=report.restore_run_id,
            tenant_id=tenant.tenant_id,
            installation_id=installation.installation_id,
            report_sha256="sha256:" + "9" * 64,
            authority_ref="restore-authority:test/operator",
            enabled_at=NOW + timedelta(minutes=4),
        )

    enablement_id = uuid4()
    enabled_at = NOW + timedelta(minutes=4)
    restarted.enable(
        enablement_id=enablement_id,
        restore_run_id=report.restore_run_id,
        tenant_id=tenant.tenant_id,
        installation_id=installation.installation_id,
        report_sha256=report_sha256,
        authority_ref="restore-authority:test/operator",
        enabled_at=enabled_at,
    )
    restarted.enable(
        enablement_id=enablement_id,
        restore_run_id=report.restore_run_id,
        tenant_id=tenant.tenant_id,
        installation_id=installation.installation_id,
        report_sha256=report_sha256,
        authority_ref="restore-authority:test/operator",
        enabled_at=enabled_at,
    )
    with pytest.raises(RecoveryReplayConflictError, match="enablement"):
        restarted.enable(
            enablement_id=uuid4(),
            restore_run_id=report.restore_run_id,
            tenant_id=tenant.tenant_id,
            installation_id=installation.installation_id,
            report_sha256=report_sha256,
            authority_ref="restore-authority:test/operator",
            enabled_at=enabled_at,
        )
    RestoreGate(
        PostgresRecovery(tenant.database.admin_dsn),
        tenant_id=tenant.tenant_id,
        installation_id=installation.installation_id,
        report_sha256=report_sha256,
    ).require_ordinary_reads()
    assert gate.effects_enabled() is False


def _ticket(tenant: TenantFixture) -> UUID:
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            source=SourceReference("test", f"test:cp3c:{uuid4()}"),
            title="CP3-C encrypted object",
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
    return outcome.ticket.ticket_id


def _verify_restore(
    verifier: RestoreVerifier,
    tenant_id: UUID,
    installation: InstallationIdentity,
    backup: BackupVerificationReceipt,
    inventory: InventoryRevision,
    restore_run_id: UUID,
    accepted_position: int,
) -> tuple[RestoreReport, str]:
    return verifier.verify(
        restore_run_id=restore_run_id,
        tenant_id=tenant_id,
        installation_id=installation.installation_id,
        backup_id=backup.manifest.backup_id,
        inventory=inventory,
        inventory_verification=signature_verification(inventory),
        reconciled_source_keys=frozenset(),
        accepted_source_position=accepted_position,
        restored_acceptance_position=accepted_position,
        artifact_rpo_seconds=60,
        started_at=NOW,
        completed_at=NOW + timedelta(minutes=3),
        evidence=_restore_evidence(),
    )


def _restore_evidence() -> RestoreEvidence:
    values = {
        field: CheckEvidence(
            outcome="pass",
            evidence_sha256="sha256:" + f"{index:x}" * 64,
            detail=f"{field} passed",
        )
        for index, field in enumerate(RestoreEvidence.model_fields, 1)
    }
    return RestoreEvidence.model_validate(values)


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
