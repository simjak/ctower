-- CT-I1-032: the company-record aggregate (escape ledger first). One append-only
-- tenant-scoped accountability row per natural key; UPDATE and DELETE are
-- refused at the database boundary and the table accepts no credential
-- material or prohibited class (enforced at the kernel boundary through the
-- prohibited-data refusal before any byte commits).
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'runtime.dream_dispatch_consumed',
    'runtime.dream_lane_bound', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'ruling.recorded', 'estate.import_changed', 'company.record_appended'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling', 'company_record'
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
            'knowledge_document', 'request', 'ruling', 'company_record'
        )
    );

CREATE TABLE company_records (
    record_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    record_type text NOT NULL CHECK (record_type IN ('escape')),
    natural_key text NOT NULL CHECK (length(natural_key) BETWEEN 1 AND 256),
    occurred_on date NOT NULL,
    seat text NOT NULL CHECK (seat ~ '^[a-z][a-z0-9._-]{1,127}$'),
    payload jsonb NOT NULL,
    payload_sha256 bytea NOT NULL CHECK (octet_length(payload_sha256) = 32),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 512),
    imported_by uuid NOT NULL,
    imported_at timestamptz NOT NULL,
    command_id uuid NOT NULL,
    event_id uuid NOT NULL,
    UNIQUE (tenant_id, record_type, natural_key),
    UNIQUE (tenant_id, imported_by, command_id),
    FOREIGN KEY (imported_by, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
);
CREATE INDEX company_records_type_date
    ON company_records (tenant_id, record_type, occurred_on DESC, natural_key);

CREATE TRIGGER company_records_immutable
    BEFORE UPDATE OR DELETE ON company_records
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON company_records FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON company_records TO ctower_svc;
GRANT SELECT ON company_records TO ctower_projection;
