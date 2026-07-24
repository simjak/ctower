ALTER TABLE proof_objects
    ALTER COLUMN content DROP NOT NULL,
    ADD COLUMN storage_state text NOT NULL DEFAULT 'inline_compatible'
        CHECK (
            storage_state IN (
                'inline_compatible', 'external_verified', 'erasure_pending', 'erased'
            )
        ),
    ADD COLUMN object_key text,
    ADD COLUMN object_version text,
    ADD COLUMN ciphertext_sha256 bytea CHECK (
        ciphertext_sha256 IS NULL OR octet_length(ciphertext_sha256) = 32
    ),
    ADD COLUMN key_reference text CHECK (
        key_reference IS NULL OR key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'
    ),
    ADD COLUMN key_version text CHECK (
        key_version IS NULL OR key_version ~ '^[A-Za-z0-9._:-]{1,128}$'
    ),
    ADD COLUMN wrapped_key_sha256 bytea CHECK (
        wrapped_key_sha256 IS NULL OR octet_length(wrapped_key_sha256) = 32
    ),
    ADD COLUMN external_verified_at timestamptz,
    ADD CONSTRAINT proof_objects_storage_shape CHECK (
        (storage_state = 'inline_compatible' AND content IS NOT NULL)
        OR (
            storage_state IN ('external_verified', 'erasure_pending')
            AND object_key IS NOT NULL
            AND object_version IS NOT NULL
            AND ciphertext_sha256 IS NOT NULL
            AND key_reference IS NOT NULL
            AND key_version IS NOT NULL
            AND wrapped_key_sha256 IS NOT NULL
            AND external_verified_at IS NOT NULL
        )
        OR (
            storage_state = 'erased'
            AND content IS NULL
            AND object_key IS NULL
            AND object_version IS NULL
        )
    ),
    ADD CONSTRAINT proof_objects_external_locator_unique
        UNIQUE (tenant_id, object_key, object_version);

CREATE FUNCTION refuse_immutable_recovery_fact_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'recovery evidence is immutable' USING ERRCODE = '55000';
END
$$;

