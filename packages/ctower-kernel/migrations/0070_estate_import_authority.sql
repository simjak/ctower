-- CT-I1-032: give the operator-directed estate import path its own
-- event origin. The existing migration_importer guard remains reserved for
-- the Request cutover importer and its narrowly bounded event capability.
ALTER TABLE events DROP CONSTRAINT events_origin_check;
ALTER TABLE events ADD CONSTRAINT events_origin_check CHECK (
    origin IN ('api', 'bootstrap', 'control_worker', 'migration_importer', 'estate_import')
);

CREATE FUNCTION guard_estate_import_event() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    actor_kind text;
BEGIN
    IF NEW.origin <> 'estate_import' THEN
        RETURN NEW;
    END IF;
    SELECT kind INTO actor_kind
    FROM principals
    WHERE principal_id = NEW.actor_principal_id
      AND tenant_id = NEW.tenant_id;
    IF actor_kind <> 'operator'
        OR NEW.kind NOT IN (
            'thread.opened', 'message.appended', 'message.delivered', 'message.read',
            'knowledge.document_registered', 'ruling.recorded',
            'estate.import_changed', 'company.record_appended'
        ) THEN
        RAISE EXCEPTION 'estate import event capability denied'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER events_estate_import_guard
    BEFORE INSERT ON events FOR EACH ROW EXECUTE FUNCTION guard_estate_import_event();

ALTER TABLE knowledge_projection_documents
    DROP CONSTRAINT knowledge_projection_documents_source_ref_check;
ALTER TABLE knowledge_projection_documents
    ADD CONSTRAINT knowledge_projection_documents_source_ref_check
    CHECK (source_ref IS NULL OR length(source_ref) BETWEEN 1 AND 512);
