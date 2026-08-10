-- gh#403: Request-derived decision briefs and Request-to-Ruling linkage.
-- A linked Ruling stays immutable. Each root answers one exact active decision
-- blocker fact, and every successor inherits that occurrence relation exactly.

ALTER TABLE requests ADD CONSTRAINT requests_identity_project_unique
    UNIQUE (request_id, tenant_id, project_key);
ALTER TABLE request_blocker_facts ADD CONSTRAINT request_blocker_fact_request_unique
    UNIQUE (blocker_fact_id, request_id, tenant_id);

ALTER TABLE rulings ADD COLUMN request_id uuid;
ALTER TABLE rulings ADD COLUMN decision_blocker_fact_id uuid;
ALTER TABLE rulings ADD CONSTRAINT rulings_request_project_fkey
    FOREIGN KEY (request_id, tenant_id, project_key)
    REFERENCES requests(request_id, tenant_id, project_key);
ALTER TABLE rulings ADD CONSTRAINT rulings_decision_occurrence_fkey
    FOREIGN KEY (decision_blocker_fact_id, request_id, tenant_id)
    REFERENCES request_blocker_facts(blocker_fact_id, request_id, tenant_id);
ALTER TABLE rulings ADD CONSTRAINT rulings_decision_occurrence_pair
    CHECK ((request_id IS NULL) = (decision_blocker_fact_id IS NULL));

CREATE UNIQUE INDEX rulings_one_root_per_decision_occurrence
    ON rulings (tenant_id, decision_blocker_fact_id)
    WHERE decision_blocker_fact_id IS NOT NULL AND supersedes_ruling_id IS NULL;
CREATE INDEX rulings_request_chain
    ON rulings (tenant_id, request_id, decision_blocker_fact_id, recorded_at, ruling_id)
    WHERE request_id IS NOT NULL;

CREATE FUNCTION enforce_ruling_request_chain() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    predecessor_request_id uuid;
    predecessor_decision_fact_id uuid;
    decision_key text;
    decision_active boolean;
BEGIN
    IF NEW.supersedes_ruling_id IS NULL THEN
        IF NEW.decision_blocker_fact_id IS NULL THEN
            RETURN NEW;
        END IF;
        SELECT blocker_key, active INTO decision_key, decision_active
        FROM public.request_blocker_facts
        WHERE blocker_fact_id = NEW.decision_blocker_fact_id
          AND request_id = NEW.request_id
          AND tenant_id = NEW.tenant_id;
        IF NOT FOUND OR decision_key <> 'operator-decision-required' OR NOT decision_active THEN
            RAISE check_violation
                USING MESSAGE = 'Ruling root must answer one active operator decision fact';
        END IF;
        RETURN NEW;
    END IF;
    SELECT request_id, decision_blocker_fact_id
      INTO predecessor_request_id, predecessor_decision_fact_id
    FROM public.rulings
    WHERE ruling_id = NEW.supersedes_ruling_id
      AND tenant_id = NEW.tenant_id
      AND project_key = NEW.project_key;
    IF NOT FOUND THEN
        RAISE foreign_key_violation
            USING MESSAGE = 'superseded Ruling is not in the same tenant and Project';
    END IF;
    IF NEW.request_id IS DISTINCT FROM predecessor_request_id
       OR NEW.decision_blocker_fact_id IS DISTINCT FROM predecessor_decision_fact_id THEN
        RAISE check_violation
            USING MESSAGE = 'Ruling successor must inherit the Request decision occurrence';
    END IF;
    RETURN NEW;
END
$$;
REVOKE ALL ON FUNCTION enforce_ruling_request_chain() FROM PUBLIC;
CREATE TRIGGER rulings_request_chain_guard
    BEFORE INSERT ON rulings
    FOR EACH ROW EXECUTE FUNCTION enforce_ruling_request_chain();

-- Exact replay remains strict after the boundary grows: canonicalize existing
-- Ruling receipts once instead of carrying runtime compatibility fallbacks.
UPDATE command_results
SET response_body = response_body || jsonb_build_object(
    'request_id', NULL,
    'supersedes_ruling_id', response_body -> 'supersedes_ruling_id'
)
WHERE response_body ? 'ruling_id' AND NOT response_body ? 'request_id';
