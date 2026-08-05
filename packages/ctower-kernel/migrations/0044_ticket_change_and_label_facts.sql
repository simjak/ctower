-- INV-66/AC-TM-07: Change references and applied labels are append-only
-- ticket-scoped facts. Change references have no vocabulary (recorded
-- exactly as linked); applied labels pin the label-vocabulary revision
-- active at application time, per D29(b) clause 3.
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied'
));

CREATE TABLE ticket_change_references (
    change_reference_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    ticket_id uuid NOT NULL,
    repository text NOT NULL CHECK (length(repository) BETWEEN 1 AND 256),
    change_identity text NOT NULL CHECK (length(change_identity) BETWEEN 1 AND 128),
    reference text NOT NULL CHECK (length(reference) BETWEEN 1 AND 256),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, ticket_id, repository, change_identity),
    UNIQUE (event_id)
);

CREATE TABLE ticket_applied_labels (
    ticket_label_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    ticket_id uuid NOT NULL,
    label_key text NOT NULL CHECK (label_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    label_vocabulary_revision_id uuid NOT NULL,
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (label_vocabulary_revision_id, tenant_id, label_key)
        REFERENCES label_vocabulary_members(label_vocabulary_revision_id, tenant_id, label_key),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, ticket_id, label_key),
    UNIQUE (event_id)
);

CREATE TRIGGER ticket_change_references_immutable
    BEFORE UPDATE OR DELETE ON ticket_change_references
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER ticket_applied_labels_immutable
    BEFORE UPDATE OR DELETE ON ticket_applied_labels
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON ticket_change_references, ticket_applied_labels
    FROM PUBLIC, ctower_svc, ctower_projection;

GRANT INSERT, SELECT ON ticket_change_references, ticket_applied_labels TO ctower_svc;
GRANT SELECT ON ticket_change_references, ticket_applied_labels TO ctower_projection;
