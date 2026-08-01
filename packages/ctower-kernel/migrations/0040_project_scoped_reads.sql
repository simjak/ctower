ALTER TABLE tickets
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
