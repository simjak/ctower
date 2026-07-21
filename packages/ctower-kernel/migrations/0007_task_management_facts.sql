ALTER TABLE principals DROP CONSTRAINT principals_kind_check;
ALTER TABLE principals ADD CONSTRAINT principals_kind_check CHECK (kind IN (
    'bootstrap_installer', 'operator', 'commander', 'agent', 'reviewer', 'runner'
));

ALTER TABLE tickets ADD COLUMN current_episode integer NOT NULL DEFAULT 1
    CHECK (current_episode >= 1);

ALTER TABLE lifecycle_episodes
    DROP CONSTRAINT lifecycle_episodes_episode_number_check,
    DROP CONSTRAINT lifecycle_episodes_state_check;
ALTER TABLE lifecycle_episodes
    ADD CONSTRAINT lifecycle_episodes_episode_number_check CHECK (episode_number >= 1),
    ADD CONSTRAINT lifecycle_episodes_state_check CHECK (
        state IN ('open', 'active', 'waiting', 'resolved', 'closed', 'cancelled')
    ),
    ADD COLUMN closed_at timestamptz;

ALTER TABLE priority_facts DROP CONSTRAINT priority_facts_fact_sequence_check;
ALTER TABLE priority_facts
    ADD COLUMN episode_number integer NOT NULL DEFAULT 1 CHECK (episode_number >= 1),
    ADD COLUMN operation text NOT NULL DEFAULT 'initial'
        CHECK (operation IN ('initial', 'change')),
    ADD COLUMN previous_priority text,
    ADD COLUMN authority text NOT NULL DEFAULT 'ticket-create'
        CHECK (authority IN ('ticket-create', 'commander', 'operator', 'reopen-policy')),
    ADD COLUMN policy_ref text NOT NULL DEFAULT 'ctower.priority-authority@1'
        CHECK (policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    ADD COLUMN urgent_evidence_ref text
        CHECK (urgent_evidence_ref IS NULL OR length(urgent_evidence_ref) BETWEEN 1 AND 256),
    ADD CONSTRAINT priority_facts_fact_sequence_check CHECK (fact_sequence >= 1),
    ADD CONSTRAINT priority_facts_previous_check CHECK (
        (operation = 'initial' AND previous_priority IS NULL)
        OR (operation = 'change' AND previous_priority IN ('P0', 'P1', 'P2'))
    );

ALTER TABLE assignment_intervals
    DROP CONSTRAINT assignment_intervals_assignment_kind_check;
ALTER TABLE assignment_intervals
    ADD CONSTRAINT assignment_intervals_assignment_kind_check CHECK (assignment_kind IN (
        'ticket_custodian', 'current_assignee', 'stage_owner',
        'reviewer_assignment', 'runner_lease_owner'
    )),
    ADD COLUMN scope_ref text CHECK (scope_ref IS NULL OR length(scope_ref) BETWEEN 1 AND 256);

CREATE UNIQUE INDEX one_current_scoped_assignment
    ON assignment_intervals (ticket_id, assignment_kind, COALESCE(scope_ref, ''))
    WHERE released_at IS NULL;
CREATE UNIQUE INDEX one_current_assignee
    ON assignment_intervals (ticket_id)
    WHERE assignment_kind = 'current_assignee' AND released_at IS NULL;

CREATE FUNCTION enforce_assignment_interval_no_overlap() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM assignment_intervals AS existing
        WHERE existing.ticket_id = NEW.ticket_id
          AND existing.assignment_kind = NEW.assignment_kind
          AND existing.scope_ref IS NOT DISTINCT FROM NEW.scope_ref
          AND existing.interval_sequence <> NEW.interval_sequence
          AND tstzrange(existing.assigned_at, existing.released_at, '[)')
              && tstzrange(NEW.assigned_at, NEW.released_at, '[)')
    ) THEN
        RAISE EXCEPTION 'assignment intervals overlap' USING ERRCODE = '23P01';
    END IF;
    RETURN NEW;
END
$$;
CREATE CONSTRAINT TRIGGER assignment_intervals_no_overlap
    AFTER INSERT OR UPDATE OF assigned_at, released_at ON assignment_intervals
    DEFERRABLE INITIALLY IMMEDIATE
    FOR EACH ROW EXECUTE FUNCTION enforce_assignment_interval_no_overlap();

ALTER TABLE lifecycle_facts
    DROP CONSTRAINT lifecycle_facts_fact_sequence_check,
    DROP CONSTRAINT lifecycle_facts_state_check,
    DROP CONSTRAINT lifecycle_facts_ticket_id_fact_sequence_key,
    DROP CONSTRAINT lifecycle_facts_ticket_id_state_key;
ALTER TABLE lifecycle_facts
    ADD COLUMN episode_number integer NOT NULL DEFAULT 1 CHECK (episode_number >= 1),
    ADD COLUMN reason text NOT NULL DEFAULT 'legacy lifecycle transition'
        CHECK (length(reason) BETWEEN 1 AND 500),
    ADD CONSTRAINT lifecycle_facts_fact_sequence_check CHECK (fact_sequence >= 1),
    ADD CONSTRAINT lifecycle_facts_state_check CHECK (
        state IN ('open', 'active', 'waiting', 'resolved', 'closed', 'cancelled', 'reopened')
    ),
    ADD CONSTRAINT lifecycle_facts_episode_sequence_unique
        UNIQUE (ticket_id, episode_number, fact_sequence);

