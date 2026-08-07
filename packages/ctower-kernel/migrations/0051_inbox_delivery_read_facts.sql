-- Append-only recipient delivery/read facts replace mutable projection read cursors.
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
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket'
));

CREATE TABLE inbox_message_delivery_facts (
    event_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    message_id uuid NOT NULL REFERENCES inbox_messages(message_id),
    recipient_id uuid NOT NULL,
    recipient_seat text NOT NULL CHECK (recipient_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    state text NOT NULL CHECK (state IN ('delivered', 'read')),
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (thread_id, tenant_id) REFERENCES inbox_threads(thread_id, tenant_id),
    FOREIGN KEY (recipient_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, message_id, state),
    CHECK (recipient_id = recorded_by)
);

CREATE TRIGGER inbox_message_delivery_facts_immutable
    BEFORE UPDATE OR DELETE ON inbox_message_delivery_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

DROP TABLE inbox_projection_reads;
DROP INDEX inbox_projection_recipient_unread;
ALTER TABLE inbox_projection_messages
    ADD COLUMN delivered_event_id uuid,
    ADD COLUMN delivered_at timestamptz,
    ADD COLUMN read_event_id uuid,
    ADD COLUMN read_at timestamptz,
    ADD CONSTRAINT inbox_projection_delivered_pair CHECK (
        (delivered_event_id IS NULL) = (delivered_at IS NULL)
    ),
    ADD CONSTRAINT inbox_projection_read_pair CHECK (
        (read_event_id IS NULL) = (read_at IS NULL)
    ),
    ADD CONSTRAINT inbox_projection_read_requires_delivery CHECK (
        read_event_id IS NULL OR delivered_event_id IS NOT NULL
    );
CREATE INDEX inbox_projection_recipient_unread
    ON inbox_projection_messages (tenant_id, recipient_id, thread_id, position)
    WHERE read_at IS NULL;

REVOKE ALL ON inbox_message_delivery_facts FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON inbox_message_delivery_facts TO ctower_svc;
