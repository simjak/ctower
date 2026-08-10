-- gh#403: Request-derived decision briefs and Request-to-Ruling linkage.
-- A linked Ruling stays immutable. The Request relation is part of that fact,
-- and every successor must inherit the predecessor's relation exactly.

ALTER TABLE requests ADD CONSTRAINT requests_identity_project_unique
    UNIQUE (request_id, tenant_id, project_key);

ALTER TABLE rulings ADD COLUMN request_id uuid;
ALTER TABLE rulings ADD CONSTRAINT rulings_request_project_fkey
    FOREIGN KEY (request_id, tenant_id, project_key)
    REFERENCES requests(request_id, tenant_id, project_key);

CREATE UNIQUE INDEX rulings_one_root_per_request
    ON rulings (tenant_id, request_id)
    WHERE request_id IS NOT NULL AND supersedes_ruling_id IS NULL;
CREATE INDEX rulings_request_chain
    ON rulings (tenant_id, request_id, recorded_at, ruling_id)
    WHERE request_id IS NOT NULL;

CREATE FUNCTION enforce_ruling_request_chain() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    predecessor_request_id uuid;
BEGIN
    IF NEW.supersedes_ruling_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT request_id INTO predecessor_request_id
    FROM public.rulings
    WHERE ruling_id = NEW.supersedes_ruling_id
      AND tenant_id = NEW.tenant_id
      AND project_key = NEW.project_key;
    IF NOT FOUND THEN
        RAISE foreign_key_violation
            USING MESSAGE = 'superseded Ruling is not in the same tenant and Project';
    END IF;
    IF NEW.request_id IS DISTINCT FROM predecessor_request_id THEN
        RAISE check_violation
            USING MESSAGE = 'Ruling successor must inherit the Request relation';
    END IF;
    RETURN NEW;
END
$$;
REVOKE ALL ON FUNCTION enforce_ruling_request_chain() FROM PUBLIC;
CREATE TRIGGER rulings_request_chain_guard
    BEFORE INSERT ON rulings
    FOR EACH ROW EXECUTE FUNCTION enforce_ruling_request_chain();
