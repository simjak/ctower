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
CREATE UNIQUE INDEX inbox_estate_source_ref
    ON inbox_messages (tenant_id, source_ref)
    WHERE source_ref IS NOT NULL;

REVOKE UPDATE (source_ref) ON rulings, knowledge_documents, inbox_messages FROM ctower_svc;
GRANT INSERT, SELECT ON rulings, knowledge_documents, inbox_messages TO ctower_svc;
