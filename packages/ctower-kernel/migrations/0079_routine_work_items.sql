-- CT-I1-035 / D67: a Routine emits a record-backed Inbox work item.
-- The item is a pointer to Knowledge policy; completion, suppression, and
-- missed-window alarms remain typed append-only facts.

ALTER TABLE routine_revisions DROP CONSTRAINT routine_revisions_handler_kind_check;
ALTER TABLE routine_revisions ADD CONSTRAINT routine_revisions_handler_kind_check CHECK (
    handler_kind IN (
        'synthetic_four_stage', 'daily_backup', 'record_anchor',
        'dream_dispatch', 'beat_dispatch', 'routine_item'
    )
);

CREATE TABLE routine_item_specs (
    revision_digest bytea PRIMARY KEY REFERENCES routine_revisions(revision_digest),
    item_key text NOT NULL CHECK (item_key ~ '^[a-z][a-z0-9._-]*$'),
    knowledge_ref text NOT NULL CHECK (knowledge_ref ~ '^[a-z][a-z0-9._-]{0,127}$'),
    owner_seat text NOT NULL CHECK (owner_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    escalation_seat text NOT NULL CHECK (escalation_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    UNIQUE (item_key, revision_digest)
);

CREATE TABLE inbox_work_items (
    work_item_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    routine_ref text NOT NULL CHECK (routine_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    revision_digest bytea NOT NULL REFERENCES routine_item_specs(revision_digest),
    scheduled_for timestamptz NOT NULL,
    window_ends_at timestamptz NOT NULL,
    owner_seat text NOT NULL CHECK (owner_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    escalation_seat text NOT NULL CHECK (escalation_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    knowledge_ref text NOT NULL CHECK (knowledge_ref ~ '^[a-z][a-z0-9._-]{0,127}$'),
    gate_evidence jsonb NOT NULL CHECK (jsonb_typeof(gate_evidence) = 'object'),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    receipt_artifact_ref text CHECK (receipt_artifact_ref IS NULL OR length(receipt_artifact_ref) BETWEEN 1 AND 512),
    receipt_id uuid,
    created_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    UNIQUE (work_item_id, tenant_id),
    UNIQUE (tenant_id, routine_ref, scheduled_for),
    CHECK (window_ends_at > scheduled_for),
    CHECK ((status = 'open' AND receipt_id IS NULL AND receipt_artifact_ref IS NULL)
        OR (status = 'closed' AND receipt_id IS NOT NULL AND receipt_artifact_ref IS NOT NULL)),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);

CREATE TABLE routine_work_item_receipts (
    receipt_id uuid PRIMARY KEY,
    work_item_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    owner_seat text NOT NULL CHECK (owner_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    artifact_ref text NOT NULL CHECK (length(artifact_ref) BETWEEN 1 AND 512),
    delivered_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    UNIQUE (work_item_id, tenant_id),
    FOREIGN KEY (work_item_id, tenant_id)
        REFERENCES inbox_work_items(work_item_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);

CREATE TABLE routine_work_item_suppressions (
    suppression_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    routine_ref text NOT NULL CHECK (routine_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    scheduled_for timestamptz NOT NULL,
    blocking_item_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    UNIQUE (tenant_id, routine_ref, scheduled_for),
    FOREIGN KEY (blocking_item_id, tenant_id)
        REFERENCES inbox_work_items(work_item_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);

CREATE TABLE routine_work_item_alarms (
    alarm_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    routine_ref text NOT NULL CHECK (routine_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    scheduled_for timestamptz NOT NULL,
    work_item_id uuid,
    escalation_seat text NOT NULL CHECK (escalation_seat ~ '^[a-z][a-z0-9._-]{1,95}$'),
    kind text NOT NULL CHECK (kind IN ('missed_window', 'degraded_read')),
    recorded_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    UNIQUE (tenant_id, routine_ref, scheduled_for, kind),
    FOREIGN KEY (work_item_id, tenant_id)
        REFERENCES inbox_work_items(work_item_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);

ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'routine.retired', 'runtime.dream_dispatch_consumed',
    'runtime.dream_lane_bound', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'request.proposal_changed', 'ruling.recorded', 'estate.import_changed',
    'company.record_appended', 'spawn.recorded', 'spawn.transitioned',
    'pools.observation_recorded',
    'routine.work_item_appended', 'routine.work_item_suppressed',
    'routine.work_item_completed', 'routine.work_item_alarm_raised'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling', 'request_proposal',
        'company_record', 'spawn_record', 'pool_observation', 'routine_work_item'
    )
);
ALTER TABLE durability_subject_heads DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling', 'request_proposal',
        'company_record', 'spawn_record', 'pool_observation', 'routine_work_item'
    )
);

CREATE INDEX inbox_work_items_owner_status
    ON inbox_work_items (tenant_id, owner_seat, status, scheduled_for, work_item_id);
CREATE INDEX routine_work_item_alarms_escalation
    ON routine_work_item_alarms (tenant_id, escalation_seat, recorded_at, alarm_id);

REVOKE ALL ON routine_item_specs, inbox_work_items,
    routine_work_item_receipts, routine_work_item_suppressions,
    routine_work_item_alarms FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON routine_item_specs TO ctower_svc;
GRANT INSERT, SELECT, UPDATE (status, receipt_id, receipt_artifact_ref) ON inbox_work_items TO ctower_svc;
GRANT INSERT, SELECT ON routine_work_item_receipts,
    routine_work_item_suppressions, routine_work_item_alarms TO ctower_svc;
GRANT SELECT ON routine_item_specs, inbox_work_items,
    routine_work_item_receipts, routine_work_item_suppressions,
    routine_work_item_alarms TO ctower_projection;
