-- R2982/R3000 (CT-I1-034): spawn-custody records capture pre-dispatch crew spawn
-- facts (who/what/why/where) as append-only facts. Lifecycle moves are POSTed
-- transition facts, never in-place mutation: spawn_records carries NO status
-- column; the effective lifecycle state derives from the latest transition
-- (COALESCE over spawn_record_transitions, initial state 'requested'), exactly
-- like ticket_work_sessions/ticket_work_session_transitions.
-- CT-I1-031 workspace_id is OPTIONAL (null until workspaces build lands).

ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'routine.retired',
    'runtime.dream_dispatch_consumed', 'runtime.dream_lane_bound',
    'attention.poison_disposition_recorded', 'catalog.component_published',
    'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'ruling.recorded', 'request.proposal_changed', 'spawn.recorded',
    'spawn.transitioned'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling', 'request_proposal',
        'spawn_record'
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
            'knowledge_document', 'request', 'ruling', 'request_proposal',
            'spawn_record'
        )
    );

CREATE TABLE spawn_records (
    spawn_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    seat_key text NOT NULL CHECK (length(seat_key) BETWEEN 1 AND 255),
    crew_name text NOT NULL CHECK (length(crew_name) BETWEEN 1 AND 255),
    task_file_ref text NOT NULL CHECK (length(task_file_ref) BETWEEN 1 AND 1024),
    worktree_path text NOT NULL CHECK (length(worktree_path) BETWEEN 1 AND 1024),
    harness text NOT NULL CHECK (length(harness) BETWEEN 1 AND 64),
    model text NOT NULL CHECK (length(model) BETWEEN 1 AND 128),
    effort text CHECK (effort IS NULL OR length(effort) BETWEEN 1 AND 64),
    workspace_id uuid,
    principal_id uuid NOT NULL,
    command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (spawn_id, tenant_id),
    UNIQUE (tenant_id, principal_id, command_id),
    FOREIGN KEY (principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE spawn_record_transitions (
    transition_id uuid PRIMARY KEY,
    spawn_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    transition_number bigint NOT NULL,
    to_status text NOT NULL CHECK (to_status IN (
        'accepted', 'running', 'completed', 'failed', 'reaped'
    )),
    reason text CHECK (reason IS NULL OR length(reason) BETWEEN 1 AND 4096),
    principal_id uuid NOT NULL,
    command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    transitioned_at timestamptz NOT NULL,
    UNIQUE (spawn_id, tenant_id, transition_number),
    UNIQUE (tenant_id, principal_id, command_id),
    FOREIGN KEY (spawn_id, tenant_id)
        REFERENCES spawn_records(spawn_id, tenant_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX idx_spawn_records_tenant_project
    ON spawn_records (tenant_id, project_key, created_at DESC);
CREATE INDEX idx_spawn_record_transitions_spawn
    ON spawn_record_transitions (tenant_id, spawn_id, transition_number DESC);

CREATE TRIGGER spawn_records_immutable
    BEFORE UPDATE OR DELETE ON spawn_records
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER spawn_record_transitions_immutable
    BEFORE UPDATE OR DELETE ON spawn_record_transitions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON spawn_records, spawn_record_transitions
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON spawn_records, spawn_record_transitions TO ctower_svc;
GRANT SELECT ON spawn_records, spawn_record_transitions TO ctower_projection;
