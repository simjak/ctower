-- CT-I1-019 completion: one operator may terminally retire an active fleet-beat
-- reference without rewriting its immutable revision, occurrence, or effect history.
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
    'ruling.recorded'
));

ALTER TABLE routine_revisions ADD CONSTRAINT routine_revisions_digest_ref_unique
    UNIQUE (revision_digest, routine_ref);

CREATE TABLE routine_retirements (
    retirement_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    routine_ref text NOT NULL CHECK (
        routine_ref ~ '^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$'
    ),
    revision_digest bytea NOT NULL,
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    retired_at timestamptz NOT NULL,
    UNIQUE (tenant_id, routine_ref),
    UNIQUE (tenant_id, actor_principal_id, client_command_id),
    UNIQUE (event_id, tenant_id),
    FOREIGN KEY (revision_digest, routine_ref)
        REFERENCES routine_revisions(revision_digest, routine_ref),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, actor_principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);

CREATE TRIGGER routine_retirements_immutable
    BEFORE UPDATE OR DELETE ON routine_retirements
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

-- This guard intentionally returns NULL instead of raising. A pre-retirement binary
-- may be rolled back for read/service continuity, but its fixed-pack registration
-- loop cannot resurrect a terminally retired tenant/reference trigger.
CREATE FUNCTION prevent_retired_routine_trigger() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM routine_revisions AS revision
        JOIN routine_retirements AS retirement
          ON retirement.routine_ref = revision.routine_ref
        WHERE retirement.tenant_id = NEW.tenant_id
          AND revision.revision_digest = NEW.revision_digest
    ) THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER routine_triggers_retirement_guard
    BEFORE INSERT OR UPDATE ON routine_triggers
    FOR EACH ROW EXECUTE FUNCTION prevent_retired_routine_trigger();

REVOKE ALL ON routine_retirements FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON routine_retirements TO ctower_svc;
GRANT SELECT ON routine_retirements TO ctower_projection;
