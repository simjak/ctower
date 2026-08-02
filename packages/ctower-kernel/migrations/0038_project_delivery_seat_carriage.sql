ALTER TABLE catalog_components DROP CONSTRAINT catalog_components_kind_check;
ALTER TABLE catalog_components ADD CONSTRAINT catalog_components_kind_check CHECK (kind IN (
    'workflow', 'execution_policy', 'gate_policy', 'evidence_policy',
    'goal', 'project', 'agent_profile', 'persona', 'skill', 'tool',
    'capability', 'environment', 'image', 'harness', 'supervisor',
    'target', 'workspace', 'telemetry', 'placement_policy', 'extension',
    'cadence_policy', 'notification', 'integration', 'adapter', 'checkpoint',
    'seat_catalog'
));

CREATE TABLE project_delivery_seat_catalog_revisions (
    seat_catalog_revision_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    catalog_key text NOT NULL CHECK (catalog_key ~ '^[a-z][a-z0-9.-]{2,127}$'),
    catalog_revision integer NOT NULL CHECK (catalog_revision >= 1),
    catalog_digest bytea NOT NULL CHECK (octet_length(catalog_digest) = 32),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (seat_catalog_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, catalog_key, catalog_revision),
    UNIQUE (tenant_id, catalog_key, catalog_digest),
    UNIQUE (seat_catalog_revision_id, tenant_id),
    UNIQUE (event_id)
);

CREATE TABLE project_delivery_seat_catalog_members (
    seat_catalog_revision_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    seat_key text NOT NULL CHECK (seat_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    seat_label text NOT NULL CHECK (length(seat_label) BETWEEN 1 AND 128),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    PRIMARY KEY (seat_catalog_revision_id, seat_key),
    FOREIGN KEY (seat_catalog_revision_id, tenant_id)
        REFERENCES project_delivery_seat_catalog_revisions(
            seat_catalog_revision_id, tenant_id
        ),
    UNIQUE (seat_catalog_revision_id, tenant_id, seat_key),
    UNIQUE (seat_catalog_revision_id, ordinal)
);

ALTER TABLE project_delivery_exit_criteria
    ADD COLUMN assigned_seat_catalog_revision_id uuid,
    ADD COLUMN assigned_seat_key text CHECK (
        assigned_seat_key IS NULL
        OR assigned_seat_key ~ '^[a-z][a-z0-9._-]{1,95}$'
    ),
    ADD CONSTRAINT project_delivery_exit_criteria_assigned_seat_complete CHECK (
        (assigned_seat_catalog_revision_id IS NULL AND assigned_seat_key IS NULL)
        OR
        (assigned_seat_catalog_revision_id IS NOT NULL AND assigned_seat_key IS NOT NULL)
    ),
    ADD CONSTRAINT project_delivery_exit_criteria_assigned_seat_member_fkey
        FOREIGN KEY (assigned_seat_catalog_revision_id, tenant_id, assigned_seat_key)
        REFERENCES project_delivery_seat_catalog_members(
            seat_catalog_revision_id, tenant_id, seat_key
        );

CREATE TABLE assignment_interval_seat_facts (
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    assignment_kind text NOT NULL,
    interval_sequence integer NOT NULL CHECK (interval_sequence >= 1),
    seat_catalog_revision_id uuid NOT NULL,
    seat_key text NOT NULL CHECK (seat_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (ticket_id, assignment_kind, interval_sequence),
    FOREIGN KEY (ticket_id, assignment_kind, interval_sequence)
        REFERENCES assignment_intervals(ticket_id, assignment_kind, interval_sequence),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (seat_catalog_revision_id, tenant_id, seat_key)
        REFERENCES project_delivery_seat_catalog_members(
            seat_catalog_revision_id, tenant_id, seat_key
        )
);

CREATE TABLE proof_evidence_verifier_assignments (
    evidence_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    assignment_ticket_id uuid NOT NULL,
    assignment_kind text NOT NULL,
    assignment_interval_sequence integer NOT NULL CHECK (
        assignment_interval_sequence >= 1
    ),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (evidence_id, tenant_id)
        REFERENCES proof_evidence(evidence_id, tenant_id),
    FOREIGN KEY (
        assignment_ticket_id, assignment_kind, assignment_interval_sequence
    ) REFERENCES assignment_intervals(ticket_id, assignment_kind, interval_sequence),
    FOREIGN KEY (assignment_ticket_id, tenant_id)
        REFERENCES tickets(ticket_id, tenant_id)
);

CREATE TRIGGER project_delivery_seat_catalog_revisions_immutable
    BEFORE UPDATE OR DELETE ON project_delivery_seat_catalog_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER project_delivery_seat_catalog_members_immutable
    BEFORE UPDATE OR DELETE ON project_delivery_seat_catalog_members
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER assignment_interval_seat_facts_immutable
    BEFORE UPDATE OR DELETE ON assignment_interval_seat_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER proof_evidence_verifier_assignments_immutable
    BEFORE UPDATE OR DELETE ON proof_evidence_verifier_assignments
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON project_delivery_seat_catalog_revisions,
    project_delivery_seat_catalog_members,
    assignment_interval_seat_facts,
    proof_evidence_verifier_assignments
    FROM PUBLIC, ctower_svc, ctower_projection;

GRANT INSERT, SELECT ON project_delivery_seat_catalog_revisions,
    project_delivery_seat_catalog_members,
    assignment_interval_seat_facts,
    proof_evidence_verifier_assignments
    TO ctower_svc;
GRANT SELECT ON project_delivery_seat_catalog_revisions,
    project_delivery_seat_catalog_members,
    assignment_interval_seat_facts,
    proof_evidence_verifier_assignments
    TO ctower_projection;
