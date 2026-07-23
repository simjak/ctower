CREATE FUNCTION refuse_immutable_control_fact_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'control-loop fact is immutable' USING ERRCODE = '55000';
END
$$;

ALTER TABLE principals DROP CONSTRAINT principals_kind_check;
ALTER TABLE principals ADD CONSTRAINT principals_kind_check CHECK (kind IN (
    'bootstrap_installer', 'operator', 'commander', 'agent', 'reviewer', 'runner',
    'control_worker'
));
ALTER TABLE principals DROP CONSTRAINT principals_display_name_check;
ALTER TABLE principals ADD CONSTRAINT principals_display_name_check CHECK (
    (kind = 'control_worker'
        AND display_name = 'ctower:internal:control-worker:' || repeat('-', 90))
    OR
    (kind <> 'control_worker' AND length(display_name) BETWEEN 1 AND 120)
);
CREATE UNIQUE INDEX principals_one_control_worker_per_tenant
    ON principals (tenant_id) WHERE kind = 'control_worker';

ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created',
    'ticket.created',
    'ticket.custody_transferred',
    'proof.changed',
    'workflow.changed',
    'work.changed',
    'routine.occurrence_recorded',
    'attention.poison_disposition_recorded'
));
ALTER TABLE events DROP CONSTRAINT events_origin_check;
ALTER TABLE events ADD CONSTRAINT events_origin_check CHECK (
    origin IN ('api', 'bootstrap', 'control_worker')
);

CREATE TABLE workflow_start_facts (
    event_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    workflow_run_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    activity_class text NOT NULL CHECK (activity_class IN ('work', 'verification')),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (workflow_run_id, tenant_id) REFERENCES workflow_runs(workflow_run_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    UNIQUE (tenant_id, workflow_run_id)
);

INSERT INTO workflow_start_facts (
    event_id, tenant_id, workflow_run_id, ticket_id, activity_class, recorded_at
)
SELECT
    event.event_id, event.tenant_id, run.workflow_run_id, run.ticket_id,
    run.activity_class, event.server_time
FROM events AS event
JOIN workflow_runs AS run
  ON run.tenant_id = event.tenant_id AND run.workflow_run_id = event.aggregate_id
WHERE event.kind = 'workflow.changed' AND event.payload ->> 'operation' = 'start';

CREATE TRIGGER workflow_start_facts_immutable
    BEFORE UPDATE OR DELETE ON workflow_start_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

CREATE TABLE routine_revisions (
    revision_digest bytea PRIMARY KEY CHECK (octet_length(revision_digest) = 32),
    routine_ref text NOT NULL CHECK (routine_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    schedule_kind text NOT NULL CHECK (schedule_kind IN ('daily', 'hourly')),
    timezone text NOT NULL CHECK (length(timezone) BETWEEN 1 AND 128),
    local_time time,
    dst_policy text NOT NULL CHECK (dst_policy = 'wall_clock_once'),
    concurrency text NOT NULL CHECK (concurrency IN (
        'coalesce_if_active', 'skip_if_active',
        'serialize_one_pending', 'always_enqueue_bounded'
    )),
    catch_up text NOT NULL CHECK (catch_up IN (
        'skip_missed', 'coalesce_latest', 'enqueue_missed_with_cap'
    )),
    catch_up_cap integer NOT NULL CHECK (catch_up_cap BETWEEN 1 AND 100),
    timeout_seconds integer NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 86400),
    handler_kind text NOT NULL CHECK (handler_kind IN (
        'synthetic_four_stage', 'daily_backup', 'record_anchor'
    )),
    component_digests bytea[] NOT NULL CHECK (cardinality(component_digests) >= 1),
    registered_at timestamptz NOT NULL,
    UNIQUE (routine_ref),
    CHECK ((schedule_kind = 'daily' AND local_time IS NOT NULL)
        OR (schedule_kind = 'hourly' AND local_time IS NULL))
);

CREATE TABLE routine_triggers (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    revision_digest bytea NOT NULL REFERENCES routine_revisions(revision_digest),
    next_fire_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, revision_digest)
);

CREATE TABLE routine_occurrences (
    occurrence_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    revision_digest bytea NOT NULL REFERENCES routine_revisions(revision_digest),
    scheduled_for timestamptz NOT NULL,
    local_civil_time timestamp NOT NULL,
    timezone text NOT NULL CHECK (length(timezone) BETWEEN 1 AND 128),
    utc_offset_seconds integer CHECK (utc_offset_seconds BETWEEN -64800 AND 64800),
    offset_decision text NOT NULL CHECK (offset_decision IN (
        'exact', 'earlier_offset', 'nonexistent_local_time'
    )),
    outcome text NOT NULL CHECK (outcome IN ('queued', 'coalesced', 'skipped', 'refused')),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, actor_principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    UNIQUE (tenant_id, revision_digest, scheduled_for),
    UNIQUE (occurrence_id, tenant_id),
    CHECK (
        (offset_decision = 'nonexistent_local_time'
            AND utc_offset_seconds IS NULL AND outcome = 'skipped')
        OR (offset_decision <> 'nonexistent_local_time' AND utc_offset_seconds IS NOT NULL)
    )
);

