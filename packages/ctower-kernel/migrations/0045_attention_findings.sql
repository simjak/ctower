-- INV-67/AC-ATT-01/AC-ATT-02: the Attention findings feed. A finding is one
-- appended typed statement of a human need; resolution/snooze/expiry/
-- cancellation/supersession are further appended dispositions, never a row
-- update or delete. Kind is drawn from the attention-kind catalog and pinned
-- to the revision active when the finding was appended.
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
    'attention.finding_appended', 'attention.finding_disposition_recorded'
));

CREATE TABLE attention_need_findings (
    finding_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    subject_ticket_id uuid NOT NULL,
    attention_kind_catalog_revision_id uuid NOT NULL,
    kind_key text NOT NULL CHECK (kind_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    reason_code text NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9._-]*$'),
    effective_owner text NOT NULL CHECK (effective_owner IN ('operator', 'commander')),
    recommendation text NOT NULL CHECK (length(recommendation) BETWEEN 1 AND 500),
    alternatives text[] NOT NULL DEFAULT ARRAY[]::text[],
    consequence text NOT NULL CHECK (length(consequence) BETWEEN 1 AND 500),
    deadline timestamptz,
    dedupe_key text NOT NULL CHECK (dedupe_key ~ '^[a-z][a-z0-9._-]{1,127}$'),
    source_facts text[] NOT NULL DEFAULT ARRAY[]::text[],
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    appended_at timestamptz NOT NULL,
    FOREIGN KEY (subject_ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (attention_kind_catalog_revision_id, tenant_id, kind_key)
        REFERENCES attention_kind_catalog_members(
            attention_kind_catalog_revision_id, tenant_id, kind_key
        ),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (finding_id, tenant_id),
    UNIQUE (event_id)
);

CREATE TABLE attention_need_dispositions (
    disposition_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    finding_id uuid NOT NULL,
    outcome text NOT NULL CHECK (
        outcome IN ('resolved', 'snoozed', 'expired', 'superseded', 'cancelled')
    ),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (finding_id, tenant_id) REFERENCES attention_need_findings(finding_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (event_id)
);

CREATE TRIGGER attention_need_findings_immutable
    BEFORE UPDATE OR DELETE ON attention_need_findings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER attention_need_dispositions_immutable
    BEFORE UPDATE OR DELETE ON attention_need_dispositions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON attention_need_findings, attention_need_dispositions
    FROM PUBLIC, ctower_svc, ctower_projection;

GRANT INSERT, SELECT ON attention_need_findings, attention_need_dispositions TO ctower_svc;
GRANT SELECT ON attention_need_findings, attention_need_dispositions TO ctower_projection;
