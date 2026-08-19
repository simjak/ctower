-- gh#457: retirement is a new immutable tenant-scoped fact. The mutable
-- scheduling trigger is removed; Routine revisions, occurrences, and effects
-- remain append-only history.
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'routine.retired',
    'runtime.dream_dispatch_consumed', 'runtime.dream_lane_bound',
    'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'ruling.recorded'
));

CREATE TABLE routine_retirements (
    retirement_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    routine_ref text NOT NULL CHECK (
        routine_ref ~ '^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$'
    ),
    revision_digest bytea NOT NULL REFERENCES routine_revisions(revision_digest),
    retired_by uuid NOT NULL,
    command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    retired_at timestamptz NOT NULL,
    UNIQUE (retirement_id, tenant_id),
    UNIQUE (tenant_id, routine_ref),
    UNIQUE (tenant_id, retired_by, command_id),
    FOREIGN KEY (retired_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);
CREATE INDEX routine_retirements_ref_tenant
    ON routine_retirements (routine_ref, tenant_id);

CREATE TRIGGER routine_retirements_immutable
    BEFORE UPDATE OR DELETE ON routine_retirements
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON routine_retirements FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON routine_retirements TO ctower_svc;
GRANT SELECT ON routine_retirements TO ctower_projection;
