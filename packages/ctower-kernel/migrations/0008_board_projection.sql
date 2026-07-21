ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created',
    'ticket.created',
    'ticket.custody_transferred',
    'proof.changed',
    'workflow.changed',
    'work.changed'
));
ALTER TABLE events ADD COLUMN record_position bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE events ADD CONSTRAINT events_record_position_unique UNIQUE (record_position);
ALTER TABLE events ADD CONSTRAINT events_id_tenant_unique UNIQUE (event_id, tenant_id);

CREATE TABLE event_links (
    event_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    subject_kind text NOT NULL CHECK (subject_kind IN ('ticket', 'work', 'workflow', 'proof')),
    subject_id uuid NOT NULL,
    PRIMARY KEY (event_id, subject_kind, subject_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);
CREATE INDEX event_links_subject
    ON event_links (tenant_id, subject_kind, subject_id, event_id);

INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
SELECT event_id, tenant_id,
    CASE WHEN kind = 'work.changed' THEN 'work' ELSE 'ticket' END,
    aggregate_id
FROM events WHERE kind IN ('ticket.created', 'ticket.custody_transferred', 'work.changed');

INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
SELECT event.event_id, event.tenant_id, 'workflow', run.workflow_run_id
FROM events AS event
JOIN workflow_runs AS run
  ON run.tenant_id = event.tenant_id AND run.workflow_run_id = event.aggregate_id
WHERE event.kind = 'workflow.changed';
INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
SELECT event.event_id, event.tenant_id, 'ticket', run.ticket_id
FROM events AS event
JOIN workflow_runs AS run
  ON run.tenant_id = event.tenant_id AND run.workflow_run_id = event.aggregate_id
WHERE event.kind = 'workflow.changed';

INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
SELECT event.event_id, event.tenant_id, 'proof', bundle.proof_id
FROM events AS event
JOIN proof_bundles AS bundle
  ON bundle.tenant_id = event.tenant_id AND bundle.proof_id = event.aggregate_id
WHERE event.kind = 'proof.changed';
INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
SELECT event.event_id, event.tenant_id, 'ticket', bundle.ticket_id
FROM events AS event
JOIN proof_bundles AS bundle
  ON bundle.tenant_id = event.tenant_id AND bundle.proof_id = event.aggregate_id
WHERE event.kind = 'proof.changed';

CREATE TABLE board_projection_rows (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    ticket_id uuid NOT NULL,
    title text NOT NULL,
    lane text NOT NULL CHECK (lane IN (
        'backlog', 'ready', 'in_progress', 'in_review', 'blocked', 'complete'
    )),
    underlying_lane text CHECK (underlying_lane IN (
        'backlog', 'ready', 'in_progress', 'in_review', 'complete'
    )),
    priority text NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    stage_key text CHECK (stage_key IS NULL OR stage_key ~ '^[a-z][a-z0-9._-]*$'),
    activity_class text CHECK (activity_class IS NULL OR activity_class IN ('work', 'verification')),
    custodian_id uuid NOT NULL,
    assignee_id uuid,
    blocker_reason text,
    blocker_opened_at timestamptz,
    risk text,
    delivery_facts jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(delivery_facts) = 'array'
    ),
    ticket_version integer NOT NULL CHECK (ticket_version >= 1),
    source_position bigint NOT NULL CHECK (source_position >= 0),
    PRIMARY KEY (tenant_id, ticket_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id)
);

CREATE TABLE projection_cursors (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id),
    projection_watermark bigint NOT NULL DEFAULT 0 CHECK (projection_watermark >= 0),
    health text NOT NULL DEFAULT 'STATE_UNKNOWN' CHECK (health IN ('CURRENT', 'STATE_UNKNOWN')),
    detail text NOT NULL DEFAULT 'not-built',
    updated_at timestamptz NOT NULL
);

GRANT INSERT, SELECT ON event_links TO ctower_svc;
GRANT SELECT ON board_projection_rows, projection_cursors TO ctower_svc;
GRANT INSERT, UPDATE, DELETE ON board_projection_rows TO ctower_projection;
GRANT INSERT, UPDATE, DELETE ON projection_cursors TO ctower_projection;
GRANT USAGE, SELECT ON SEQUENCE events_record_position_seq TO ctower_svc;
