-- gh#332 (IS-07 decision 7): the knowledge base. A registered document is one
-- append-only control fact; its title/body/scope are immutable. Retrieval goes
-- through the knowledge_projection_documents projection (list by scope, get one).
-- The external-source MCP/adapter seam is a later phase (D10: one impl now).
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
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'thread.promoted_to_ticket',
    'knowledge.document_registered'
));

-- The knowledge_document subject appears in the durability subject heads so the
-- record can prove append-only facts project-wide (the same subject-kind domain
-- used by event_links and durability_subject_heads).
ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document'
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
            'knowledge_document'
        )
    );

-- Authority trust: one immutable fact row per registered document. The fact is
-- the source of truth; the projection below is derived and disposable.
CREATE TABLE knowledge_documents (
    document_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    scope text NOT NULL CHECK (scope IN ('org', 'project')),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 1024),
    body text NOT NULL CHECK (length(body) BETWEEN 1 AND 1048576),
    registered_by uuid NOT NULL,
    registered_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    UNIQUE (document_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (registered_by, tenant_id)
        REFERENCES principals(principal_id, tenant_id)
);

-- Read-side projection: list by scope, retrieve one. Every column is copied from
-- the accepted fact; nothing here is authoritative on its own.
CREATE TABLE knowledge_projection_documents (
    tenant_id uuid NOT NULL,
    document_id uuid NOT NULL,
    scope text NOT NULL CHECK (scope IN ('org', 'project')),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 1024),
    body text NOT NULL CHECK (length(body) BETWEEN 1 AND 1048576),
    registered_by uuid NOT NULL,
    registered_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, document_id),
    FOREIGN KEY (document_id, tenant_id)
        REFERENCES knowledge_documents(document_id, tenant_id)
);
CREATE INDEX knowledge_projection_documents_scope_idx
    ON knowledge_projection_documents (tenant_id, scope, registered_at);

CREATE TRIGGER knowledge_documents_immutable
    BEFORE UPDATE OR DELETE ON knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON knowledge_documents, knowledge_projection_documents
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON knowledge_documents, knowledge_projection_documents
    TO ctower_svc;
GRANT SELECT ON knowledge_documents, knowledge_projection_documents
    TO ctower_projection;
