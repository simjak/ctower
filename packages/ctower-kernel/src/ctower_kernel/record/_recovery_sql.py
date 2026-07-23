"""Least-privilege SQL for immutable recovery evidence and enablement."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record._integrity import anchor_digest, canonical_digest
from ctower_kernel.record._recovery_replay import (
    lock_recovery_chain,
    require_anchor_predecessor,
    require_anchor_replay,
    require_exact_row,
    require_inventory_predecessor,
    require_inventory_replay,
)
from ctower_kernel.record.recovery import (
    AnchorRecord,
    BackupRecord,
    InstallationIdentity,
    InventoryRevision,
    RecoveryReplayConflictError,
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
            ON CONFLICT DO NOTHING
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
        require_exact_row(
            connection,
            """
            SELECT 1 FROM backup_manifests
            WHERE backup_id = %s AND tenant_id = %s AND manifest_sha256 = %s
              AND backup_kind = 'daily_full' AND repository_ref = %s
              AND base_backup_sha256 = %s AND wal_start_lsn = %s
              AND wal_stop_lsn = %s AND logical_dump_sha256 = %s
              AND object_manifest_sha256 = %s AND migration_manifest_sha256 = %s
              AND key_reference = %s AND key_version = %s
              AND started_at = %s AND completed_at = %s
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
            label="backup",
        )
        connection.execute(
            """
            INSERT INTO backup_verification_receipts (
                receipt_id, backup_id, tenant_id, repository_object_version,
                base_verified, wal_verified, logical_dump_verified, objects_verified,
                key_reference_verified, verified_at
            ) VALUES (%s, %s, %s, %s, true, true, true, true, true, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                backup.verification_receipt_id,
                backup.backup_id,
                backup.tenant_id,
                backup.repository_object_version,
                backup.completed_at,
            ),
        )
        require_exact_row(
            connection,
            """
            SELECT 1 FROM backup_verification_receipts
            WHERE receipt_id = %s AND backup_id = %s AND tenant_id = %s
              AND repository_object_version = %s
              AND base_verified AND wal_verified AND logical_dump_verified
              AND objects_verified AND key_reference_verified AND verified_at = %s
            """,
            (
                backup.verification_receipt_id,
                backup.backup_id,
                backup.tenant_id,
                backup.repository_object_version,
                backup.completed_at,
            ),
            label="backup verification receipt",
        )


def insert_anchor(dsn: str, anchor: AnchorRecord) -> None:
    with _connection(dsn, "ctower_anchor") as connection:
        existing = connection.execute(
            "SELECT 1 FROM record_anchor_receipts WHERE anchor_id = %s",
            (anchor.anchor_id,),
        ).fetchone()
        if existing is not None:
            require_anchor_replay(connection, anchor)
            return
        lock_recovery_chain(connection, anchor.tenant_id, "anchor")
        previous = connection.execute(
            """
            SELECT source_end_position, anchor_sha256
            FROM record_anchor_receipts
            WHERE tenant_id = %s
            ORDER BY source_end_position DESC
            LIMIT 1
            """,
            (anchor.tenant_id,),
        ).fetchone()
        require_anchor_predecessor(anchor, previous)
        roots = connection.execute(
            """
            SELECT acceptance_position, command_root
            FROM durability_acceptance_confirmations
            WHERE tenant_id = %s
              AND acceptance_position BETWEEN %s AND %s
            ORDER BY acceptance_position
            """,
            (
                anchor.tenant_id,
                anchor.source_start_position,
                anchor.source_end_position,
            ),
        ).fetchall()
        entries = tuple(
            (
                cast(int, row["acceptance_position"]),
                f"sha256:{_stored_digest(row['command_root']).hex()}",
            )
            for row in roots
        )
        expected_positions = tuple(
            range(anchor.source_start_position, anchor.source_end_position + 1)
        )
        if tuple(position for position, _digest_value in entries) != expected_positions:
            raise ValueError("anchor range is not exact accepted Record coverage")
        if anchor_digest(anchor.previous_anchor_sha256, entries) != anchor.anchor_sha256:
            raise ValueError("anchor digest does not bind persisted accepted roots")
        connection.execute(
            """
            INSERT INTO record_anchor_receipts (
                anchor_id, tenant_id, source_start_position, source_end_position,
                previous_anchor_sha256, anchor_sha256, signature, signing_key_reference,
                signing_key_version, public_key_sha256, object_key, object_version, anchored_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        require_anchor_replay(connection, anchor)


def insert_installation(dsn: str, identity: InstallationIdentity) -> None:
    with _connection(dsn, "ctower_restore") as connection:
        connection.execute(
            """
            INSERT INTO installation_identities (
                installation_id, tenant_id, identity_ref, identity_sha256, signature,
                signing_key_reference, signing_key_version, public_key_sha256, issued_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
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
        require_exact_row(
            connection,
            """
            SELECT 1 FROM installation_identities
            WHERE installation_id = %s AND tenant_id = %s AND identity_ref = %s
              AND identity_sha256 = %s AND signature = %s
              AND signing_key_reference = %s AND signing_key_version = %s
              AND public_key_sha256 = %s AND issued_at = %s
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
            label="installation",
        )


def insert_inventory(dsn: str, inventory: InventoryRevision) -> None:
    with _connection(dsn, "ctower_restore") as connection:
        existing = connection.execute(
            """
            SELECT 1 FROM expected_source_inventory_revisions
            WHERE inventory_revision_id = %s
            """,
            (inventory.inventory_revision_id,),
        ).fetchone()
        if existing is not None:
            require_inventory_replay(connection, inventory)
            return
        lock_recovery_chain(connection, inventory.tenant_id, "inventory")
        previous = connection.execute(
            """
            SELECT revision_number, revision_sha256
            FROM expected_source_inventory_revisions
            WHERE tenant_id = %s
            ORDER BY revision_number DESC
            LIMIT 1
            """,
            (inventory.tenant_id,),
        ).fetchone()
        require_inventory_predecessor(inventory, previous)
        connection.execute(
            """
            INSERT INTO expected_source_inventory_revisions (
                inventory_revision_id, tenant_id, schema_id, revision_number,
                revision_sha256, previous_revision_sha256, signature,
                signing_key_reference, signing_key_version, public_key_sha256,
                object_key, object_version, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        connection.cursor().executemany(
            """
            INSERT INTO expected_source_inventory_entries (
                inventory_revision_id, tenant_id, source_key, source_kind, activation,
                cursor_declaration, source_count, trust_root_ref, trusted_cursor,
                activation_event_ref
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        require_inventory_replay(connection, inventory)


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
    if restored_acceptance_position > accepted_source_position:
        raise ValueError("restored position cannot exceed accepted source position")
    accepted_rpo = accepted_source_position - restored_acceptance_position
    with _connection(dsn, "ctower_restore") as connection:
        persisted = connection.execute(
            """
            SELECT COALESCE(max(acceptance_position), 0) AS value
            FROM durability_acceptance_confirmations
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        ).fetchone()
        if persisted is None or cast(int, persisted["value"]) != accepted_source_position:
            raise ValueError("accepted source position does not match persisted Record facts")
        connection.execute(
            """
            INSERT INTO restore_runs (
                restore_run_id, tenant_id, installation_id, backup_id,
                inventory_revision_id, status, accepted_source_position,
                restored_acceptance_position, accepted_rpo_seconds,
                artifact_rpo_seconds, started_at
            ) VALUES (%s, %s, %s, %s, %s, 'quarantined', %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
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
        require_exact_row(
            connection,
            """
            SELECT 1 FROM restore_runs
            WHERE restore_run_id = %s AND tenant_id = %s AND installation_id = %s
              AND backup_id = %s AND inventory_revision_id = %s
              AND accepted_source_position = %s AND restored_acceptance_position = %s
              AND accepted_rpo_seconds = %s AND artifact_rpo_seconds = %s
              AND started_at = %s
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
            label="restore run",
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
                raise RecoveryReplayConflictError("restore replay changed the completed report")
            return report_sha256
        _insert_steps(connection, report)
        _insert_findings(connection, report)
        persisted_eligible = _persisted_restore_eligible(connection, report)
        if persisted_eligible != report.enablement_eligible:
            raise ValueError("persisted restore facts disagree with derived report eligibility")
        status = "quarantined" if persisted_eligible else "failed"
        updated = connection.execute(
            """
            UPDATE restore_runs AS run
            SET status = %s, completed_at = %s, rto_seconds = %s, report_sha256 = %s
            FROM expected_source_inventory_revisions AS inventory
            WHERE run.inventory_revision_id = inventory.inventory_revision_id
              AND run.tenant_id = inventory.tenant_id
              AND run.restore_run_id = %s AND run.tenant_id = %s
              AND run.installation_id = %s AND run.backup_id = %s
              AND run.accepted_source_position = %s
              AND run.restored_acceptance_position = %s
              AND run.artifact_rpo_seconds = %s
              AND run.started_at = %s
              AND %s >= run.started_at
              AND EXTRACT(EPOCH FROM (%s - run.started_at))::integer = %s
              AND inventory.revision_sha256 = %s
              AND run.status = 'quarantined' AND run.completed_at IS NULL
            """,
            (
                status,
                report.completed_at,
                report.rto_seconds,
                _digest(report_sha256),
                report.restore_run_id,
                report.tenant_id,
                report.installation_id,
                report.backup_id,
                report.accepted_source_position,
                report.restored_acceptance_position,
                report.artifact_rpo_seconds,
                report.started_at,
                report.completed_at,
                report.completed_at,
                report.rto_seconds,
                _digest(report.inventory_revision_sha256),
            ),
        )
        if updated.rowcount != 1:
            raise ValueError("restore report does not match one open quarantined run")
    return report_sha256


def _persisted_restore_eligible(
    connection: psycopg.Connection[dict[str, object]],
    report: RestoreReport,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM restore_runs AS run
        JOIN expected_source_inventory_revisions AS inventory
          ON inventory.inventory_revision_id = run.inventory_revision_id
         AND inventory.tenant_id = run.tenant_id
        WHERE run.restore_run_id = %s AND run.tenant_id = %s
          AND run.installation_id = %s AND run.backup_id = %s
          AND run.accepted_source_position = %s
          AND run.restored_acceptance_position = %s
          AND run.accepted_rpo_seconds = 0 AND run.artifact_rpo_seconds = %s
          AND run.artifact_rpo_seconds <= 300
          AND run.started_at = %s
          AND %s >= run.started_at
          AND EXTRACT(EPOCH FROM (%s - run.started_at))::integer = %s
          AND inventory.revision_sha256 = %s
          AND %s BETWEEN 0 AND 14400
          AND (
              SELECT array_agg(step.step_kind ORDER BY step.step_sequence)
              FROM restore_steps AS step
              WHERE step.restore_run_id = run.restore_run_id
                AND step.tenant_id = run.tenant_id
                AND step.outcome = 'pass'
          ) = ARRAY[
              'database_recovered', 'object_access_recovered', 'key_access_recovered',
              'erasure_reapplied', 'migrations_verified', 'chains_verified',
              'anchors_verified', 'objects_verified', 'tombstones_verified',
              'inventory_verified', 'journals_reconciled', 'synthetic_verified'
          ]::text[]
          AND NOT EXISTS (
              SELECT 1 FROM restore_findings AS finding
              WHERE finding.restore_run_id = run.restore_run_id
          )
        """,
        (
            report.restore_run_id,
            report.tenant_id,
            report.installation_id,
            report.backup_id,
            report.accepted_source_position,
            report.restored_acceptance_position,
            report.artifact_rpo_seconds,
            report.started_at,
            report.completed_at,
            report.completed_at,
            report.rto_seconds,
            _digest(report.inventory_revision_sha256),
            report.rto_seconds,
        ),
    ).fetchone()
    return row is not None


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
            WHERE restore_run_id = %s OR enablement_id = %s
            """,
            (restore_run_id, enablement_id),
        ).fetchone()
        if replay is not None:
            require_exact_row(
                connection,
                """
                SELECT 1 FROM restore_enablement_receipts
                WHERE enablement_id = %s AND restore_run_id = %s
                  AND tenant_id = %s AND installation_id = %s
                  AND report_sha256 = %s AND authenticated_authority_ref = %s
                  AND ordinary_reads_enabled AND NOT effects_enabled AND enabled_at = %s
                """,
                (
                    enablement_id,
                    restore_run_id,
                    tenant_id,
                    installation_id,
                    _digest(report_sha256),
                    authority_ref,
                    enabled_at,
                ),
                label="restore enablement receipt",
            )
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
              AND run.accepted_source_position = run.restored_acceptance_position
              AND run.accepted_rpo_seconds = 0 AND run.artifact_rpo_seconds <= 300
              AND run.rto_seconds BETWEEN 0 AND 14400
              AND (
                SELECT array_agg(step.step_kind ORDER BY step.step_sequence)
                FROM restore_steps AS step
                WHERE step.restore_run_id = run.restore_run_id
                  AND step.tenant_id = run.tenant_id AND step.outcome = 'pass'
              ) = ARRAY[
                'database_recovered', 'object_access_recovered', 'key_access_recovered',
                'erasure_reapplied', 'migrations_verified', 'chains_verified',
                'anchors_verified', 'objects_verified', 'tombstones_verified',
                'inventory_verified', 'journals_reconciled', 'synthetic_verified'
              ]::text[]
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


def _stored_digest(value: object) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("database digest has an unexpected representation")
    return bytes(value)