CREATE TABLE operation_jobs (
    job_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    occurrence_id uuid NOT NULL,
    operation text NOT NULL CHECK (operation IN (
        'synthetic_four_stage', 'daily_backup', 'record_anchor'
    )),
    state text NOT NULL CHECK (state = 'pending'),
    timeout_seconds integer NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 86400),
    component_digests bytea[] NOT NULL CHECK (cardinality(component_digests) >= 1),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (occurrence_id, tenant_id)
        REFERENCES routine_occurrences(occurrence_id, tenant_id),
    UNIQUE (occurrence_id)
);

CREATE VIEW dispatchable_operation_jobs AS
SELECT job.*
FROM operation_jobs AS job
JOIN routine_occurrences AS occurrence
  ON occurrence.tenant_id = job.tenant_id
 AND occurrence.occurrence_id = job.occurrence_id
JOIN durability_acceptance_confirmations AS confirmation
  ON confirmation.tenant_id = occurrence.tenant_id
 AND confirmation.principal_id = occurrence.actor_principal_id
 AND confirmation.client_command_id = occurrence.client_command_id;

CREATE TABLE scheduler_watermarks (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id),
    scan_watermark bigint NOT NULL DEFAULT 0 CHECK (scan_watermark >= 0),
    status text NOT NULL CHECK (status IN ('HEALTHY', 'DEGRADED', 'STATE_UNKNOWN')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    observed_at timestamptz NOT NULL
);

CREATE TRIGGER routine_revisions_immutable
    BEFORE UPDATE OR DELETE ON routine_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER routine_occurrences_immutable
    BEFORE UPDATE OR DELETE ON routine_occurrences
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER operation_jobs_immutable
    BEFORE UPDATE OR DELETE ON operation_jobs
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

ALTER TABLE outbox ADD CONSTRAINT outbox_id_tenant_unique UNIQUE (outbox_id, tenant_id);

CREATE TABLE outbox_consumer_cursors (
    consumer_key text NOT NULL CHECK (consumer_key ~ '^[a-z][a-z0-9._-]*$'),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    topic text NOT NULL CHECK (topic ~ '^[a-z][a-z0-9._-]*$'),
    generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
    acceptance_position bigint NOT NULL DEFAULT 0 CHECK (acceptance_position >= 0),
    health text NOT NULL DEFAULT 'STATE_UNKNOWN'
        CHECK (health IN ('CURRENT', 'STATE_UNKNOWN')),
    detail text NOT NULL CHECK (length(detail) BETWEEN 1 AND 500),
    blocked_outbox_id uuid,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (consumer_key, tenant_id, topic),
    FOREIGN KEY (blocked_outbox_id, tenant_id) REFERENCES outbox(outbox_id, tenant_id)
);

CREATE TABLE board_projection_blockers (
    tenant_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    blocker_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    opened_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, ticket_id, blocker_id),
    FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES board_projection_rows(tenant_id, ticket_id) ON DELETE CASCADE
);

CREATE TABLE outbox_delivery_attempts (
    attempt_id uuid PRIMARY KEY,
    consumer_key text NOT NULL,
    tenant_id uuid NOT NULL,
    topic text NOT NULL,
    outbox_id uuid NOT NULL,
    generation bigint NOT NULL CHECK (generation > 0),
    acceptance_position bigint NOT NULL CHECK (acceptance_position > 0),
    attempt_number integer NOT NULL CHECK (attempt_number >= 1),
    outcome text NOT NULL CHECK (outcome IN (
        'delivered', 'retryable_failure', 'poisoned', 'tombstoned'
    )),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (consumer_key, tenant_id, topic)
        REFERENCES outbox_consumer_cursors(consumer_key, tenant_id, topic),
    FOREIGN KEY (outbox_id, tenant_id) REFERENCES outbox(outbox_id, tenant_id),
    UNIQUE (consumer_key, tenant_id, topic, generation, outbox_id, attempt_number)
);

