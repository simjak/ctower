ALTER TABLE tickets ADD COLUMN project_key text;

DO $migration$
DECLARE
    authoritative_project_key text;
    defaulted_ticket_count bigint;
BEGIN
    SELECT domain_match[1]
    INTO authoritative_project_key
    FROM pg_constraint AS constraint_row
    CROSS JOIN LATERAL regexp_match(
        pg_get_expr(constraint_row.conbin, constraint_row.conrelid, false),
        $constraint$^\(?project_key = '([a-z][a-z0-9-]{2,63})'::text\)?$$constraint$
    ) AS domain_match
    WHERE constraint_row.conrelid = 'ticket_project_bindings'::regclass
      AND constraint_row.conname = 'ticket_project_bindings_project_key_check';

    IF authoritative_project_key IS NULL THEN
        RAISE EXCEPTION
            '0038_project_scoped_reads: pre-migration binding domain does not pin one project';
    END IF;

    UPDATE tickets AS ticket
    SET project_key = binding.project_key
    FROM ticket_project_bindings AS binding
    WHERE binding.tenant_id = ticket.tenant_id
      AND binding.ticket_id = ticket.ticket_id;

    SELECT count(*)
    INTO defaulted_ticket_count
    FROM tickets
    WHERE project_key IS NULL;

    UPDATE tickets
    SET project_key = authoritative_project_key
    WHERE project_key IS NULL;

    RAISE NOTICE
        '0038_project_scoped_reads: defaulted_ticket_count=% authoritative_project_key=%',
        defaulted_ticket_count,
        authoritative_project_key;
END
$migration$;

ALTER TABLE tickets
    ALTER COLUMN project_key SET NOT NULL,
    ADD CONSTRAINT tickets_project_key_check
        CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    ADD CONSTRAINT tickets_tenant_project_unique
        UNIQUE (ticket_id, tenant_id, project_key);

ALTER TABLE ticket_project_bindings
    DROP CONSTRAINT ticket_project_bindings_project_key_check,
    ADD CONSTRAINT ticket_project_bindings_project_key_check
        CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    ADD CONSTRAINT ticket_project_bindings_ticket_project_fk
        FOREIGN KEY (ticket_id, tenant_id, project_key)
        REFERENCES tickets(ticket_id, tenant_id, project_key);

ALTER TABLE inbound_source_aliases
    DROP CONSTRAINT inbound_source_aliases_pkey,
    ADD PRIMARY KEY (tenant_id, project_key, source_kind, source_ref);

ALTER TABLE board_projection_rows ADD COLUMN project_key text;

UPDATE board_projection_rows AS board
SET project_key = ticket.project_key
FROM tickets AS ticket
WHERE ticket.tenant_id = board.tenant_id
  AND ticket.ticket_id = board.ticket_id;

ALTER TABLE board_projection_rows
    ALTER COLUMN project_key SET NOT NULL,
    ADD CONSTRAINT board_projection_project_key_check
        CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$');

ALTER TABLE board_projection_rows
    ADD CONSTRAINT board_projection_ticket_project_fk
        FOREIGN KEY (ticket_id, tenant_id, project_key)
        REFERENCES tickets(ticket_id, tenant_id, project_key);

CREATE INDEX board_projection_project_ticket
    ON board_projection_rows (tenant_id, project_key, ticket_id);

GRANT SELECT (ticket_id, tenant_id, project_key) ON tickets TO ctower_projection;
