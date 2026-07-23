REVOKE ALL ON object_upload_receipts, object_backfill_receipts,
    object_erasure_intents, object_erasure_tombstones,
    backup_manifests, backup_verification_receipts,
    record_anchor_receipts, installation_identities,
    expected_source_inventory_revisions, expected_source_inventory_entries,
    restore_runs, restore_steps, restore_findings, restore_finding_resolutions,
    restore_enablement_receipts
    FROM PUBLIC, ctower_svc, ctower_projection, ctower_object, ctower_backup,
    ctower_anchor, ctower_restore;

GRANT USAGE ON SCHEMA public
    TO ctower_object, ctower_backup, ctower_anchor, ctower_restore;

GRANT SELECT ON proof_objects, object_upload_receipts, object_backfill_receipts,
    object_erasure_intents, object_erasure_tombstones TO ctower_svc;
GRANT INSERT ON object_upload_receipts, object_backfill_receipts,
    object_erasure_intents, object_erasure_tombstones TO ctower_svc;
GRANT UPDATE (
    content, storage_state, object_key, object_version, ciphertext_sha256,
    key_reference, key_version, wrapped_key_sha256, external_verified_at
) ON proof_objects TO ctower_svc;

GRANT SELECT ON proof_objects, object_upload_receipts, object_backfill_receipts,
    object_erasure_intents, object_erasure_tombstones TO ctower_object;
GRANT INSERT ON object_upload_receipts, object_backfill_receipts,
    object_erasure_intents, object_erasure_tombstones TO ctower_object;
GRANT UPDATE (
    content, storage_state, object_key, object_version, ciphertext_sha256,
    key_reference, key_version, wrapped_key_sha256, external_verified_at
) ON proof_objects TO ctower_object;

GRANT SELECT, INSERT ON backup_manifests, backup_verification_receipts TO ctower_backup;
GRANT SELECT ON proof_objects, object_upload_receipts, object_erasure_intents,
    object_erasure_tombstones,
    expected_source_inventory_revisions, expected_source_inventory_entries
    TO ctower_backup;

GRANT SELECT, INSERT ON record_anchor_receipts TO ctower_anchor;
GRANT SELECT ON durability_acknowledgements, durability_acceptance_confirmations
    TO ctower_anchor;

GRANT SELECT, INSERT ON installation_identities,
    expected_source_inventory_revisions, expected_source_inventory_entries,
    restore_steps, restore_findings, restore_finding_resolutions,
    restore_enablement_receipts TO ctower_restore;
GRANT SELECT, INSERT ON restore_runs TO ctower_restore;
GRANT UPDATE (status, completed_at, rto_seconds, report_sha256)
    ON restore_runs TO ctower_restore;
GRANT SELECT ON backup_manifests, backup_verification_receipts,
    record_anchor_receipts, proof_objects, object_upload_receipts,
    object_erasure_intents, object_erasure_tombstones, events, command_results,
    durability_acknowledgements, durability_acceptance_confirmations
    TO ctower_restore;

GRANT SELECT ON installation_identities, restore_runs, restore_findings,
    restore_finding_resolutions, restore_enablement_receipts TO ctower_svc;
GRANT SELECT ON backup_manifests, backup_verification_receipts,
    record_anchor_receipts, expected_source_inventory_revisions,
    expected_source_inventory_entries TO ctower_svc;

REVOKE INSERT, UPDATE, DELETE ON restore_runs, restore_steps, restore_findings,
    restore_finding_resolutions, restore_enablement_receipts FROM ctower_svc;
REVOKE INSERT, UPDATE, DELETE ON backup_manifests, backup_verification_receipts,
    record_anchor_receipts FROM ctower_svc;
