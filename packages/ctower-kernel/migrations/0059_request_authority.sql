-- gh#400: first-class Request authority. Requests are independent from Tickets;
-- one atomic command records transport provenance, the Request, its initial facts,
-- the exact command result, audit event, and outbox intent.
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
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread', 'request'
    )
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN (
            'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
            'inbound_thread', 'inbound_event', 'access', 'session',
            'attention_finding', 'attention_finding_disposition', 'inbox_thread', 'request'
        )
    );

ALTER TABLE inbound_events DROP CONSTRAINT inbound_events_initial_intent_check;
ALTER TABLE inbound_events ADD CONSTRAINT inbound_events_initial_intent_check CHECK (
    initial_intent IN ('discussion', 'create_ticket', 'link_ticket', 'create_request')
);
ALTER TABLE inbound_events DROP CONSTRAINT inbound_events_initial_outcome_check;
ALTER TABLE inbound_events ADD CONSTRAINT inbound_events_initial_outcome_check CHECK (
    initial_outcome IN (
        'discussion', 'ticket_created', 'ticket_linked', 'quarantined', 'request_created'
    )
);

CREATE TABLE request_number_allocators (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id),
    last_number bigint NOT NULL CHECK (last_number >= 0),
    advanced_at timestamptz NOT NULL
);

CREATE TABLE requests (
    request_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    request_number bigint NOT NULL CHECK (request_number > 0),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 65536),
    content_digest bytea NOT NULL CHECK (octet_length(content_digest) = 32),
    source_kind text NOT NULL CHECK (length(source_kind) BETWEEN 1 AND 64),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    inbound_event_id uuid NOT NULL,
    submitted_by uuid NOT NULL,
    capture_command_id uuid NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (inbound_event_id, tenant_id)
        REFERENCES inbound_events(inbound_event_id, tenant_id),
    FOREIGN KEY (submitted_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (request_id, tenant_id),
    UNIQUE (tenant_id, request_number),
    UNIQUE (tenant_id, source_kind, source_ref),
    UNIQUE (inbound_event_id),
    UNIQUE (tenant_id, submitted_by, capture_command_id)
);

CREATE TABLE request_owner_facts (
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    owner_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, sequence),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (owner_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_priority_facts (
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    priority text NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    is_default boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, sequence),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_triage_facts (
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    disposition text NOT NULL CHECK (
        disposition IN ('UNTRIAGED', 'ACCEPTED', 'DUPLICATE', 'REJECTED')
    ),
    reason text,
    canonical_request_id uuid,
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, sequence),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (canonical_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    CHECK (
        (disposition IN ('UNTRIAGED', 'ACCEPTED') AND reason IS NULL
            AND canonical_request_id IS NULL)
        OR (disposition = 'REJECTED' AND length(reason) BETWEEN 1 AND 500
            AND canonical_request_id IS NULL)
        OR (disposition = 'DUPLICATE' AND length(reason) BETWEEN 1 AND 500
            AND canonical_request_id IS NOT NULL AND canonical_request_id <> request_id)
    )
);

CREATE TABLE request_ticket_relation_facts (
    relation_fact_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('required', 'optional')),
    active boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);
CREATE INDEX request_ticket_relation_latest
    ON request_ticket_relation_facts (tenant_id, request_id, ticket_id, recorded_at DESC);

CREATE TABLE request_blocker_facts (
    blocker_fact_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    blocker_key text NOT NULL CHECK (length(blocker_key) BETWEEN 1 AND 256),
    active boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);
CREATE INDEX request_blocker_latest
    ON request_blocker_facts (tenant_id, request_id, blocker_key, recorded_at DESC);

CREATE TABLE request_closure_evaluations (
    evaluation_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    request_version integer NOT NULL CHECK (request_version >= 1),
    outcome text NOT NULL CHECK (outcome IN ('open', 'done')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    dependency_digest bytea NOT NULL CHECK (octet_length(dependency_digest) = 32),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_attention_facts (
    attention_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    kind text NOT NULL CHECK (
        kind IN ('request_triage_required', 'request_execution_link_required',
                 'request_import_attention')
    ),
    active boolean NOT NULL,
    owner_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (owner_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_import_manifests (
    manifest_digest bytea PRIMARY KEY CHECK (octet_length(manifest_digest) = 32),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    archive_ref text NOT NULL CHECK (length(archive_ref) BETWEEN 1 AND 512),
    ledger_digest bytea NOT NULL CHECK (octet_length(ledger_digest) = 32),
    row_digest bytea NOT NULL CHECK (octet_length(row_digest) = 32),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    maximum_request_number bigint NOT NULL CHECK (maximum_request_number >= 0),
    project_counts jsonb NOT NULL CHECK (jsonb_typeof(project_counts) = 'object'),
    owner_mapping_digest bytea NOT NULL CHECK (octet_length(owner_mapping_digest) = 32),
    observed_file_size bigint NOT NULL CHECK (observed_file_size >= 0),
    sealed_at timestamptz NOT NULL,
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE INDEX requests_project_number ON requests (tenant_id, project_key, request_number);

CREATE TRIGGER request_owner_facts_immutable
    BEFORE UPDATE OR DELETE ON request_owner_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_priority_facts_immutable
    BEFORE UPDATE OR DELETE ON request_priority_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_triage_facts_immutable
    BEFORE UPDATE OR DELETE ON request_triage_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_ticket_relation_facts_immutable
    BEFORE UPDATE OR DELETE ON request_ticket_relation_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_blocker_facts_immutable
    BEFORE UPDATE OR DELETE ON request_blocker_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_closure_evaluations_immutable
    BEFORE UPDATE OR DELETE ON request_closure_evaluations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_attention_facts_immutable
    BEFORE UPDATE OR DELETE ON request_attention_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_import_manifests_immutable
    BEFORE UPDATE OR DELETE ON request_import_manifests
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON request_number_allocators, requests, request_owner_facts,
    request_priority_facts, request_triage_facts, request_ticket_relation_facts,
    request_blocker_facts, request_closure_evaluations, request_attention_facts,
    request_import_manifests FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON request_number_allocators, requests, request_owner_facts,
    request_priority_facts, request_triage_facts, request_ticket_relation_facts,
    request_blocker_facts, request_closure_evaluations, request_attention_facts,
    request_import_manifests TO ctower_svc;
GRANT UPDATE (last_number, advanced_at) ON request_number_allocators TO ctower_svc;
GRANT UPDATE (version) ON requests TO ctower_svc;
GRANT SELECT ON requests, request_owner_facts, request_priority_facts,
    request_triage_facts, request_ticket_relation_facts, request_blocker_facts,
    request_closure_evaluations, request_attention_facts, request_import_manifests
    TO ctower_projection;
