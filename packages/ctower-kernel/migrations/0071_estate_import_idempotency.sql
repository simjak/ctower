-- CT-I1-032: retain source-path identities on the existing record tiers.
-- Import rows are immutable and operator-only at the command boundary; these
-- unique indexes make reruns converge even when a client command UUID changes.
ALTER TABLE rulings
    ADD COLUMN source_ref text
    CHECK (source_ref IS NULL OR length(source_ref) BETWEEN 1 AND 512);
CREATE UNIQUE INDEX rulings_estate_source_ref
    ON rulings (tenant_id, project_key, source_ref)
    WHERE source_ref IS NOT NULL;

ALTER TABLE knowledge_documents
    DROP CONSTRAINT knowledge_documents_source_ref_check;
ALTER TABLE knowledge_documents
    ADD CONSTRAINT knowledge_documents_source_ref_check
    CHECK (source_ref IS NULL OR length(source_ref) BETWEEN 1 AND 512);
CREATE UNIQUE INDEX knowledge_estate_source_ref
    ON knowledge_documents (tenant_id, scope, project_key, source_ref)
    WHERE source_ref IS NOT NULL;

ALTER TABLE inbox_messages
    ADD COLUMN source_ref text
    CHECK (source_ref IS NULL OR length(source_ref) BETWEEN 1 AND 512);
ALTER TABLE inbox_messages
    ADD COLUMN source_sender text
    CHECK (source_sender IS NULL OR length(source_sender) BETWEEN 1 AND 128),
    ADD COLUMN source_recipient text
    CHECK (source_recipient IS NULL OR length(source_recipient) BETWEEN 1 AND 128);
CREATE UNIQUE INDEX inbox_estate_source_ref
    ON inbox_messages (tenant_id, source_ref)
    WHERE source_ref IS NOT NULL;

CREATE TABLE estate_import_source_only_messages (
    message_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 512),
    source_sender text NOT NULL CHECK (length(source_sender) BETWEEN 1 AND 128),
    source_recipient text NOT NULL CHECK (length(source_recipient) BETWEEN 1 AND 128),
    sent_at timestamptz NOT NULL,
    subject text NOT NULL CHECK (length(subject) <= 1024),
    body text NOT NULL CHECK (length(body) BETWEEN 1 AND 65536),
    read_state text NOT NULL CHECK (read_state IN ('delivered', 'read')),
    content_sha256 bytea NOT NULL CHECK (octet_length(content_sha256) = 32),
    source_only_disposition text NOT NULL CHECK (source_only_disposition = 'source_only'),
    imported_by uuid NOT NULL,
    imported_at timestamptz NOT NULL,
    command_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, source_ref),
    UNIQUE (tenant_id, message_id),
    FOREIGN KEY (imported_by, tenant_id)
        REFERENCES principals(principal_id, tenant_id)
);
CREATE TRIGGER estate_import_source_only_messages_immutable
    BEFORE UPDATE OR DELETE ON estate_import_source_only_messages
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
REVOKE ALL ON estate_import_source_only_messages FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON estate_import_source_only_messages TO ctower_svc;
GRANT SELECT ON estate_import_source_only_messages TO ctower_projection;

REVOKE UPDATE (source_ref) ON rulings, knowledge_documents, inbox_messages FROM ctower_svc;
GRANT INSERT, SELECT ON rulings, knowledge_documents, inbox_messages TO ctower_svc;
