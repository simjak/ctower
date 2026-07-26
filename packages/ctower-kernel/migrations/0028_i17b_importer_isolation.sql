ALTER TABLE principals DROP CONSTRAINT principals_kind_check;
ALTER TABLE principals ADD CONSTRAINT principals_kind_check CHECK (kind IN (
    'bootstrap_installer', 'operator', 'commander', 'agent', 'reviewer', 'runner',
    'control_worker', 'migration_importer', 'fence_observer'
));

ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed'
));
ALTER TABLE events DROP CONSTRAINT events_origin_check;
ALTER TABLE events ADD CONSTRAINT events_origin_check CHECK (
    origin IN ('api', 'bootstrap', 'control_worker', 'migration_importer')
);
ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN ('ticket', 'work', 'workflow', 'proof', 'catalog', 'migration')
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN ('ticket', 'work', 'workflow', 'proof', 'catalog', 'migration')
    );

CREATE TABLE migration_import_runs (
    run_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    cutover_id uuid NOT NULL,
    tenant_key text NOT NULL CHECK (tenant_key = 'ctower'),
    project_key text NOT NULL CHECK (project_key = 'ctower'),
    source_selection_digest bytea NOT NULL CHECK (octet_length(source_selection_digest) = 32),
    build_digest bytea NOT NULL CHECK (octet_length(build_digest) = 32),
    client_digest bytea NOT NULL CHECK (octet_length(client_digest) = 32),
    schema_digest bytea NOT NULL CHECK (octet_length(schema_digest) = 32),
    operation_registry_digest bytea NOT NULL CHECK (octet_length(operation_registry_digest) = 32),
    reviewer_public_key_digest bytea NOT NULL
        CHECK (octet_length(reviewer_public_key_digest) = 32),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (created_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, cutover_id),
    UNIQUE (run_id, tenant_id, cutover_id, project_key)
);

CREATE TABLE migration_importer_bindings (
    run_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    cutover_id uuid NOT NULL,
    project_key text NOT NULL CHECK (project_key = 'ctower'),
    principal_id uuid NOT NULL,
    credential_digest bytea NOT NULL UNIQUE CHECK (octet_length(credential_digest) = 32),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL CHECK (expires_at > created_at),
    FOREIGN KEY (run_id, tenant_id, cutover_id, project_key)
        REFERENCES migration_import_runs(run_id, tenant_id, cutover_id, project_key),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (principal_id),
    UNIQUE (run_id, principal_id)
);

CREATE TABLE migration_importer_credential_facts (
    credential_fact_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    fact_sequence integer NOT NULL CHECK (fact_sequence >= 1),
    lifecycle text NOT NULL CHECK (lifecycle IN ('activated', 'revoked')),
    actor_principal_id uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, principal_id)
        REFERENCES migration_importer_bindings(run_id, principal_id),
    FOREIGN KEY (actor_principal_id) REFERENCES principals(principal_id),
    UNIQUE (run_id, fact_sequence),
    UNIQUE (run_id, lifecycle)
);

CREATE TABLE migration_import_run_facts (
    run_fact_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    fact_sequence integer NOT NULL CHECK (fact_sequence >= 1),
    state text NOT NULL CHECK (state IN (
        'created', 'export_equality_bound', 'alias_plan_bound', 'importing',
        'pass_one_complete', 'pass_two_noop', 'reconciled'
    )),
    export_equality_digest bytea CHECK (octet_length(export_equality_digest) = 32),
    alias_map_digest bytea CHECK (octet_length(alias_map_digest) = 32),
    semantic_digest bytea NOT NULL CHECK (octet_length(semantic_digest) = 32),
    record_watermark bigint NOT NULL CHECK (record_watermark >= 0),
    projection_watermark bigint NOT NULL CHECK (projection_watermark >= 0),
    event_id uuid NOT NULL REFERENCES events(event_id),
    actor_principal_id uuid NOT NULL REFERENCES principals(principal_id),
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    UNIQUE (run_id, fact_sequence),
    UNIQUE (event_id),
    UNIQUE (actor_principal_id, command_id)
);

CREATE TABLE migration_import_batches (
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    batch_index integer NOT NULL CHECK (batch_index >= 0),
    batch_digest bytea NOT NULL CHECK (octet_length(batch_digest) = 32),
    request_digest bytea NOT NULL CHECK (octet_length(request_digest) = 32),
    operation_count integer NOT NULL CHECK (operation_count BETWEEN 1 AND 64),
    response_body jsonb NOT NULL CHECK (jsonb_typeof(response_body) = 'object'),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, batch_index),
    UNIQUE (run_id, batch_digest)
);

