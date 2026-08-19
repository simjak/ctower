-- CT-I1-035 / D67 §2: persist the exact immutable Knowledge snapshot
-- alongside the descriptive source label. Existing alias rows remain historical;
-- new Routine item revisions must carry a UUID document pin.
ALTER TABLE routine_item_specs
    ADD COLUMN document_id uuid;
ALTER TABLE inbox_work_items
    ADD COLUMN document_id uuid;

ALTER TABLE routine_item_specs
    ADD CONSTRAINT routine_item_specs_document_id_required
    CHECK (document_id IS NOT NULL) NOT VALID;
ALTER TABLE inbox_work_items
    ADD CONSTRAINT inbox_work_items_document_id_required
    CHECK (document_id IS NOT NULL) NOT VALID;
