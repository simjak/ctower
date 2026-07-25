ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event'
    )
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN (
            'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
            'inbound_thread', 'inbound_event'
        )
    );

CREATE TABLE inbound_threads (
    thread_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9._-]{2,127}$'),
    version integer NOT NULL CHECK (version >= 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (created_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (thread_id, tenant_id)
);

CREATE TABLE inbound_events (
    inbound_event_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    thread_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 1),
    source_kind text NOT NULL CHECK (length(source_kind) BETWEEN 1 AND 64),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 65536),
    content_digest bytea NOT NULL CHECK (octet_length(content_digest) = 32),
    taint text NOT NULL CHECK (
        taint IN ('authenticated', 'external_untrusted', 'quarantine_required')
    ),
    initial_intent text NOT NULL CHECK (
        initial_intent IN ('discussion', 'create_ticket', 'link_ticket')
    ),
    initial_outcome text NOT NULL CHECK (
        initial_outcome IN ('discussion', 'ticket_created', 'ticket_linked', 'quarantined')
    ),
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (thread_id, tenant_id) REFERENCES inbound_threads(thread_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (inbound_event_id, tenant_id),
    UNIQUE (thread_id, position)
);

CREATE TABLE inbound_source_aliases (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    source_kind text NOT NULL CHECK (length(source_kind) BETWEEN 1 AND 64),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    inbound_event_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9._-]{2,127}$'),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, source_kind, source_ref),
    FOREIGN KEY (inbound_event_id, tenant_id)
        REFERENCES inbound_events(inbound_event_id, tenant_id),
    FOREIGN KEY (thread_id, tenant_id) REFERENCES inbound_threads(thread_id, tenant_id),
    UNIQUE (inbound_event_id)
);

CREATE TABLE intake_ticket_projects (
    ticket_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9._-]{2,127}$'),
    inbound_event_id uuid NOT NULL UNIQUE,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (inbound_event_id, tenant_id)
        REFERENCES inbound_events(inbound_event_id, tenant_id),
    UNIQUE (ticket_id, tenant_id)
);

CREATE TABLE inbound_ticket_links (
    inbound_event_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    thread_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    link_kind text NOT NULL CHECK (
        link_kind IN ('initial_create', 'initial_link', 'promotion_create', 'promotion_link')
    ),
    command_id uuid NOT NULL,
    linked_by uuid NOT NULL,
    linked_at timestamptz NOT NULL,
    FOREIGN KEY (inbound_event_id, tenant_id)
        REFERENCES inbound_events(inbound_event_id, tenant_id),
    FOREIGN KEY (thread_id, tenant_id) REFERENCES inbound_threads(thread_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (linked_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE inbound_quarantines (
    inbound_event_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (inbound_event_id, tenant_id)
        REFERENCES inbound_events(inbound_event_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE INDEX inbound_events_thread_order
    ON inbound_events (tenant_id, thread_id, position);
CREATE INDEX inbound_ticket_links_ticket
    ON inbound_ticket_links (tenant_id, ticket_id, inbound_event_id);

REVOKE ALL ON inbound_threads, inbound_events, inbound_source_aliases,
    intake_ticket_projects, inbound_ticket_links, inbound_quarantines
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON inbound_threads, inbound_events, inbound_source_aliases,
    intake_ticket_projects, inbound_ticket_links, inbound_quarantines TO ctower_svc;
REVOKE UPDATE ON inbound_threads FROM ctower_svc;
GRANT UPDATE (version) ON inbound_threads TO ctower_svc;
