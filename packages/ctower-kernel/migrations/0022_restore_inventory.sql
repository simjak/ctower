CREATE TABLE installation_identities (
    installation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    identity_ref text NOT NULL CHECK (identity_ref ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    identity_sha256 bytea NOT NULL CHECK (octet_length(identity_sha256) = 32),
    signature text NOT NULL CHECK (length(signature) BETWEEN 1 AND 4096),
    signing_key_reference text NOT NULL CHECK (
        signing_key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'
    ),
    signing_key_version text NOT NULL CHECK (
        signing_key_version ~ '^[A-Za-z0-9._:-]{1,128}$'
    ),
    public_key_sha256 bytea NOT NULL CHECK (octet_length(public_key_sha256) = 32),
    issued_at timestamptz NOT NULL,
    UNIQUE (tenant_id, identity_ref),
    UNIQUE (installation_id, tenant_id)
);

CREATE TABLE expected_source_inventory_revisions (
    inventory_revision_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    schema_id text NOT NULL CHECK (schema_id = 'ctower.expected-source-inventory/v1'),
    revision_number integer NOT NULL CHECK (revision_number >= 1),
    revision_sha256 bytea NOT NULL CHECK (octet_length(revision_sha256) = 32),
    previous_revision_sha256 bytea CHECK (
        previous_revision_sha256 IS NULL OR octet_length(previous_revision_sha256) = 32
    ),
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
    created_at timestamptz NOT NULL,
    UNIQUE (tenant_id, revision_number),
    UNIQUE (tenant_id, revision_sha256),
    UNIQUE (inventory_revision_id, tenant_id)
);

CREATE TABLE expected_source_inventory_entries (
    inventory_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    source_key text NOT NULL CHECK (source_key ~ '^[a-z][a-z0-9._-]*$'),
    source_kind text NOT NULL CHECK (source_kind IN (
        'root_supervisor_journal', 'effect_journal', 'provider_journal'
    )),
    activation text NOT NULL CHECK (activation IN ('not_exercised', 'active')),
    cursor_declaration text NOT NULL CHECK (
        cursor_declaration IN ('zero_source', 'trusted_cursor')
    ),
    source_count bigint NOT NULL CHECK (source_count >= 0),
    trust_root_ref text,
    trusted_cursor text,
    activation_event_ref text,
    PRIMARY KEY (inventory_revision_id, source_key),
    FOREIGN KEY (inventory_revision_id, tenant_id)
        REFERENCES expected_source_inventory_revisions(inventory_revision_id, tenant_id),
    CHECK (
        (
            activation = 'not_exercised'
            AND cursor_declaration = 'zero_source'
            AND source_count = 0
            AND trust_root_ref IS NULL
            AND trusted_cursor IS NULL
            AND activation_event_ref IS NULL
        )
        OR (
            activation = 'active'
            AND cursor_declaration = 'trusted_cursor'
            AND source_count > 0
            AND length(trust_root_ref) BETWEEN 1 AND 255
            AND length(trusted_cursor) BETWEEN 1 AND 255
            AND length(activation_event_ref) BETWEEN 1 AND 255
        )
    )
);

CREATE TABLE restore_runs (
    restore_run_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    installation_id uuid NOT NULL,
    backup_id uuid NOT NULL,
    inventory_revision_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('quarantined', 'failed', 'enabled')),
    accepted_source_position bigint NOT NULL CHECK (accepted_source_position >= 0),
    restored_acceptance_position bigint NOT NULL CHECK (restored_acceptance_position >= 0),
    accepted_rpo_seconds integer NOT NULL CHECK (accepted_rpo_seconds >= 0),
    artifact_rpo_seconds integer NOT NULL CHECK (artifact_rpo_seconds >= 0),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    report_sha256 bytea CHECK (report_sha256 IS NULL OR octet_length(report_sha256) = 32),
    FOREIGN KEY (installation_id, tenant_id)
        REFERENCES installation_identities(installation_id, tenant_id),
    FOREIGN KEY (backup_id, tenant_id) REFERENCES backup_manifests(backup_id, tenant_id),
    FOREIGN KEY (inventory_revision_id, tenant_id)
        REFERENCES expected_source_inventory_revisions(inventory_revision_id, tenant_id),
    CHECK (
        (
            status = 'quarantined'
            AND (
                (completed_at IS NULL AND report_sha256 IS NULL)
                OR (completed_at IS NOT NULL AND report_sha256 IS NOT NULL)
            )
        )
        OR (
            status IN ('failed', 'enabled')
            AND completed_at IS NOT NULL
            AND completed_at >= started_at
            AND report_sha256 IS NOT NULL
        )
    ),
    UNIQUE (restore_run_id, tenant_id),
    UNIQUE (restore_run_id, tenant_id, installation_id)
);

