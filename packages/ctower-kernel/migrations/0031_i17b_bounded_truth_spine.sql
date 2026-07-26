ALTER TABLE migration_import_runs
    ADD COLUMN reviewer_key_ref text,
    ADD COLUMN reviewer_key_version integer CHECK (reviewer_key_version >= 1);

ALTER TABLE migration_import_runs
    ADD CONSTRAINT migration_import_runs_reviewer_tuple_check CHECK (
        (reviewer_key_ref IS NULL AND reviewer_key_version IS NULL)
        OR (reviewer_key_ref IS NOT NULL AND reviewer_key_version IS NOT NULL)
    );

ALTER TABLE migration_import_run_facts
    DROP CONSTRAINT migration_import_run_facts_state_check;
ALTER TABLE migration_import_run_facts
    ADD CONSTRAINT migration_import_run_facts_state_check CHECK (state IN (
        'created', 'export_equality_bound', 'alias_plan_bound', 'importing',
        'pass_one_complete', 'pass_two_started', 'pass_two_noop', 'reconciled'
    ));

ALTER TABLE migration_verified_artifacts
    DROP CONSTRAINT migration_verified_artifacts_artifact_kind_check;
ALTER TABLE migration_verified_artifacts
    ADD CONSTRAINT migration_verified_artifacts_artifact_kind_check CHECK (
        artifact_kind IN (
            'source_selection', 'export_a', 'export_b', 'export_equality',
            'alias_map', 'import_plan', 'fence_registry', 'reconciliation'
        )
    ),
    ADD COLUMN artifact_canonical_bytes bytea;

ALTER TABLE migration_fence_registries
    ADD COLUMN source_pointer_digest bytea
        CHECK (source_pointer_digest IS NULL OR octet_length(source_pointer_digest) = 32),
    ADD COLUMN source_pointer_device bigint CHECK (source_pointer_device >= 0),
    ADD COLUMN source_pointer_inode bigint CHECK (source_pointer_inode >= 1),
    ADD COLUMN source_pointer_offset bigint CHECK (source_pointer_offset >= 0),
    ADD COLUMN source_pointer_scoped_digest bytea
        CHECK (
            source_pointer_scoped_digest IS NULL
            OR octet_length(source_pointer_scoped_digest) = 32
        ),
    ADD COLUMN monitor_interval_seconds integer CHECK (monitor_interval_seconds >= 1),
    ADD COLUMN max_observation_age_seconds integer CHECK (max_observation_age_seconds >= 1),
    ADD COLUMN max_future_clock_skew_seconds integer
        CHECK (max_future_clock_skew_seconds >= 0);

CREATE TABLE migration_import_pass_two_snapshots (
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    boundary text NOT NULL CHECK (boundary IN ('start', 'end')),
    snapshot_digest bytea NOT NULL CHECK (octet_length(snapshot_digest) = 32),
    snapshot_body jsonb NOT NULL CHECK (jsonb_typeof(snapshot_body) = 'object'),
    domain_fact_count bigint NOT NULL CHECK (domain_fact_count >= 0),
    event_count bigint NOT NULL CHECK (event_count >= 0),
    outbox_count bigint NOT NULL CHECK (outbox_count >= 0),
    record_position bigint NOT NULL CHECK (record_position >= 0),
    project_delivery_digest bytea NOT NULL
        CHECK (octet_length(project_delivery_digest) = 32),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, boundary)
);

CREATE TABLE migration_stable_alias_bindings (
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    stable_item_id text NOT NULL CHECK (stable_item_id ~ '^CT-[A-Z0-9-]+$'),
    target_ticket_id uuid NOT NULL,
    mapping_digest bytea NOT NULL CHECK (octet_length(mapping_digest) = 32),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, stable_item_id),
    FOREIGN KEY (target_ticket_id) REFERENCES tickets(ticket_id)
);

CREATE TRIGGER migration_import_pass_two_snapshots_immutable
    BEFORE UPDATE OR DELETE ON migration_import_pass_two_snapshots
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER migration_stable_alias_bindings_immutable
    BEFORE UPDATE OR DELETE ON migration_stable_alias_bindings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

