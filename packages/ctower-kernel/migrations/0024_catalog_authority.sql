CREATE FUNCTION refuse_immutable_catalog_fact_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'catalog fact is immutable' USING ERRCODE = '55000';
END
$$;

CREATE TABLE catalog_components (
    component_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    kind text NOT NULL CHECK (kind IN (
        'workflow', 'execution_policy', 'gate_policy', 'evidence_policy',
        'goal', 'project', 'agent_profile', 'persona', 'skill', 'tool',
        'capability', 'environment', 'image', 'harness', 'supervisor',
        'target', 'workspace', 'telemetry', 'placement_policy', 'extension',
        'cadence_policy', 'notification', 'integration', 'adapter'
    )),
    component_key text NOT NULL CHECK (
        component_key ~ '^[a-z][a-z0-9.-]{2,127}$'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (tenant_id, kind, component_key),
    UNIQUE (component_id, tenant_id)
);

CREATE TABLE catalog_component_revisions (
    component_revision_id uuid PRIMARY KEY,
    component_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    revision_number integer NOT NULL CHECK (revision_number >= 1),
    content_digest bytea NOT NULL CHECK (octet_length(content_digest) = 32),
    schema_ref text NOT NULL CHECK (
        schema_ref ~ '^ctower\.[a-z][a-z0-9.-]*/v[1-9][0-9]*$'
    ),
    scope_project text CHECK (
        scope_project IS NULL OR length(scope_project) BETWEEN 1 AND 128
    ),
    compatibility_ctower text NOT NULL CHECK (
        length(compatibility_ctower) BETWEEN 1 AND 128
    ),
    payload_ref text NOT NULL CHECK (
        payload_ref ~ '^object:sha256:[0-9a-f]{64}$'
    ),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (component_id, tenant_id)
        REFERENCES catalog_components(component_id, tenant_id),
    FOREIGN KEY (created_by, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (component_id, revision_number),
    UNIQUE (component_id, content_digest),
    UNIQUE (component_revision_id, tenant_id)
);

CREATE TABLE catalog_payload_receipts (
    component_revision_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    object_key text NOT NULL CHECK (length(object_key) BETWEEN 1 AND 512),
    object_version text NOT NULL CHECK (length(object_version) BETWEEN 1 AND 256),
    ciphertext_sha256 bytea NOT NULL CHECK (octet_length(ciphertext_sha256) = 32),
    key_reference text NOT NULL CHECK (
        key_reference ~ '^[a-z][a-z0-9._:/-]{2,255}$'
    ),
    key_version text NOT NULL CHECK (
        key_version ~ '^[A-Za-z0-9._:-]{1,128}$'
    ),
    wrapped_key_sha256 bytea NOT NULL CHECK (octet_length(wrapped_key_sha256) = 32),
    uploaded_at timestamptz NOT NULL,
    verified_at timestamptz NOT NULL CHECK (verified_at >= uploaded_at),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    UNIQUE (tenant_id, artifact_digest, object_key, object_version)
);

CREATE TABLE catalog_component_dependencies (
    component_revision_id uuid NOT NULL,
    required_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    PRIMARY KEY (component_revision_id, required_revision_id),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (required_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    CHECK (component_revision_id <> required_revision_id)
);

CREATE TABLE catalog_component_provenance (
    component_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    provenance_kind text NOT NULL CHECK (length(provenance_kind) BETWEEN 1 AND 64),
    source text NOT NULL CHECK (length(source) BETWEEN 1 AND 512),
    source_digest bytea NOT NULL CHECK (octet_length(source_digest) = 32),
    PRIMARY KEY (component_revision_id, ordinal),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id)
);

CREATE TABLE catalog_component_lifecycle_facts (
    lifecycle_fact_id uuid PRIMARY KEY,
    component_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    action text NOT NULL CHECK (action IN ('published', 'deprecated', 'revoked')),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (component_revision_id, action),
    UNIQUE (event_id)
);

CREATE TABLE catalog_component_supersessions (
    replacement_revision_id uuid PRIMARY KEY,
    superseded_revision_id uuid NOT NULL UNIQUE,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (replacement_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (superseded_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    CHECK (replacement_revision_id <> superseded_revision_id)
);

CREATE TABLE company_bundle_revisions (
    bundle_revision_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    active_version integer NOT NULL CHECK (active_version >= 1),
    bundle_digest bytea NOT NULL CHECK (octet_length(bundle_digest) = 32),
    plan_digest bytea NOT NULL CHECK (octet_length(plan_digest) = 32),
    company_key text NOT NULL CHECK (company_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    company_display_name text NOT NULL CHECK (
        length(company_display_name) BETWEEN 1 AND 128
    ),
    previous_bundle_revision_id uuid,
    activation_event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    activated_at timestamptz NOT NULL,
    FOREIGN KEY (previous_bundle_revision_id, tenant_id)
        REFERENCES company_bundle_revisions(bundle_revision_id, tenant_id),
    FOREIGN KEY (activation_event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, actor_principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    UNIQUE (tenant_id, active_version),
    UNIQUE (activation_event_id),
    UNIQUE (bundle_revision_id, tenant_id),
    UNIQUE (bundle_revision_id, tenant_id, active_version, bundle_digest)
);

CREATE TABLE company_bundle_members (
    bundle_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    component_revision_id uuid NOT NULL,
    publication_event_id uuid NOT NULL,
    PRIMARY KEY (bundle_revision_id, ordinal),
    FOREIGN KEY (bundle_revision_id, tenant_id)
        REFERENCES company_bundle_revisions(bundle_revision_id, tenant_id),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (publication_event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    UNIQUE (bundle_revision_id, component_revision_id)
);

CREATE TABLE company_bundle_assignments (
    bundle_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    subject text NOT NULL CHECK (
        subject ~ '^[a-z][a-z0-9._-]*:[a-z][a-z0-9._-]*$'
    ),
    slot text NOT NULL CHECK (slot ~ '^[a-z][a-z0-9._-]{1,63}$'),
    component_revision_id uuid NOT NULL,
    PRIMARY KEY (bundle_revision_id, subject, slot),
    FOREIGN KEY (bundle_revision_id, tenant_id)
        REFERENCES company_bundle_revisions(bundle_revision_id, tenant_id),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id)
);

CREATE TABLE company_bundle_secret_refs (
    bundle_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    binding_name text NOT NULL CHECK (binding_name ~ '^[A-Z][A-Z0-9_]{2,127}$'),
    reference_class text NOT NULL CHECK (
        reference_class IN ('os-credential', 'vault-path', 'runtime-binding')
    ),
    PRIMARY KEY (bundle_revision_id, binding_name),
    FOREIGN KEY (bundle_revision_id, tenant_id)
        REFERENCES company_bundle_revisions(bundle_revision_id, tenant_id)
);

CREATE TABLE company_bundle_checks (
    bundle_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    check_code text NOT NULL CHECK (check_code ~ '^[a-z][a-z0-9._-]{1,95}$'),
    status text NOT NULL CHECK (status IN ('passed', 'warning')),
    PRIMARY KEY (bundle_revision_id, check_code),
    FOREIGN KEY (bundle_revision_id, tenant_id)
        REFERENCES company_bundle_revisions(bundle_revision_id, tenant_id)
);

CREATE TABLE company_bundle_active (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id),
    bundle_revision_id uuid NOT NULL,
    active_version integer NOT NULL CHECK (active_version >= 1),
    bundle_digest bytea NOT NULL CHECK (octet_length(bundle_digest) = 32),
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    updated_at timestamptz NOT NULL,
    FOREIGN KEY (bundle_revision_id, tenant_id, active_version, bundle_digest)
        REFERENCES company_bundle_revisions(
            bundle_revision_id, tenant_id, active_version, bundle_digest
        ),
    FOREIGN KEY (tenant_id, principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id)
);

ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created',
    'ticket.created',
    'ticket.custody_transferred',
    'proof.changed',
    'workflow.changed',
    'work.changed',
    'routine.occurrence_recorded',
    'attention.poison_disposition_recorded',
    'catalog.component_published',
    'catalog.bundle_activated'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN ('ticket', 'work', 'workflow', 'proof', 'catalog')
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN ('ticket', 'work', 'workflow', 'proof', 'catalog')
    );

CREATE INDEX catalog_component_revisions_exact
    ON catalog_component_revisions (tenant_id, component_id, revision_number, content_digest);
CREATE INDEX catalog_component_lifecycle_current
    ON catalog_component_lifecycle_facts (tenant_id, component_revision_id, recorded_at DESC);
CREATE INDEX company_bundle_members_component
    ON company_bundle_members (tenant_id, component_revision_id, bundle_revision_id);

DO $$
DECLARE
    catalog_table text;
BEGIN
    FOREACH catalog_table IN ARRAY ARRAY[
        'catalog_components',
        'catalog_component_revisions',
        'catalog_payload_receipts',
        'catalog_component_dependencies',
        'catalog_component_provenance',
        'catalog_component_lifecycle_facts',
        'catalog_component_supersessions',
        'company_bundle_revisions',
        'company_bundle_members',
        'company_bundle_assignments',
        'company_bundle_secret_refs',
        'company_bundle_checks'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I_immutable BEFORE UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION refuse_immutable_catalog_fact_mutation()',
            catalog_table,
            catalog_table
        );
    END LOOP;
END
$$;

REVOKE ALL ON catalog_components, catalog_component_revisions,
    catalog_payload_receipts, catalog_component_dependencies,
    catalog_component_provenance, catalog_component_lifecycle_facts,
    catalog_component_supersessions, company_bundle_revisions,
    company_bundle_members, company_bundle_assignments,
    company_bundle_secret_refs, company_bundle_checks, company_bundle_active
    FROM PUBLIC, ctower_svc, ctower_projection;

GRANT INSERT, SELECT ON catalog_components, catalog_component_revisions,
    catalog_payload_receipts, catalog_component_dependencies,
    catalog_component_provenance, catalog_component_lifecycle_facts,
    catalog_component_supersessions, company_bundle_revisions,
    company_bundle_members, company_bundle_assignments,
    company_bundle_secret_refs, company_bundle_checks TO ctower_svc;
GRANT INSERT, SELECT ON company_bundle_active TO ctower_svc;
GRANT UPDATE (
    bundle_revision_id, active_version, bundle_digest,
    principal_id, client_command_id, updated_at
) ON company_bundle_active TO ctower_svc;