CREATE TABLE outbox_poison (
    poison_id uuid PRIMARY KEY,
    consumer_key text NOT NULL,
    tenant_id uuid NOT NULL,
    topic text NOT NULL,
    outbox_id uuid NOT NULL,
    acceptance_position bigint NOT NULL CHECK (acceptance_position > 0),
    payload_digest bytea NOT NULL CHECK (octet_length(payload_digest) = 32),
    attempt_count integer NOT NULL CHECK (attempt_count >= 1),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (consumer_key, tenant_id, topic)
        REFERENCES outbox_consumer_cursors(consumer_key, tenant_id, topic),
    FOREIGN KEY (outbox_id, tenant_id) REFERENCES outbox(outbox_id, tenant_id),
    UNIQUE (consumer_key, tenant_id, topic, outbox_id)
);

CREATE TABLE outbox_poison_dispositions (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    consumer_key text NOT NULL,
    topic text NOT NULL,
    outbox_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('retry', 'tombstone')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, actor_principal_id, client_command_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, actor_principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (consumer_key, tenant_id, topic, outbox_id)
        REFERENCES outbox_poison(consumer_key, tenant_id, topic, outbox_id)
);

CREATE TABLE attention_findings (
    finding_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    finding_key text NOT NULL CHECK (finding_key ~ '^[a-z][a-z0-9._:-]*$'),
    kind text NOT NULL CHECK (kind = 'outbox_poison'),
    severity text NOT NULL CHECK (severity = 'critical'),
    summary text NOT NULL CHECK (length(summary) BETWEEN 1 AND 500),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    recorded_at timestamptz NOT NULL,
    UNIQUE (tenant_id, finding_key)
);

CREATE TABLE health_watermarks (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    contributor text NOT NULL CHECK (contributor IN (
        'durability', 'scheduler', 'outbox', 'projection',
        'backup', 'anchor', 'object', 'synthetic'
    )),
    status text NOT NULL CHECK (status IN ('HEALTHY', 'DEGRADED', 'STATE_UNKNOWN')),
    watermark bigint CHECK (watermark IS NULL OR watermark >= 0),
    threshold_seconds integer NOT NULL CHECK (threshold_seconds >= 0),
    observed_at timestamptz NOT NULL,
    owner text NOT NULL CHECK (length(owner) BETWEEN 1 AND 128),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    PRIMARY KEY (tenant_id, contributor)
);

CREATE TRIGGER outbox_delivery_attempts_immutable
    BEFORE UPDATE OR DELETE ON outbox_delivery_attempts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER outbox_poison_immutable
    BEFORE UPDATE OR DELETE ON outbox_poison
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER outbox_poison_dispositions_immutable
    BEFORE UPDATE OR DELETE ON outbox_poison_dispositions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER attention_findings_immutable
    BEFORE UPDATE OR DELETE ON attention_findings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

CREATE INDEX accepted_outbox_partition_order
    ON outbox (tenant_id, topic, outbox_id);
CREATE INDEX outbox_attempts_partition_time
    ON outbox_delivery_attempts (consumer_key, tenant_id, topic, recorded_at);
CREATE INDEX outbox_poison_partition
    ON outbox_poison (consumer_key, tenant_id, topic, acceptance_position);
CREATE INDEX routine_triggers_due
    ON routine_triggers (next_fire_at, tenant_id, revision_digest);
CREATE INDEX operation_jobs_pending
    ON operation_jobs (tenant_id, operation, created_at) WHERE state = 'pending';

GRANT INSERT, SELECT ON workflow_start_facts TO ctower_svc;
GRANT INSERT, SELECT ON routine_revisions, routine_occurrences, operation_jobs TO ctower_svc;
GRANT SELECT ON dispatchable_operation_jobs TO ctower_svc;
GRANT INSERT, SELECT ON routine_triggers, scheduler_watermarks TO ctower_svc;
GRANT UPDATE (next_fire_at, updated_at) ON routine_triggers TO ctower_svc;
GRANT UPDATE (scan_watermark, status, reason, observed_at) ON scheduler_watermarks TO ctower_svc;
GRANT INSERT, SELECT ON outbox_poison_dispositions TO ctower_svc;
GRANT SELECT ON outbox_poison, attention_findings TO ctower_svc;
GRANT INSERT, SELECT ON health_watermarks TO ctower_svc;
GRANT UPDATE (status, watermark, threshold_seconds, observed_at, owner, reason)
    ON health_watermarks TO ctower_svc;

GRANT INSERT, SELECT ON outbox_consumer_cursors, outbox_delivery_attempts,
    outbox_poison, attention_findings, health_watermarks,
    board_projection_blockers TO ctower_projection;
GRANT DELETE ON board_projection_blockers TO ctower_projection;
GRANT UPDATE (generation, acceptance_position, health, detail, blocked_outbox_id, updated_at)
    ON outbox_consumer_cursors TO ctower_projection;
GRANT UPDATE (status, watermark, threshold_seconds, observed_at, owner, reason)
    ON health_watermarks TO ctower_projection;