ALTER TABLE migration_reconciliation_facts
    ADD COLUMN report_canonical_bytes bytea,
    ADD COLUMN pass_two_start_digest bytea
        CHECK (pass_two_start_digest IS NULL OR octet_length(pass_two_start_digest) = 32),
    ADD COLUMN pass_two_end_digest bytea
        CHECK (pass_two_end_digest IS NULL OR octet_length(pass_two_end_digest) = 32);

CREATE OR REPLACE FUNCTION guard_migration_importer_event() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    actor_kind text;
    binding migration_importer_bindings%ROWTYPE;
    current_lifecycle text;
    canonical_credential_active boolean;
BEGIN
    SELECT kind INTO actor_kind FROM principals
    WHERE principal_id = NEW.actor_principal_id AND tenant_id = NEW.tenant_id;
    IF actor_kind <> 'migration_importer' THEN
        IF NEW.origin = 'migration_importer' THEN
            RAISE EXCEPTION 'migration importer origin requires its principal'
                USING ERRCODE = '42501';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.origin <> 'migration_importer'
        OR NEW.kind NOT IN ('ticket.created', 'work.changed', 'migration.changed') THEN
        RAISE EXCEPTION 'migration importer event capability denied'
            USING ERRCODE = '42501';
    END IF;
    SELECT * INTO binding FROM migration_importer_bindings
    WHERE principal_id = NEW.actor_principal_id AND tenant_id = NEW.tenant_id;
    SELECT fact.lifecycle INTO current_lifecycle
    FROM migration_importer_credential_facts AS fact
    WHERE fact.run_id = binding.run_id ORDER BY fact.fact_sequence DESC LIMIT 1;
    SELECT EXISTS (
        SELECT 1
        FROM principal_credentials AS credential
        WHERE credential.principal_id = binding.principal_id
          AND credential.tenant_id = binding.tenant_id
          AND credential.credential_digest = binding.credential_digest
          AND credential.revoked_at IS NULL
    ) INTO canonical_credential_active;
    IF binding.run_id IS NULL OR current_lifecycle <> 'activated'
        OR binding.expires_at <= NEW.server_time
        OR NOT coalesce(canonical_credential_active, false) THEN
        RAISE EXCEPTION 'migration importer binding unavailable'
            USING ERRCODE = '42501';
    END IF;
    IF NEW.kind = 'migration.changed' AND (
        NEW.payload ->> 'run_id' <> binding.run_id::text
        OR NEW.payload ->> 'cutover_id' <> binding.cutover_id::text
        OR NEW.payload ->> 'project_key' <> binding.project_key
    ) THEN
        RAISE EXCEPTION 'migration importer event scope denied'
            USING ERRCODE = '42501';
    END IF;
    IF NEW.kind = 'ticket.created' AND NOT EXISTS (
        SELECT 1 FROM ticket_project_bindings AS project
        WHERE project.ticket_id = NEW.aggregate_id
          AND project.tenant_id = NEW.tenant_id
          AND project.project_key = binding.project_key
          AND project.run_id = binding.run_id
    ) THEN
        RAISE EXCEPTION 'migration importer ticket scope denied'
            USING ERRCODE = '42501';
    END IF;
    IF NEW.kind = 'work.changed' AND (
        NEW.payload ->> 'operation' <> 'relation_added'
        OR NOT EXISTS (
            SELECT 1
            FROM ticket_project_bindings AS source
            JOIN ticket_project_bindings AS target
              ON target.ticket_id = (NEW.payload #>> '{data,target_ticket_id}')::uuid
             AND target.run_id = source.run_id
             AND target.tenant_id = source.tenant_id
            WHERE source.ticket_id = NEW.aggregate_id
              AND source.tenant_id = NEW.tenant_id
              AND source.run_id = binding.run_id
        )
    ) THEN
        RAISE EXCEPTION 'migration importer relation scope denied'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$$;

REVOKE ALL ON migration_import_pass_two_snapshots, migration_stable_alias_bindings
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON migration_import_pass_two_snapshots,
    migration_stable_alias_bindings TO ctower_svc;
GRANT SELECT ON migration_import_pass_two_snapshots,
    migration_stable_alias_bindings TO ctower_projection;
