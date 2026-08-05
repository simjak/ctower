-- D29(b)/(c): label vocabulary and attention-kind catalog are configured data
-- of the same class as the seat catalog (project_delivery_seat_catalog_*).
ALTER TABLE catalog_components DROP CONSTRAINT catalog_components_kind_check;
ALTER TABLE catalog_components ADD CONSTRAINT catalog_components_kind_check CHECK (kind IN (
    'workflow', 'execution_policy', 'gate_policy', 'evidence_policy',
    'goal', 'project', 'agent_profile', 'persona', 'skill', 'tool',
    'capability', 'environment', 'image', 'harness', 'supervisor',
    'target', 'workspace', 'telemetry', 'placement_policy', 'extension',
    'cadence_policy', 'notification', 'integration', 'adapter', 'checkpoint',
    'seat_catalog', 'label_vocabulary', 'attention_kind_catalog'
));

CREATE TABLE label_vocabulary_revisions (
    label_vocabulary_revision_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    catalog_key text NOT NULL CHECK (catalog_key ~ '^[a-z][a-z0-9.-]{2,127}$'),
    catalog_revision integer NOT NULL CHECK (catalog_revision >= 1),
    catalog_digest bytea NOT NULL CHECK (octet_length(catalog_digest) = 32),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (label_vocabulary_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, catalog_key, catalog_revision),
    UNIQUE (tenant_id, catalog_key, catalog_digest),
    UNIQUE (label_vocabulary_revision_id, tenant_id),
    UNIQUE (event_id)
);

CREATE TABLE label_vocabulary_members (
    label_vocabulary_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    label_key text NOT NULL CHECK (label_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 128),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    PRIMARY KEY (label_vocabulary_revision_id, label_key),
    FOREIGN KEY (label_vocabulary_revision_id, tenant_id)
        REFERENCES label_vocabulary_revisions(label_vocabulary_revision_id, tenant_id),
    UNIQUE (label_vocabulary_revision_id, tenant_id, label_key),
    UNIQUE (label_vocabulary_revision_id, ordinal)
);

CREATE TABLE attention_kind_catalog_revisions (
    attention_kind_catalog_revision_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    catalog_key text NOT NULL CHECK (catalog_key ~ '^[a-z][a-z0-9.-]{2,127}$'),
    catalog_revision integer NOT NULL CHECK (catalog_revision >= 1),
    catalog_digest bytea NOT NULL CHECK (octet_length(catalog_digest) = 32),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (attention_kind_catalog_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, catalog_key, catalog_revision),
    UNIQUE (tenant_id, catalog_key, catalog_digest),
    UNIQUE (attention_kind_catalog_revision_id, tenant_id),
    UNIQUE (event_id)
);

CREATE TABLE attention_kind_catalog_members (
    attention_kind_catalog_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    kind_key text NOT NULL CHECK (kind_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 128),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    PRIMARY KEY (attention_kind_catalog_revision_id, kind_key),
    FOREIGN KEY (attention_kind_catalog_revision_id, tenant_id)
        REFERENCES attention_kind_catalog_revisions(attention_kind_catalog_revision_id, tenant_id),
    UNIQUE (attention_kind_catalog_revision_id, tenant_id, kind_key),
    UNIQUE (attention_kind_catalog_revision_id, ordinal)
);

CREATE TRIGGER label_vocabulary_revisions_immutable
    BEFORE UPDATE OR DELETE ON label_vocabulary_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER label_vocabulary_members_immutable
    BEFORE UPDATE OR DELETE ON label_vocabulary_members
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER attention_kind_catalog_revisions_immutable
    BEFORE UPDATE OR DELETE ON attention_kind_catalog_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER attention_kind_catalog_members_immutable
    BEFORE UPDATE OR DELETE ON attention_kind_catalog_members
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON label_vocabulary_revisions, label_vocabulary_members,
    attention_kind_catalog_revisions, attention_kind_catalog_members
    FROM PUBLIC, ctower_svc, ctower_projection;

GRANT INSERT, SELECT ON label_vocabulary_revisions, label_vocabulary_members,
    attention_kind_catalog_revisions, attention_kind_catalog_members
    TO ctower_svc;
GRANT SELECT ON label_vocabulary_revisions, label_vocabulary_members,
    attention_kind_catalog_revisions, attention_kind_catalog_members
    TO ctower_projection;