CREATE TABLE admission_facts (
    admission_fact_id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    episode_number integer NOT NULL CHECK (episode_number >= 1),
    fact_sequence integer NOT NULL CHECK (fact_sequence >= 1),
    admitted boolean NOT NULL,
    review_after timestamptz,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (ticket_id, episode_number, fact_sequence)
);

CREATE TABLE blocker_heads (
    blocker_id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    blocker_kind text NOT NULL CHECK (blocker_kind IN (
        'dependency', 'operator_action', 'policy', 'resource', 'technical'
    )),
    reason_class text NOT NULL CHECK (length(reason_class) BETWEEN 1 AND 64),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    owner_principal_id uuid NOT NULL,
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    affected_stage text CHECK (
        affected_stage IS NULL OR affected_stage ~ '^[a-z][a-z0-9._-]*$'
    ),
    resolution_condition text NOT NULL CHECK (length(resolution_condition) BETWEEN 1 AND 500),
    next_check_at timestamptz,
    dependency_ref text CHECK (dependency_ref IS NULL OR length(dependency_ref) <= 256),
    board_impact boolean NOT NULL,
    opened_at timestamptz NOT NULL,
    resolved_at timestamptz,
    resolution_evidence_ref text,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (owner_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (blocker_id, tenant_id),
    CHECK (
        (resolved_at IS NULL AND resolution_evidence_ref IS NULL)
        OR (resolved_at IS NOT NULL AND length(resolution_evidence_ref) BETWEEN 1 AND 256)
    )
);

CREATE TABLE blocker_facts (
    blocker_fact_id uuid PRIMARY KEY,
    blocker_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    fact_sequence integer NOT NULL CHECK (fact_sequence >= 1),
    operation text NOT NULL CHECK (operation IN ('opened', 'resolved')),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    resolution_evidence_ref text,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (blocker_id, tenant_id) REFERENCES blocker_heads(blocker_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (blocker_id, fact_sequence)
);

CREATE TABLE ticket_relations (
    relation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    source_ticket_id uuid NOT NULL,
    target_ticket_id uuid NOT NULL,
    relation_kind text NOT NULL CHECK (relation_kind IN (
        'parent_of', 'depends_on', 'blocks', 'duplicates', 'relates_to', 'caused_by'
    )),
    actor_principal_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (source_ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (target_ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, source_ticket_id, target_ticket_id, relation_kind),
    CHECK (source_ticket_id <> target_ticket_id)
);
CREATE INDEX ticket_relations_target
    ON ticket_relations (tenant_id, target_ticket_id, relation_kind);

ALTER TABLE workflow_runs
    DROP CONSTRAINT workflow_runs_ticket_id_tenant_id_key;
ALTER TABLE workflow_runs
    ADD COLUMN episode_number integer NOT NULL DEFAULT 1 CHECK (episode_number >= 1),
    ADD COLUMN workflow_digest bytea NOT NULL DEFAULT decode(repeat('00', 32), 'hex')
        CHECK (octet_length(workflow_digest) = 32),
    ADD COLUMN execution_policy_ref text NOT NULL DEFAULT 'legacy.execution@1'
        CHECK (execution_policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    ADD COLUMN execution_policy_digest bytea NOT NULL DEFAULT decode(repeat('00', 32), 'hex')
        CHECK (octet_length(execution_policy_digest) = 32),
    ADD COLUMN gate_policy_ref text NOT NULL DEFAULT 'legacy.gates@1'
        CHECK (gate_policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    ADD COLUMN gate_policy_digest bytea NOT NULL DEFAULT decode(repeat('00', 32), 'hex')
        CHECK (octet_length(gate_policy_digest) = 32),
    ADD COLUMN evidence_policy_ref text NOT NULL DEFAULT 'legacy.evidence@1'
        CHECK (evidence_policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    ADD COLUMN evidence_policy_digest bytea NOT NULL DEFAULT decode(repeat('00', 32), 'hex')
        CHECK (octet_length(evidence_policy_digest) = 32),
    ADD COLUMN started_by uuid,
    ADD CONSTRAINT workflow_runs_started_by_tenant_fkey
        FOREIGN KEY (started_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    ADD CONSTRAINT workflow_runs_ticket_episode_unique
        UNIQUE (ticket_id, tenant_id, episode_number);
UPDATE workflow_runs SET started_by = (
    SELECT created_by FROM tickets WHERE tickets.ticket_id = workflow_runs.ticket_id
);
ALTER TABLE workflow_runs ALTER COLUMN started_by SET NOT NULL;

GRANT INSERT, SELECT ON admission_facts, blocker_facts, ticket_relations TO ctower_svc;
GRANT INSERT, SELECT ON blocker_heads TO ctower_svc;
GRANT UPDATE (resolved_at, resolution_evidence_ref) ON blocker_heads TO ctower_svc;

REVOKE UPDATE ON tickets, lifecycle_episodes, assignment_intervals, priority_facts
    FROM ctower_svc;
GRANT UPDATE (custodian_principal_id, priority, version, current_episode)
    ON tickets TO ctower_svc;
GRANT UPDATE (state, closed_at) ON lifecycle_episodes TO ctower_svc;
GRANT UPDATE (released_at) ON assignment_intervals TO ctower_svc;
