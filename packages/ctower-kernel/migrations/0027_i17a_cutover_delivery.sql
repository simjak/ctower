ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created',
    'ticket.created',
    'ticket.custody_transferred',
    'ticket.comment_added',
    'proof.changed',
    'workflow.changed',
    'work.changed',
    'routine.occurrence_recorded',
    'attention.poison_disposition_recorded',
    'catalog.component_published',
    'catalog.bundle_activated'
));

CREATE TABLE ctower_project_cutover_facts (
    cutover_fact_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    cutover_id uuid NOT NULL,
    fact_sequence integer NOT NULL CHECK (fact_sequence >= 1),
    phase text NOT NULL CHECK (phase IN (
        'prepared', 'development_epoch_committed', 'disaster_safe_active'
    )),
    authority_mode text NOT NULL CHECK (authority_mode IN (
        'legacy_writable', 'development_single_writer', 'disaster_safe'
    )),
    writes_enabled boolean NOT NULL,
    durability_claim text NOT NULL CHECK (durability_claim IN (
        'CP3_D_NOT_PROVEN', 'CP3_D_PROVEN'
    )),
    recovery_claim text NOT NULL CHECK (recovery_claim IN (
        'EXTERNAL_FAILURE_DOMAIN_UNPROVEN', 'EXTERNAL_FAILURE_DOMAIN_PROVEN'
    )),
    data_class text NOT NULL CHECK (data_class IN (
        'RECONSTRUCTIBLE_ONLY', 'DISASTER_SAFE_CTOWER_ENGINEERING'
    )),
    legacy_writer_fence text NOT NULL CHECK (legacy_writer_fence IN (
        'not_armed', 'enforced', 'unknown'
    )),
    split_brain text NOT NULL CHECK (split_brain IN (
        'clear', 'detected', 'unknown'
    )),
    source_watermark bigint NOT NULL CHECK (source_watermark >= 0),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, cutover_id, fact_sequence),
    UNIQUE (event_id),
    CHECK (
        (phase = 'prepared' AND authority_mode = 'legacy_writable')
        OR (phase = 'development_epoch_committed'
            AND authority_mode = 'development_single_writer')
        OR (phase = 'disaster_safe_active' AND authority_mode = 'disaster_safe')
    ),
    CHECK (
        (authority_mode = 'disaster_safe'
            AND durability_claim = 'CP3_D_PROVEN'
            AND recovery_claim = 'EXTERNAL_FAILURE_DOMAIN_PROVEN'
            AND data_class = 'DISASTER_SAFE_CTOWER_ENGINEERING')
        OR
        (authority_mode <> 'disaster_safe'
            AND durability_claim = 'CP3_D_NOT_PROVEN'
            AND recovery_claim = 'EXTERNAL_FAILURE_DOMAIN_UNPROVEN'
            AND data_class = 'RECONSTRUCTIBLE_ONLY')
    ),
    CHECK (
        NOT writes_enabled
        OR (
            legacy_writer_fence = 'enforced'
            AND split_brain = 'clear'
            AND authority_mode <> 'legacy_writable'
        )
    )
);

CREATE TABLE project_delivery_checkpoint_definitions (
    checkpoint_definition_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    company_key text NOT NULL CHECK (company_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    checkpoint_key text NOT NULL CHECK (checkpoint_key ~ '^I[12]\.[0-9]+$'),
    definition_revision integer NOT NULL CHECK (definition_revision >= 1),
    ordered_position integer NOT NULL CHECK (ordered_position >= 1),
    checkpoint_label text NOT NULL CHECK (length(checkpoint_label) BETWEEN 1 AND 160),
    outcome text NOT NULL CHECK (length(outcome) BETWEEN 1 AND 500),
    accountable_owner text NOT NULL CHECK (length(accountable_owner) BETWEEN 1 AND 128),
    applicable_states text[] NOT NULL CHECK (
        cardinality(applicable_states) BETWEEN 2 AND 8
        AND 'planned' = ANY(applicable_states)
        AND 'done' = ANY(applicable_states)
        AND applicable_states <@ ARRAY[
            'planned', 'in_progress', 'ready_to_land', 'merged',
            'verified', 'released', 'blocked', 'done'
        ]::text[]
    ),
    catalog_revision text NOT NULL CHECK (length(catalog_revision) BETWEEN 1 AND 256),
    catalog_digest bytea NOT NULL CHECK (octet_length(catalog_digest) = 32),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, project_key, checkpoint_key, definition_revision),
    UNIQUE (tenant_id, project_key, ordered_position, definition_revision),
    UNIQUE (event_id),
    UNIQUE (checkpoint_definition_id, tenant_id)
);