CREATE TABLE migration_import_operation_results (
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    command_id uuid NOT NULL,
    namespace text NOT NULL CHECK (length(namespace) BETWEEN 1 AND 128),
    immutable_source_id text NOT NULL CHECK (length(immutable_source_id) BETWEEN 1 AND 512),
    source_version_or_digest text NOT NULL
        CHECK (length(source_version_or_digest) BETWEEN 1 AND 256),
    operation_kind text NOT NULL CHECK (operation_kind IN (
        'ticket_seed', 'exact_alias', 'ticket_relation', 'source_link'
    )),
    planned_target_ref text NOT NULL CHECK (length(planned_target_ref) BETWEEN 1 AND 256),
    request_digest bytea NOT NULL CHECK (octet_length(request_digest) = 32),
    target_id text NOT NULL CHECK (length(target_id) BETWEEN 1 AND 256),
    event_ids uuid[] NOT NULL CHECK (cardinality(event_ids) >= 1),
    record_position bigint NOT NULL CHECK (record_position >= 1),
    response_body jsonb NOT NULL CHECK (jsonb_typeof(response_body) = 'object'),
    occurred_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, command_id),
    UNIQUE (
        run_id, namespace, immutable_source_id, source_version_or_digest,
        operation_kind, planned_target_ref
    )
);

CREATE TABLE ticket_project_bindings (
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    project_key text NOT NULL CHECK (project_key = 'ctower'),
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    source_namespace text NOT NULL CHECK (length(source_namespace) BETWEEN 1 AND 128),
    immutable_source_id text NOT NULL CHECK (length(immutable_source_id) BETWEEN 1 AND 512),
    bound_at timestamptz NOT NULL,
    PRIMARY KEY (ticket_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    UNIQUE (run_id, source_namespace, immutable_source_id)
);

CREATE TABLE migration_alias_revisions (
    alias_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision >= 1),
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    namespace text NOT NULL CHECK (length(namespace) BETWEEN 1 AND 128),
    immutable_source_id text NOT NULL CHECK (length(immutable_source_id) BETWEEN 1 AND 512),
    target_ticket_id uuid NOT NULL REFERENCES tickets(ticket_id),
    disposition text NOT NULL CHECK (disposition IN (
        'alias_linked_existing', 'exact_duplicate', 'provenance_only'
    )),
    semantic_digest bytea NOT NULL CHECK (octet_length(semantic_digest) = 32),
    supersedes_revision integer,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (alias_id, revision),
    UNIQUE (run_id, namespace, immutable_source_id, revision),
    CHECK (
        (revision = 1 AND supersedes_revision IS NULL)
        OR (revision > 1 AND supersedes_revision = revision - 1)
    )
);

CREATE TABLE migration_source_link_revisions (
    link_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision >= 1),
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    namespace text NOT NULL CHECK (length(namespace) BETWEEN 1 AND 128),
    immutable_source_id text NOT NULL CHECK (length(immutable_source_id) BETWEEN 1 AND 512),
    link_class text NOT NULL CHECK (link_class IN (
        'decision', 'external_effect', 'artifact_not_proof', 'provenance',
        'excluded_out_of_scope'
    )),
    target_kind text NOT NULL CHECK (target_kind IN (
        'ticket', 'ticket_relation', 'checkpoint', 'decision', 'artifact', 'external_effect'
    )),
    target_id text NOT NULL CHECK (length(target_id) BETWEEN 1 AND 256),
    reason_code text NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9._-]{2,95}$'),
    semantic_digest bytea NOT NULL CHECK (octet_length(semantic_digest) = 32),
    supersedes_revision integer,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (link_id, revision),
    CHECK (
        (revision = 1 AND supersedes_revision IS NULL)
        OR (revision > 1 AND supersedes_revision = revision - 1)
    )
);

CREATE TABLE migration_relation_validity_facts (
    relation_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision >= 1),
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    active boolean NOT NULL,
    replacement_relation_id uuid,
    semantic_digest bytea NOT NULL CHECK (octet_length(semantic_digest) = 32),
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (relation_id, revision),
    CHECK (active OR replacement_relation_id IS DISTINCT FROM relation_id)
);

