-- Native two-party agent inbox. Record facts are authoritative and append-only;
-- thread version/head and recipient read cursors are the only mutable state.
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'thread.promoted_to_ticket'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread'
    )
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN (
            'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
            'inbound_thread', 'inbound_event', 'access', 'session',
            'attention_finding', 'attention_finding_disposition', 'inbox_thread'
        )
    );

CREATE TABLE inbox_threads (
    thread_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    participant_a_id uuid NOT NULL,
    participant_a_seat text NOT NULL CHECK (participant_a_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    participant_b_id uuid NOT NULL,
    participant_b_seat text NOT NULL CHECK (participant_b_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    version bigint NOT NULL CHECK (version >= 2),
    last_event_hash bytea NOT NULL CHECK (octet_length(last_event_hash) = 32),
    opened_by uuid NOT NULL,
    opened_at timestamptz NOT NULL,
    CHECK (participant_a_id <> participant_b_id),
    FOREIGN KEY (participant_a_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (participant_b_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (opened_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (thread_id, tenant_id)
);

CREATE TABLE inbox_messages (
    message_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    position bigint NOT NULL CHECK (position >= 1),
    sender_id uuid NOT NULL,
    sender_seat text NOT NULL CHECK (sender_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    recipient_id uuid NOT NULL,
    recipient_seat text NOT NULL CHECK (recipient_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 65536),
    event_id uuid NOT NULL,
    sent_at timestamptz NOT NULL,
    CHECK (sender_id <> recipient_id),
    FOREIGN KEY (thread_id, tenant_id) REFERENCES inbox_threads(thread_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (sender_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (recipient_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, thread_id, position),
    UNIQUE (event_id)
);

CREATE TABLE inbox_ticket_links (
    thread_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    event_id uuid NOT NULL,
    promoted_by uuid NOT NULL,
    promoted_at timestamptz NOT NULL,
    FOREIGN KEY (thread_id, tenant_id) REFERENCES inbox_threads(thread_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (promoted_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, ticket_id, thread_id),
    UNIQUE (event_id)
);

CREATE TRIGGER inbox_messages_immutable
    BEFORE UPDATE OR DELETE ON inbox_messages
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER inbox_ticket_links_immutable
    BEFORE UPDATE OR DELETE ON inbox_ticket_links
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

CREATE TABLE inbox_projection_threads (
    tenant_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    participant_a_id uuid NOT NULL,
    participant_a_seat text NOT NULL,
    participant_b_id uuid NOT NULL,
    participant_b_seat text NOT NULL,
    promoted_ticket_id uuid,
    last_message_at timestamptz,
    last_message_preview text,
    PRIMARY KEY (tenant_id, thread_id)
);

CREATE TABLE inbox_projection_messages (
    tenant_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    message_id uuid NOT NULL,
    position bigint NOT NULL,
    sender_id uuid NOT NULL,
    sender_seat text NOT NULL,
    recipient_id uuid NOT NULL,
    recipient_seat text NOT NULL,
    content text NOT NULL,
    sent_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, thread_id, position),
    UNIQUE (message_id),
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES inbox_projection_threads(tenant_id, thread_id) ON DELETE CASCADE
);

CREATE TABLE inbox_projection_reads (
    tenant_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    through_position bigint NOT NULL CHECK (through_position >= 1),
    read_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, thread_id, principal_id),
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES inbox_projection_threads(tenant_id, thread_id) ON DELETE CASCADE
);

CREATE INDEX inbox_projection_recipient_unread
    ON inbox_projection_messages (tenant_id, recipient_id, thread_id, position);
CREATE INDEX inbox_ticket_links_ticket
    ON inbox_ticket_links (tenant_id, ticket_id, thread_id);

REVOKE ALL ON inbox_threads, inbox_messages, inbox_ticket_links,
    inbox_projection_threads, inbox_projection_messages, inbox_projection_reads
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON inbox_threads TO ctower_svc;
GRANT UPDATE (version, last_event_hash) ON inbox_threads TO ctower_svc;
GRANT SELECT, INSERT ON inbox_messages, inbox_ticket_links TO ctower_svc;
GRANT SELECT ON inbox_ticket_links TO ctower_projection;
GRANT SELECT, INSERT, UPDATE, DELETE ON inbox_projection_threads,
    inbox_projection_messages, inbox_projection_reads TO ctower_projection;
