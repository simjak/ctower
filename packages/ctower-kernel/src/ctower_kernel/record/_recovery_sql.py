"""Least-privilege SQL for immutable recovery evidence and enablement."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record._integrity import canonical_digest
from ctower_kernel.record.recovery import (
    AnchorRecord,
    BackupRecord,
    InstallationIdentity,
    InventoryRevision,
    RestoreReport,
)

__all__: tuple[str, ...] = ()

_ROLES = frozenset({"ctower_backup", "ctower_anchor", "ctower_restore"})


def insert_backup(dsn: str, backup: BackupRecord) -> None:
    with _connection(dsn, "ctower_backup") as connection:
        connection.execute(
            """
            INSERT INTO backup_manifests (
                backup_id, tenant_id, manifest_sha256, backup_kind, repository_ref,
                base_backup_sha256, wal_start_lsn, wal_stop_lsn, logical_dump_sha256,
                object_manifest_sha256, migration_manifest_sha256, key_reference,
                key_version, started_at, completed_at
            ) VALUES (
                %s, %s, %s, 'daily_full', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (backup_id) DO NOTHING
            """,
            (
                backup.backup_id,
                backup.tenant_id,
                _digest(backup.manifest_sha256),
                backup.repository_ref,
                _digest(backup.base_backup_sha256),
                backup.wal_start_lsn,
                backup.wal_stop_lsn,
                _digest(backup.logical_dump_sha256),
                _digest(backup.object_manifest_sha256),
                _digest(backup.migration_manifest_sha256),
                backup.key_reference,
                backup.key_version,
                backup.started_at,
                backup.completed_at,
            ),
        )
        _require_digest_identity(
            connection,
            "SELECT tenant_id, manifest_sha256 AS digest FROM backup_manifests "
            "WHERE backup_id = %s",
            backup.backup_id,
            backup.tenant_id,
            backup.manifest_sha256,
            label="backup",
        )
        connection.execute(
            """
            INSERT INTO backup_verification_receipts (
                receipt_id, backup_id, tenant_id, repository_object_version,
                base_verified, wal_verified, logical_dump_verified, objects_verified,
                key_reference_verified, verified_at
            ) VALUES (%s, %s, %s, %s, true, true, true, true, true, %s)
            ON CONFLICT (backup_id, repository_object_version) DO NOTHING
            """,
            (
                backup.verification_receipt_id,
                backup.backup_id,
                backup.tenant_id,
                backup.repository_object_version,
                backup.completed_at,
            ),
        )


def insert_anchor(dsn: str, anchor: AnchorRecord) -> None:
    with _connection(dsn, "ctower_anchor") as connection:
        connection.execute(
            """
            INSERT INTO record_anchor_receipts (
                anchor_id, tenant_id, source_start_position, source_end_position,
                previous_anchor_sha256, anchor_sha256, signature, signing_key_reference,
                signing_key_version, public_key_sha256, object_key, object_version, anchored_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (anchor_id) DO NOTHING
            """,
            (
                anchor.anchor_id,
                anchor.tenant_id,
                anchor.source_start_position,
                anchor.source_end_position,
                _optional_digest(anchor.previous_anchor_sha256),
                _digest(anchor.anchor_sha256),
                anchor.signature,
                anchor.signing_key_reference,
                anchor.signing_key_version,
                _digest(anchor.public_key_sha256),
                anchor.object_key,
                anchor.object_version,
                anchor.anchored_at,
            ),
        )
        _require_digest_identity(
            connection,
            "SELECT tenant_id, anchor_sha256 AS digest FROM record_anchor_receipts "
            "WHERE anchor_id = %s",
            anchor.anchor_id,
            anchor.tenant_id,
            anchor.anchor_sha256,
            label="anchor",
        )


def insert_installation(dsn: str, identity: InstallationIdentity) -> None:
    with _connection(dsn, "ctower_restore") as connection:
        connection.execute(
            """
            INSERT INTO installation_identities (
                installation_id, tenant_id, identity_ref, identity_sha256, signature,
                signing_key_reference, signing_key_version, public_key_sha256, issued_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (installation_id) DO NOTHING
            """,
            (
                identity.installation_id,
                identity.tenant_id,
                identity.identity_ref,
                _digest(identity.identity_sha256),
                identity.signature,
                identity.signing_key_reference,
                identity.signing_key_version,
                _digest(identity.public_key_sha256),
                identity.issued_at,
            ),
        )
        _require_digest_identity(
            connection,
            "SELECT tenant_id, identity_sha256 AS digest FROM installation_identities "
            "WHERE installation_id = %s",
            identity.installation_id,
            identity.tenant_id,
            identity.identity_sha256,
            label="installation",
        )


def insert_inventory(dsn: str, inventory: InventoryRevision) -> None:
    with _connection(dsn, "ctower_restore") as connection:
        connection.execute(
            """
            INSERT INTO expected_source_inventory_revisions (
                inventory_revision_id, tenant_id, schema_id, revision_number,
                revision_sha256, previous_revision_sha256, signature,
                signing_key_reference, signing_key_version, public_key_sha256,
                object_key, object_version, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (inventory_revision_id) DO NOTHING
            """,
            (
                inventory.inventory_revision_id,
                inventory.tenant_id,
                inventory.schema_id,
                inventory.revision_number,
                _digest(inventory.revision_sha256),
                _optional_digest(inventory.previous_revision_sha256),
                inventory.signature,
                inventory.signing_key_reference,
                inventory.signing_key_version,
                _digest(inventory.public_key_sha256),
                inventory.object_key,
                inventory.object_version,
                inventory.created_at,
            ),
        )
        _require_digest_identity(
            connection,
            "SELECT tenant_id, revision_sha256 AS digest "
            "FROM expected_source_inventory_revisions WHERE inventory_revision_id = %s",
            inventory.inventory_revision_id,
            inventory.tenant_id,
            inventory.revision_sha256,
            label="inventory",
        )
        connection.cursor().executemany(
            """
            INSERT INTO expected_source_inventory_entries (
                inventory_revision_id, tenant_id, source_key, source_kind, activation,
                cursor_declaration, source_count, trust_root_ref, trusted_cursor,
                activation_event_ref
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (inventory_revision_id, source_key) DO NOTHING
            """,
            (
                (
                    inventory.inventory_revision_id,
                    inventory.tenant_id,
                    source.source_key,
                    source.source_kind,
                    source.activation,
                    source.cursor_declaration,
                    source.source_count,
                    source.trust_root_ref,
                    source.trusted_cursor,
                    source.activation_event_ref,
                )
                for source in inventory.sources
            ),
        )


def begin_restore(
    dsn: str,
    *,
    restore_run_id: UUID,
    tenant_id: UUID,
    installation_id: UUID,
    backup_id: UUID,
    inventory_revision_id: UUID,
    accepted_source_position: int,
    restored_acceptance_position: int,
    artifact_rpo_seconds: int,
    started_at: datetime,
) -> None:
    accepted_rpo = max(accepted_source_position - restored_acceptance_position, 0)
    with _connection(dsn, "ctower_restore") as connection:
        connection.execute(
            """
            INSERT INTO restore_runs (
                restore_run_id, tenant_id, installation_id, backup_id,
                inventory_revision_id, status, accepted_source_position,
                restored_acceptance_position, accepted_rpo_seconds,
                artifact_rpo_seconds, started_at
            ) VALUES (%s, %s, %s, %s, %s, 'quarantined', %s, %s, %s, %s, %s)
            ON CONFLICT (restore_run_id) DO NOTHING
            """,
            (
                restore_run_id,
                tenant_id,
                installation_id,
                backup_id,
                inventory_revision_id,
                accepted_source_position,
                restored_acceptance_position,
                accepted_rpo,
                artifact_rpo_seconds,
                started_at,
            ),
        )


def complete_restore(dsn: str, report: RestoreReport) -> str:
    report_sha256 = canonical_digest(report.model_dump(mode="json"))
    with _connection(dsn, "ctower_restore") as connection:
        existing = connection.execute(
            """
            SELECT report_sha256 FROM restore_runs
            WHERE restore_run_id = %s AND tenant_id = %s AND installation_id = %s
            FOR UPDATE
            """,
            (report.restore_run_id, report.tenant_id, report.installation_id),
        ).fetchone()
        if existing is not None and existing["report_sha256"] is not None:
            if _stored_digest(existing["report_sha256"]) != _digest(report_sha256):
                raise ValueError("restore replay changed the completed report")
            return report_sha256
        _insert_steps(connection, report)
        _insert_findings(connection, report)
        status = "quarantined" if report.enablement_eligible else "failed"
        updated = connection.execute(
            """
            UPDATE restore_runs AS run
            SET status = %s, completed_at = %s, report_sha256 = %s
            FROM expected_source_inventory_revisions AS inventory
            WHERE run.inventory_revision_id = inventory.inventory_revision_id
              AND run.tenant_id = inventory.tenant_id
              AND run.restore_run_id = %s AND run.tenant_id = %s
              AND run.installation_id = %s AND run.backup_id = %s
              AND run.accepted_source_position = %s
              AND run.restored_acceptance_position = %s
              AND run.artifact_rpo_seconds = %s
              AND inventory.revision_sha256 = %s
              AND run.status = 'quarantined' AND run.completed_at IS NULL
            """,
            (
                status,
                report.completed_at,
                _digest(report_sha256),
                report.restore_run_id,
                report.tenant_id,
                report.installation_id,
                report.backup_id,
                report.accepted_source_position,
                report.restored_acceptance_position,
                report.artifact_rpo_seconds,
                _digest(report.inventory_revision_sha256),
            ),
        )
        if updated.rowcount != 1:
            raise ValueError("restore report does not match one open quarantined run")
    return report_sha256


def enable_restore(
    dsn: str,
    *,
    enablement_id: UUID,
    restore_run_id: UUID,
    tenant_id: UUID,
    installation_id: UUID,
    report_sha256: str,
    authority_ref: str,
    enabled_at: datetime,
) -> None:
    with _connection(dsn, "ctower_restore") as connection:
        replay = connection.execute(
            """
            SELECT 1 FROM restore_enablement_receipts
            WHERE restore_run_id = %s AND tenant_id = %s AND installation_id = %s
              AND report_sha256 = %s AND authenticated_authority_ref = %s
            """,
            (
                restore_run_id,
                tenant_id,
                installation_id,
                _digest(report_sha256),
                authority_ref,
            ),
        ).fetchone()
        if replay is not None:
            return
        eligible = connection.execute(
            """
            SELECT inventory.revision_sha256
            FROM restore_runs AS run
            JOIN expected_source_inventory_revisions AS inventory
              ON inventory.inventory_revision_id = run.inventory_revision_id
             AND inventory.tenant_id = run.tenant_id
            WHERE run.restore_run_id = %s AND run.tenant_id = %s
              AND run.installation_id = %s AND run.status = 'quarantined'
              AND run.completed_at IS NOT NULL AND run.report_sha256 = %s
              AND run.accepted_rpo_seconds = 0 AND run.artifact_rpo_seconds <= 300
              AND (
                SELECT count(*) FROM restore_steps AS step
                WHERE step.restore_run_id = run.restore_run_id AND step.outcome = 'pass'
              ) = 12
              AND NOT EXISTS (
                SELECT 1 FROM restore_findings AS finding
                LEFT JOIN restore_finding_resolutions AS resolution
                  ON resolution.finding_id = finding.finding_id
                WHERE finding.restore_run_id = run.restore_run_id
                  AND resolution.finding_id IS NULL
              )
            FOR UPDATE OF run
            """,
            (
                restore_run_id,
                tenant_id,
                installation_id,
                _digest(report_sha256),
            ),
        ).fetchone()
        if eligible is None:
            raise ValueError("restore enablement denied by unresolved quarantine evidence")
        connection.execute(
            """
            INSERT INTO restore_enablement_receipts (
                enablement_id, restore_run_id, tenant_id, installation_id,
                report_sha256, inventory_revision_sha256, authenticated_authority_ref,
                ordinary_reads_enabled, effects_enabled, enabled_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, true, false, %s)
            """,
            (
                enablement_id,
                restore_run_id,
                tenant_id,
                installation_id,
                _digest(report_sha256),
                eligible["revision_sha256"],
                authority_ref,
                enabled_at,
            ),
        )
        connection.execute(
            "UPDATE restore_runs SET status = 'enabled' WHERE restore_run_id = %s",
            (restore_run_id,),
        )


def reads_enabled(
    dsn: str,
    *,
    tenant_id: UUID,
    installation_id: UUID,
    report_sha256: str,
) -> bool:
    with _connection(dsn, "ctower_restore") as connection:
        row = connection.execute(
            """
            SELECT 1 FROM restore_enablement_receipts
            WHERE tenant_id = %s AND installation_id = %s AND report_sha256 = %s
              AND ordinary_reads_enabled AND NOT effects_enabled
            """,
            (tenant_id, installation_id, _digest(report_sha256)),
        ).fetchone()
    return row is not None


def _insert_steps(
    connection: psycopg.Connection[dict[str, object]],
    report: RestoreReport,
) -> None:
    connection.cursor().executemany(
        """
        INSERT INTO restore_steps (
            restore_run_id, tenant_id, step_sequence, step_kind, outcome,
            evidence_sha256, detail, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (
                report.restore_run_id,
                report.tenant_id,
                sequence,
                step.kind.value,
                step.outcome,
                _digest(step.evidence_sha256),
                step.detail,
                report.completed_at,
            )
            for sequence, step in enumerate(report.steps, 1)
        ),
    )


def _insert_findings(
    connection: psycopg.Connection[dict[str, object]],
    report: RestoreReport,
) -> None:
    connection.cursor().executemany(
        """
        INSERT INTO restore_findings (
            finding_id, restore_run_id, tenant_id, finding_key, severity,
            reason, evidence_sha256, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (
                uuid5(NAMESPACE_URL, f"ctower:{report.restore_run_id}:{finding.key}"),
                report.restore_run_id,
                report.tenant_id,
                finding.key,
                finding.severity,
                finding.reason,
                _digest(finding.evidence_sha256),
                report.completed_at,
            )
            for finding in report.findings
        ),
    )


def _connection(
    dsn: str,
    role: str,
) -> psycopg.Connection[dict[str, object]]:
    if role not in _ROLES:
        raise ValueError("unknown recovery role")
    connection = psycopg.connect(dsn, row_factory=dict_row)
    connection.execute(f"SET ROLE {role}")
    return connection


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _optional_digest(value: str | None) -> bytes | None:
    return _digest(value) if value is not None else None


def _require_digest_identity(
    connection: psycopg.Connection[dict[str, object]],
    query: str,
    identifier: UUID,
    tenant_id: UUID,
    digest: str,
    *,
    label: str,
) -> None:
    row = connection.execute(query, (identifier,)).fetchone()
    if (
        row is None
        or row["tenant_id"] != tenant_id
        or _stored_digest(row["digest"]) != _digest(digest)
    ):
        raise ValueError(f"{label} replay changed immutable identity")


def _stored_digest(value: object) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("database digest has an unexpected representation")
    return bytes(value)