CREATE TABLE migration_corrections (
    correction_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES migration_import_runs(run_id),
    correction_kind text NOT NULL CHECK (correction_kind IN ('alias', 'source_link', 'relation')),
    object_id uuid NOT NULL,
    superseded_revision integer NOT NULL CHECK (superseded_revision >= 1),
    expected_current_digest bytea NOT NULL CHECK (octet_length(expected_current_digest) = 32),
    replacement jsonb NOT NULL CHECK (jsonb_typeof(replacement) = 'object'),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 1000),
    reviewer_id uuid NOT NULL REFERENCES principals(principal_id),
    command_id uuid NOT NULL,
    event_id uuid NOT NULL REFERENCES events(event_id),
    semantic_digest bytea NOT NULL CHECK (octet_length(semantic_digest) = 32),
    recorded_at timestamptz NOT NULL,
    UNIQUE (run_id, correction_kind, object_id, superseded_revision),
    UNIQUE (event_id)
);

CREATE TABLE migration_reconciliation_facts (
    reconciliation_id uuid PRIMARY KEY,
    run_id uuid NOT NULL UNIQUE REFERENCES migration_import_runs(run_id),
    report_digest bytea NOT NULL CHECK (octet_length(report_digest) = 32),
    target_semantic_digest bytea NOT NULL CHECK (octet_length(target_semantic_digest) = 32),
    report_body jsonb NOT NULL CHECK (jsonb_typeof(report_body) = 'object'),
    event_id uuid NOT NULL UNIQUE REFERENCES events(event_id),
    actor_principal_id uuid NOT NULL REFERENCES principals(principal_id),
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL
);

CREATE TABLE migration_fence_observations (
    observation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    registry_id uuid NOT NULL,
    registry_revision integer NOT NULL CHECK (registry_revision >= 1),
    sequence integer NOT NULL CHECK (sequence >= 1),
    observation_digest bytea NOT NULL UNIQUE CHECK (octet_length(observation_digest) = 32),
    previous_observation_digest bytea CHECK (octet_length(previous_observation_digest) = 32),
    status text NOT NULL CHECK (status IN ('clear', 'detected', 'unknown')),
    disables_writes boolean NOT NULL,
    observation_body jsonb NOT NULL CHECK (jsonb_typeof(observation_body) = 'object'),
    actor_principal_id uuid NOT NULL,
    command_id uuid NOT NULL,
    event_id uuid NOT NULL UNIQUE REFERENCES events(event_id),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, registry_id, registry_revision, sequence),
    CHECK (
        (sequence = 1 AND previous_observation_digest IS NULL)
        OR (sequence > 1 AND previous_observation_digest IS NOT NULL)
    )
);

CREATE FUNCTION guard_migration_importer_event() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    actor_kind text;
    binding migration_importer_bindings%ROWTYPE;
    current_lifecycle text;
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
    IF binding.run_id IS NULL OR current_lifecycle <> 'activated'
        OR binding.expires_at <= NEW.server_time THEN
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
CREATE TRIGGER events_migration_importer_guard
    BEFORE INSERT ON events FOR EACH ROW EXECUTE FUNCTION guard_migration_importer_event();

DO $$
DECLARE
    relation_name text;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'migration_import_runs', 'migration_importer_bindings',
        'migration_importer_credential_facts', 'migration_import_run_facts',
        'migration_import_batches', 'migration_import_operation_results',
        'ticket_project_bindings', 'migration_alias_revisions',
        'migration_source_link_revisions', 'migration_relation_validity_facts',
        'migration_corrections', 'migration_reconciliation_facts',
        'migration_fence_observations'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER %I_immutable BEFORE UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation()',
            relation_name, relation_name
        );
    END LOOP;
END
$$;

REVOKE ALL ON migration_import_runs, migration_importer_bindings,
    migration_importer_credential_facts, migration_import_run_facts,
    migration_import_batches, migration_import_operation_results,
    ticket_project_bindings, migration_alias_revisions,
    migration_source_link_revisions, migration_relation_validity_facts,
    migration_corrections, migration_reconciliation_facts,
    migration_fence_observations FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON migration_import_runs, migration_importer_bindings,
    migration_importer_credential_facts, migration_import_run_facts,
    migration_import_batches, migration_import_operation_results,
    ticket_project_bindings, migration_alias_revisions,
    migration_source_link_revisions, migration_relation_validity_facts,
    migration_corrections, migration_reconciliation_facts,
    migration_fence_observations TO ctower_svc;
