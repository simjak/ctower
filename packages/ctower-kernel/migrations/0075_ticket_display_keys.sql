-- CT-I1-039: immutable per-project human ticket display keys.
-- This migration is additive. Existing UUID identity and event streams remain canonical.

ALTER TABLE catalog_component_revisions
    ADD COLUMN IF NOT EXISTS project_prefix text CHECK (
        project_prefix IS NULL OR project_prefix ~ '^[A-Z]{2,5}$'
    );

ALTER TABLE tickets
    ADD COLUMN display_key text CHECK (
        display_key IS NULL OR display_key ~ '^[A-Z]{2,5}-[1-9][0-9]*$'
    );

CREATE TABLE ticket_display_sequences (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    next_number bigint NOT NULL CHECK (next_number >= 1),
    PRIMARY KEY (tenant_id, project_key)
);

-- Backfill only from the active, materialized Project component prefix. The
-- component key's first segment is the configured project key; the prefix
-- itself remains authored data and is never synthesized here.
WITH active_project_prefixes AS (
    SELECT component.component_key, split_part(component.component_key, '.', 1) AS project_key,
        revision.project_prefix
    FROM company_bundle_active AS active
    JOIN company_bundle_members AS member
      ON member.tenant_id = active.tenant_id
     AND member.bundle_revision_id = active.bundle_revision_id
    JOIN catalog_component_revisions AS revision
      ON revision.tenant_id = member.tenant_id
     AND revision.component_revision_id = member.component_revision_id
    JOIN catalog_components AS component
      ON component.tenant_id = revision.tenant_id
     AND component.component_id = revision.component_id
    WHERE component.kind = 'project' AND revision.project_prefix IS NOT NULL
), numbered AS (
    SELECT ticket.tenant_id, ticket.ticket_id,
        prefix.project_prefix || '-' || row_number() OVER (
            PARTITION BY ticket.tenant_id, ticket.project_key
            ORDER BY ticket.created_at, ticket.ticket_id
        ) AS display_key
    FROM tickets AS ticket
    JOIN active_project_prefixes AS prefix
      ON prefix.project_key = ticket.project_key
    WHERE ticket.display_key IS NULL
)
UPDATE tickets AS ticket
SET display_key = numbered.display_key
FROM numbered
WHERE ticket.tenant_id = numbered.tenant_id
  AND ticket.ticket_id = numbered.ticket_id;

INSERT INTO ticket_display_sequences (tenant_id, project_key, next_number)
SELECT tenant_id, project_key,
    max(split_part(display_key, '-', 2)::bigint) + 1
FROM tickets
WHERE display_key IS NOT NULL
GROUP BY tenant_id, project_key
ON CONFLICT (tenant_id, project_key) DO UPDATE
SET next_number = GREATEST(
    ticket_display_sequences.next_number,
    EXCLUDED.next_number
);

CREATE UNIQUE INDEX tickets_display_key
    ON tickets (tenant_id, project_key, display_key)
    WHERE display_key IS NOT NULL;

CREATE FUNCTION refuse_ticket_display_key_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.display_key IS DISTINCT FROM NEW.display_key THEN
        RAISE EXCEPTION 'ticket display key is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER tickets_display_key_immutable
    BEFORE UPDATE OF display_key ON tickets
    FOR EACH ROW EXECUTE FUNCTION refuse_ticket_display_key_mutation();

ALTER TABLE board_projection_rows
    ADD COLUMN display_key text CHECK (
        display_key IS NULL OR display_key ~ '^[A-Z]{2,5}-[1-9][0-9]*$'
    );

UPDATE board_projection_rows AS board
SET display_key = ticket.display_key
FROM tickets AS ticket
WHERE ticket.tenant_id = board.tenant_id
  AND ticket.ticket_id = board.ticket_id;

CREATE INDEX board_projection_display_key
    ON board_projection_rows (tenant_id, project_key, display_key)
    WHERE display_key IS NOT NULL;

GRANT INSERT, SELECT, UPDATE ON ticket_display_sequences TO ctower_svc;
GRANT SELECT (project_prefix) ON catalog_component_revisions TO ctower_svc;
GRANT SELECT (display_key) ON tickets TO ctower_projection;
GRANT SELECT (display_key) ON board_projection_rows TO ctower_svc;
