ALTER TABLE migration_importer_credential_facts
    DROP CONSTRAINT migration_importer_credential_facts_lifecycle_check;
ALTER TABLE migration_importer_credential_facts
    ADD CONSTRAINT migration_importer_credential_facts_lifecycle_check
    CHECK (lifecycle IN ('pending', 'activated', 'revoked'));

CREATE TABLE migration_verified_artifacts (
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    artifact_kind text NOT NULL CHECK (artifact_kind IN (
        'source_selection', 'export_a', 'export_b', 'export_equality',
        'alias_map', 'import_plan', 'fence_registry'
    )),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    artifact_body jsonb NOT NULL CHECK (jsonb_typeof(artifact_body) = 'object'),
    reviewer_key_ref text,
    reviewer_key_version integer CHECK (reviewer_key_version >= 1),
    reviewer_key_digest bytea CHECK (octet_length(reviewer_key_digest) = 32),
    actor_principal_id uuid NOT NULL REFERENCES principals(principal_id),
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, artifact_kind),
    UNIQUE (run_id, artifact_digest),
    CHECK (
        (artifact_kind IN ('export_a', 'export_b')
            AND reviewer_key_ref IS NULL
            AND reviewer_key_version IS NULL
            AND reviewer_key_digest IS NULL)
        OR
        (artifact_kind NOT IN ('export_a', 'export_b')
            AND reviewer_key_ref IS NOT NULL
            AND reviewer_key_version IS NOT NULL
            AND reviewer_key_digest IS NOT NULL)
    )
);

CREATE TABLE migration_import_plans (
    run_id uuid PRIMARY KEY REFERENCES migration_import_runs(run_id),
    plan_id uuid NOT NULL UNIQUE,
    plan_digest bytea NOT NULL UNIQUE CHECK (octet_length(plan_digest) = 32),
    batch_count integer NOT NULL CHECK (batch_count >= 1),
    operation_count integer NOT NULL CHECK (operation_count >= 1),
    source_native_watermark bigint NOT NULL CHECK (source_native_watermark >= 0),
    export_native_watermark bigint NOT NULL CHECK (export_native_watermark >= 0),
    recorded_at timestamptz NOT NULL
);

CREATE TABLE migration_import_plan_batches (
    run_id uuid NOT NULL REFERENCES migration_import_plans(run_id),
    batch_index integer NOT NULL CHECK (batch_index >= 0),
    batch_digest bytea NOT NULL CHECK (octet_length(batch_digest) = 32),
    request_digest bytea NOT NULL CHECK (octet_length(request_digest) = 32),
    operation_count integer NOT NULL CHECK (operation_count BETWEEN 1 AND 64),
    batch_body jsonb NOT NULL CHECK (jsonb_typeof(batch_body) = 'object'),
    PRIMARY KEY (run_id, batch_index),
    UNIQUE (run_id, batch_digest)
);

CREATE TABLE migration_import_replay_receipts (
    run_id uuid NOT NULL REFERENCES migration_import_plans(run_id),
    batch_index integer NOT NULL,
    batch_digest bytea NOT NULL CHECK (octet_length(batch_digest) = 32),
    request_digest bytea NOT NULL CHECK (octet_length(request_digest) = 32),
    operation_count integer NOT NULL CHECK (operation_count BETWEEN 1 AND 64),
    new_domain_facts integer NOT NULL CHECK (new_domain_facts = 0),
    new_events integer NOT NULL CHECK (new_events = 0),
    new_outbox_rows integer NOT NULL CHECK (new_outbox_rows = 0),
    record_position_delta bigint NOT NULL CHECK (record_position_delta = 0),
    projection_semantic_delta bigint NOT NULL CHECK (projection_semantic_delta = 0),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, batch_index),
    FOREIGN KEY (run_id, batch_index)
        REFERENCES migration_import_plan_batches(run_id, batch_index)
);

CREATE TABLE migration_fence_registries (
    run_id uuid PRIMARY KEY REFERENCES migration_import_runs(run_id),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    cutover_id uuid NOT NULL,
    project_key text NOT NULL CHECK (project_key = 'ctower'),
    registry_id uuid NOT NULL,
    registry_revision integer NOT NULL CHECK (registry_revision >= 1),
    registry_digest bytea NOT NULL CHECK (octet_length(registry_digest) = 32),
    source_selection_digest bytea NOT NULL
        CHECK (octet_length(source_selection_digest) = 32),
    UNIQUE (tenant_id, cutover_id, project_key, registry_id, registry_revision),
    UNIQUE (tenant_id, registry_digest),
    FOREIGN KEY (run_id, tenant_id, cutover_id, project_key)
        REFERENCES migration_import_runs(run_id, tenant_id, cutover_id, project_key)
);

CREATE TABLE migration_fence_observer_bindings (
    run_id uuid PRIMARY KEY REFERENCES migration_fence_registries(run_id),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    cutover_id uuid NOT NULL,
    project_key text NOT NULL CHECK (project_key = 'ctower'),
    registry_id uuid NOT NULL,
    registry_revision integer NOT NULL CHECK (registry_revision >= 1),
    registry_digest bytea NOT NULL CHECK (octet_length(registry_digest) = 32),
    principal_id uuid NOT NULL,
    credential_digest bytea NOT NULL UNIQUE CHECK (octet_length(credential_digest) = 32),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL CHECK (expires_at > created_at),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, cutover_id, project_key, registry_id, registry_revision)
        REFERENCES migration_fence_registries(
            tenant_id, cutover_id, project_key, registry_id, registry_revision
        )
);

DO $$
DECLARE
    relation_name text;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'migration_verified_artifacts', 'migration_import_plans',
        'migration_import_plan_batches', 'migration_import_replay_receipts',
        'migration_fence_registries', 'migration_fence_observer_bindings'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER %I_immutable BEFORE UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation()',
            relation_name, relation_name
        );
    END LOOP;
END
$$;

REVOKE ALL ON migration_verified_artifacts, migration_import_plans,
    migration_import_plan_batches, migration_import_replay_receipts,
    migration_fence_registries, migration_fence_observer_bindings
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON migration_verified_artifacts, migration_import_plans,
    migration_import_plan_batches, migration_import_replay_receipts,
    migration_fence_registries, migration_fence_observer_bindings TO ctower_svc;
GRANT SELECT ON migration_import_plans, migration_import_replay_receipts,
    migration_fence_registries, migration_fence_observer_bindings TO ctower_projection;
