ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed'
));

CREATE TABLE ticket_work_sessions (
    session_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    ticket_id uuid NOT NULL,
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    seat_key text NOT NULL CHECK (seat_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    crew_name text NOT NULL CHECK (crew_name ~ '^[a-z][a-z0-9._-]{1,95}$'),
    model_ref text NOT NULL CHECK (char_length(model_ref) BETWEEN 1 AND 128),
    harness_ref text NOT NULL CHECK (char_length(harness_ref) BETWEEN 1 AND 64),
    worktree_ref text NOT NULL CHECK (char_length(worktree_ref) BETWEEN 1 AND 256),
    branch_ref text NOT NULL CHECK (char_length(branch_ref) BETWEEN 1 AND 256),
    started_by uuid NOT NULL,
    started_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id, project_key)
        REFERENCES tickets(ticket_id, tenant_id, project_key),
    FOREIGN KEY (started_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (event_id),
    UNIQUE (session_id, tenant_id)
);

CREATE TABLE ticket_work_session_transitions (
    session_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    transition_number integer NOT NULL CHECK (transition_number >= 1),
    from_state text NOT NULL
        CHECK (from_state IN ('dispatched', 'briefed', 'working', 'gated')),
    to_state text NOT NULL
        CHECK (to_state IN ('dispatched', 'briefed', 'working', 'gated')),
    reason text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 500),
    occurred_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    PRIMARY KEY (session_id, transition_number),
    FOREIGN KEY (session_id, tenant_id)
        REFERENCES ticket_work_sessions(session_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (event_id)
);

CREATE TABLE ticket_work_session_closures (
    session_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    outcome text NOT NULL
        CHECK (outcome IN ('delivered', 'blocked', 'abandoned', 'failed')),
    duration_seconds integer NOT NULL
        CHECK (duration_seconds BETWEEN 0 AND 31536000),
    input_tokens bigint NOT NULL CHECK (input_tokens BETWEEN 0 AND 1000000000),
    output_tokens bigint NOT NULL CHECK (output_tokens BETWEEN 0 AND 1000000000),
    evidence_ref text CHECK (char_length(evidence_ref) BETWEEN 1 AND 256),
    closed_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    FOREIGN KEY (session_id, tenant_id)
        REFERENCES ticket_work_sessions(session_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (event_id)
);

CREATE INDEX ticket_work_sessions_ticket
    ON ticket_work_sessions (tenant_id, ticket_id, started_at, session_id);
CREATE INDEX ticket_work_sessions_project
    ON ticket_work_sessions (tenant_id, project_key, started_at, session_id);

CREATE TRIGGER ticket_work_sessions_immutable
    BEFORE UPDATE OR DELETE ON ticket_work_sessions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER ticket_work_session_transitions_immutable
    BEFORE UPDATE OR DELETE ON ticket_work_session_transitions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER ticket_work_session_closures_immutable
    BEFORE UPDATE OR DELETE ON ticket_work_session_closures
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON ticket_work_sessions, ticket_work_session_transitions,
    ticket_work_session_closures
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON ticket_work_sessions, ticket_work_session_transitions,
    ticket_work_session_closures
    TO ctower_svc;
GRANT SELECT ON ticket_work_sessions, ticket_work_session_transitions,
    ticket_work_session_closures
    TO ctower_projection;