CREATE TABLE object_upload_receipts (
    receipt_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    object_key text NOT NULL CHECK (length(object_key) BETWEEN 1 AND 512),
    object_version text NOT NULL CHECK (length(object_version) BETWEEN 1 AND 256),
    ciphertext_sha256 bytea NOT NULL CHECK (octet_length(ciphertext_sha256) = 32),
    key_reference text NOT NULL CHECK (key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    key_version text NOT NULL CHECK (key_version ~ '^[A-Za-z0-9._:-]{1,128}$'),
    wrapped_key_sha256 bytea NOT NULL CHECK (octet_length(wrapped_key_sha256) = 32),
    uploaded_at timestamptz NOT NULL,
    verified_at timestamptz NOT NULL CHECK (verified_at >= uploaded_at),
    FOREIGN KEY (tenant_id, artifact_digest)
        REFERENCES proof_objects(tenant_id, artifact_digest),
    UNIQUE (tenant_id, artifact_digest, object_key, object_version)
);

CREATE TABLE object_backfill_receipts (
    receipt_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    before_sha256 bytea NOT NULL CHECK (octet_length(before_sha256) = 32),
    after_sha256 bytea NOT NULL CHECK (octet_length(after_sha256) = 32),
    object_version text NOT NULL CHECK (length(object_version) BETWEEN 1 AND 256),
    inline_cleared boolean NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (tenant_id, artifact_digest)
        REFERENCES proof_objects(tenant_id, artifact_digest),
    CHECK (before_sha256 = after_sha256),
    UNIQUE (tenant_id, artifact_digest, object_version)
);

CREATE TABLE object_erasure_tombstones (
    tombstone_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    erased_object_key text NOT NULL CHECK (length(erased_object_key) BETWEEN 1 AND 512),
    erased_object_version text NOT NULL CHECK (length(erased_object_version) BETWEEN 1 AND 256),
    erased_key_reference text NOT NULL CHECK (
        erased_key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'
    ),
    authority_ref text NOT NULL CHECK (authority_ref ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    erased_at timestamptz NOT NULL,
    UNIQUE (tenant_id, artifact_digest)
);

CREATE TABLE object_erasure_intents (
    erasure_intent_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    object_key text NOT NULL CHECK (length(object_key) BETWEEN 1 AND 512),
    object_version text NOT NULL CHECK (length(object_version) BETWEEN 1 AND 256),
    ciphertext_sha256 bytea NOT NULL CHECK (octet_length(ciphertext_sha256) = 32),
    key_reference text NOT NULL CHECK (key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    key_version text NOT NULL CHECK (key_version ~ '^[A-Za-z0-9._:-]{1,128}$'),
    wrapped_key_sha256 bytea NOT NULL CHECK (octet_length(wrapped_key_sha256) = 32),
    uploaded_at timestamptz NOT NULL,
    verified_at timestamptz NOT NULL CHECK (verified_at >= uploaded_at),
    authority_ref text NOT NULL CHECK (authority_ref ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    requested_at timestamptz NOT NULL,
    FOREIGN KEY (tenant_id, artifact_digest)
        REFERENCES proof_objects(tenant_id, artifact_digest),
    UNIQUE (tenant_id, artifact_digest)
);

ALTER TABLE object_erasure_tombstones
    ADD COLUMN erasure_intent_id uuid NOT NULL
        REFERENCES object_erasure_intents(erasure_intent_id),
    ADD CONSTRAINT object_erasure_tombstones_intent_unique UNIQUE (erasure_intent_id);

CREATE TABLE backup_manifests (
    backup_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    schema_id text NOT NULL CHECK (schema_id = 'ctower.backup-manifest/v1'),
    manifest_sha256 bytea NOT NULL CHECK (octet_length(manifest_sha256) = 32),
    backup_kind text NOT NULL CHECK (backup_kind = 'daily_full'),
    repository_ref text NOT NULL CHECK (repository_ref ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    repository_object_version text NOT NULL CHECK (
        length(repository_object_version) BETWEEN 1 AND 256
    ),
    base_backup_sha256 bytea NOT NULL CHECK (octet_length(base_backup_sha256) = 32),
    wal_start_lsn pg_lsn NOT NULL,
    wal_stop_lsn pg_lsn NOT NULL CHECK (wal_stop_lsn >= wal_start_lsn),
    logical_dump_sha256 bytea NOT NULL CHECK (octet_length(logical_dump_sha256) = 32),
    object_manifest_sha256 bytea NOT NULL CHECK (octet_length(object_manifest_sha256) = 32),
    migration_manifest_sha256 bytea NOT NULL CHECK (octet_length(migration_manifest_sha256) = 32),
    key_reference text NOT NULL CHECK (key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    key_version text NOT NULL CHECK (key_version ~ '^[A-Za-z0-9._:-]{1,128}$'),
    pgbackrest_sha256 bytea NOT NULL CHECK (octet_length(pgbackrest_sha256) = 32),
    pg_dump_sha256 bytea NOT NULL CHECK (octet_length(pg_dump_sha256) = 32),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL CHECK (completed_at >= started_at),
    UNIQUE (tenant_id, manifest_sha256),
    UNIQUE (backup_id, tenant_id, manifest_sha256)
);

ALTER TABLE backup_manifests ADD CONSTRAINT backup_manifests_id_tenant_unique
    UNIQUE (backup_id, tenant_id);

CREATE TABLE backup_verification_receipts (
    receipt_id uuid PRIMARY KEY,
    backup_id uuid NOT NULL REFERENCES backup_manifests(backup_id),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    manifest_sha256 bytea NOT NULL CHECK (octet_length(manifest_sha256) = 32),
    verified_at timestamptz NOT NULL,
    FOREIGN KEY (backup_id, tenant_id, manifest_sha256)
        REFERENCES backup_manifests(backup_id, tenant_id, manifest_sha256),
    UNIQUE (backup_id, manifest_sha256)
);

CREATE TABLE record_anchor_receipts (
    anchor_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    source_start_position bigint NOT NULL CHECK (source_start_position >= 1),
    source_end_position bigint NOT NULL CHECK (source_end_position >= source_start_position),
    previous_anchor_sha256 bytea CHECK (
        previous_anchor_sha256 IS NULL OR octet_length(previous_anchor_sha256) = 32
    ),
    anchor_sha256 bytea NOT NULL CHECK (octet_length(anchor_sha256) = 32),
    signature text NOT NULL CHECK (length(signature) BETWEEN 1 AND 4096),
    signing_key_reference text NOT NULL CHECK (
        signing_key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'
    ),
    signing_key_version text NOT NULL CHECK (
        signing_key_version ~ '^[A-Za-z0-9._:-]{1,128}$'
    ),
    public_key_sha256 bytea NOT NULL CHECK (octet_length(public_key_sha256) = 32),
    object_key text NOT NULL CHECK (length(object_key) BETWEEN 1 AND 512),
    object_version text NOT NULL CHECK (length(object_version) BETWEEN 1 AND 256),
    anchored_at timestamptz NOT NULL,
    FOREIGN KEY (tenant_id, previous_anchor_sha256)
        REFERENCES record_anchor_receipts(tenant_id, anchor_sha256),
    UNIQUE (tenant_id, source_start_position),
    UNIQUE (tenant_id, source_end_position),
    UNIQUE (tenant_id, previous_anchor_sha256),
    UNIQUE (tenant_id, anchor_sha256),
    UNIQUE (tenant_id, object_key, object_version)
);

CREATE UNIQUE INDEX record_anchor_receipts_one_genesis
    ON record_anchor_receipts (tenant_id)
    WHERE previous_anchor_sha256 IS NULL;

CREATE TRIGGER object_upload_receipts_immutable
    BEFORE UPDATE OR DELETE ON object_upload_receipts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER object_backfill_receipts_immutable
    BEFORE UPDATE OR DELETE ON object_backfill_receipts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER object_erasure_tombstones_immutable
    BEFORE UPDATE OR DELETE ON object_erasure_tombstones
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER object_erasure_intents_immutable
    BEFORE UPDATE OR DELETE ON object_erasure_intents
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER backup_manifests_immutable
    BEFORE UPDATE OR DELETE ON backup_manifests
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER backup_verification_receipts_immutable
    BEFORE UPDATE OR DELETE ON backup_verification_receipts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER record_anchor_receipts_immutable
    BEFORE UPDATE OR DELETE ON record_anchor_receipts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();

CREATE INDEX object_upload_receipts_digest
    ON object_upload_receipts (tenant_id, artifact_digest, verified_at);
CREATE INDEX object_erasure_tombstones_time
    ON object_erasure_tombstones (tenant_id, erased_at);
CREATE INDEX object_erasure_intents_requested
    ON object_erasure_intents (tenant_id, requested_at);
CREATE INDEX backup_manifests_completed
    ON backup_manifests (tenant_id, completed_at DESC);
CREATE INDEX record_anchor_receipts_watermark
    ON record_anchor_receipts (tenant_id, source_end_position DESC);