CREATE TABLE restore_steps (
    restore_run_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    step_sequence integer NOT NULL CHECK (step_sequence BETWEEN 1 AND 12),
    step_kind text NOT NULL CHECK (step_kind IN (
        'database_recovered', 'object_access_recovered', 'key_access_recovered',
        'erasure_reapplied', 'migrations_verified', 'chains_verified',
        'anchors_verified', 'objects_verified', 'tombstones_verified',
        'inventory_verified', 'journals_reconciled', 'synthetic_verified'
    )),
    outcome text NOT NULL CHECK (outcome IN ('pass', 'fail')),
    evidence_sha256 bytea NOT NULL CHECK (octet_length(evidence_sha256) = 32),
    detail text NOT NULL CHECK (length(detail) BETWEEN 1 AND 500),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (restore_run_id, step_sequence),
    FOREIGN KEY (restore_run_id, tenant_id)
        REFERENCES restore_runs(restore_run_id, tenant_id)
);

CREATE TABLE restore_findings (
    finding_id uuid PRIMARY KEY,
    restore_run_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    finding_key text NOT NULL CHECK (finding_key ~ '^[a-z][a-z0-9._:-]*$'),
    severity text NOT NULL CHECK (severity IN ('critical', 'error')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    evidence_sha256 bytea NOT NULL CHECK (octet_length(evidence_sha256) = 32),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (restore_run_id, tenant_id)
        REFERENCES restore_runs(restore_run_id, tenant_id),
    UNIQUE (restore_run_id, finding_key)
);

CREATE TABLE restore_finding_resolutions (
    resolution_id uuid PRIMARY KEY,
    finding_id uuid NOT NULL REFERENCES restore_findings(finding_id),
    restore_run_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    authority_ref text NOT NULL CHECK (authority_ref ~ '^[a-z][a-z0-9._:/-]{2,255}$'),
    evidence_sha256 bytea NOT NULL CHECK (octet_length(evidence_sha256) = 32),
    resolved_at timestamptz NOT NULL,
    FOREIGN KEY (restore_run_id, tenant_id)
        REFERENCES restore_runs(restore_run_id, tenant_id),
    UNIQUE (finding_id)
);

CREATE TABLE restore_enablement_receipts (
    enablement_id uuid PRIMARY KEY,
    restore_run_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    installation_id uuid NOT NULL,
    report_sha256 bytea NOT NULL CHECK (octet_length(report_sha256) = 32),
    inventory_revision_sha256 bytea NOT NULL CHECK (
        octet_length(inventory_revision_sha256) = 32
    ),
    authenticated_authority_ref text NOT NULL CHECK (
        authenticated_authority_ref ~ '^[a-z][a-z0-9._:/-]{2,255}$'
    ),
    ordinary_reads_enabled boolean NOT NULL CHECK (ordinary_reads_enabled),
    effects_enabled boolean NOT NULL CHECK (NOT effects_enabled),
    enabled_at timestamptz NOT NULL,
    FOREIGN KEY (restore_run_id, tenant_id, installation_id)
        REFERENCES restore_runs(restore_run_id, tenant_id, installation_id),
    UNIQUE (restore_run_id),
    UNIQUE (tenant_id, installation_id, report_sha256)
);

CREATE TRIGGER installation_identities_immutable
    BEFORE UPDATE OR DELETE ON installation_identities
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER expected_source_inventory_revisions_immutable
    BEFORE UPDATE OR DELETE ON expected_source_inventory_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER expected_source_inventory_entries_immutable
    BEFORE UPDATE OR DELETE ON expected_source_inventory_entries
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER restore_steps_immutable
    BEFORE UPDATE OR DELETE ON restore_steps
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER restore_findings_immutable
    BEFORE UPDATE OR DELETE ON restore_findings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER restore_finding_resolutions_immutable
    BEFORE UPDATE OR DELETE ON restore_finding_resolutions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();
CREATE TRIGGER restore_enablement_receipts_immutable
    BEFORE UPDATE OR DELETE ON restore_enablement_receipts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_recovery_fact_mutation();

CREATE INDEX expected_source_inventory_latest
    ON expected_source_inventory_revisions (tenant_id, revision_number DESC);
CREATE INDEX restore_runs_installation
    ON restore_runs (tenant_id, installation_id, started_at DESC);
CREATE INDEX restore_findings_run
    ON restore_findings (restore_run_id, recorded_at);