CREATE TABLE project_delivery_exit_criteria (
    checkpoint_definition_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    criterion_key text NOT NULL CHECK (criterion_key ~ '^[a-z][a-z0-9._-]*$'),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    description text NOT NULL CHECK (length(description) BETWEEN 1 AND 500),
    proof_ticket_id uuid,
    proof_criterion_key text CHECK (
        proof_criterion_key IS NULL OR proof_criterion_key ~ '^[a-z][a-z0-9._-]*$'
    ),
    source_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
    PRIMARY KEY (checkpoint_definition_id, criterion_key),
    FOREIGN KEY (checkpoint_definition_id, tenant_id)
        REFERENCES project_delivery_checkpoint_definitions(
            checkpoint_definition_id, tenant_id
        ),
    FOREIGN KEY (proof_ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    UNIQUE (checkpoint_definition_id, ordinal),
    CHECK (
        (proof_ticket_id IS NULL AND proof_criterion_key IS NULL)
        OR (proof_ticket_id IS NOT NULL AND proof_criterion_key IS NOT NULL)
    )
);

CREATE TABLE project_delivery_projection_rows (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    checkpoint_key text NOT NULL CHECK (checkpoint_key ~ '^I[12]\.[0-9]+$'),
    row_payload jsonb NOT NULL CHECK (jsonb_typeof(row_payload) = 'object'),
    source_watermark bigint NOT NULL CHECK (source_watermark >= 0),
    projection_watermark bigint NOT NULL CHECK (projection_watermark >= 0),
    reconciled_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, project_key, checkpoint_key)
);

CREATE TRIGGER ctower_project_cutover_facts_immutable
    BEFORE UPDATE OR DELETE ON ctower_project_cutover_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER project_delivery_checkpoint_definitions_immutable
    BEFORE UPDATE OR DELETE ON project_delivery_checkpoint_definitions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER project_delivery_exit_criteria_immutable
    BEFORE UPDATE OR DELETE ON project_delivery_exit_criteria
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON ctower_project_cutover_facts,
    project_delivery_checkpoint_definitions,
    project_delivery_exit_criteria,
    project_delivery_projection_rows
    FROM PUBLIC, ctower_svc, ctower_projection;

-- I1.7A has no production writer. ctower_svc may read cutover facts but must not
-- INSERT them: arming an epoch authority fact (writes_enabled, development
-- phase) is the I1.7B/C point of no return and is deferred to that independent
-- review. Checkpoint definitions and exit criteria remain INSERTable by the
-- future I1.7B importer; cutover facts do not.
GRANT SELECT ON ctower_project_cutover_facts TO ctower_svc;
GRANT INSERT, SELECT ON project_delivery_checkpoint_definitions,
    project_delivery_exit_criteria
    TO ctower_svc;
GRANT SELECT ON ctower_project_cutover_facts,
    project_delivery_checkpoint_definitions,
    project_delivery_exit_criteria
    TO ctower_projection;
GRANT SELECT ON project_delivery_projection_rows TO ctower_svc;
GRANT INSERT, UPDATE, DELETE, SELECT ON project_delivery_projection_rows
    TO ctower_projection;
