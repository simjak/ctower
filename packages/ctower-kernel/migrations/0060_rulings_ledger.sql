-- gh#401: the Agreements ledger. One existing project seat appends one dated,
-- byte-preserved Ruling fact. A correction is a new fact that names the old
-- fact; UPDATE and DELETE are refused at the database boundary.
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'runtime.dream_dispatch_consumed',
    'runtime.dream_lane_bound', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'ruling.recorded'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling'
    )
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN (
            'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
            'inbound_thread', 'inbound_event', 'access', 'session',
            'attention_finding', 'attention_finding_disposition', 'inbox_thread',
            'knowledge_document', 'request', 'ruling'
        )
    );

CREATE TABLE rulings (
    ruling_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    verbatim_bytes bytea NOT NULL
        CHECK (octet_length(verbatim_bytes) BETWEEN 1 AND 65536),
    verbatim_sha256 bytea NOT NULL CHECK (octet_length(verbatim_sha256) = 32),
    recorded_by uuid NOT NULL,
    seat_key text NOT NULL CHECK (seat_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    recorded_at timestamptz NOT NULL,
    command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    supersedes_ruling_id uuid,
    UNIQUE (ruling_id, tenant_id, project_key),
    UNIQUE (tenant_id, recorded_by, command_id),
    UNIQUE (supersedes_ruling_id),
    FOREIGN KEY (recorded_by, tenant_id)
        REFERENCES project_seats(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (supersedes_ruling_id, tenant_id, project_key)
        REFERENCES rulings(ruling_id, tenant_id, project_key),
    CHECK (supersedes_ruling_id IS NULL OR supersedes_ruling_id <> ruling_id)
);
CREATE INDEX rulings_project_date_id
    ON rulings (tenant_id, project_key, recorded_at DESC, ruling_id DESC);

CREATE TRIGGER rulings_immutable
    BEFORE UPDATE OR DELETE ON rulings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON rulings FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON rulings TO ctower_svc;
GRANT SELECT ON rulings TO ctower_projection;
