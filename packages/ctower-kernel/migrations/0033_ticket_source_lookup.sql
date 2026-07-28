ALTER TABLE board_projection_rows
    ADD COLUMN source_kind text,
    ADD COLUMN source_ref text;

UPDATE board_projection_rows AS board
SET source_kind = ticket.source_kind,
    source_ref = ticket.source_ref
FROM tickets AS ticket
WHERE ticket.tenant_id = board.tenant_id
  AND ticket.ticket_id = board.ticket_id;

ALTER TABLE board_projection_rows
    ALTER COLUMN source_kind SET NOT NULL,
    ALTER COLUMN source_ref SET NOT NULL,
    ADD CONSTRAINT board_projection_source_kind_length
        CHECK (length(source_kind) BETWEEN 1 AND 64),
    ADD CONSTRAINT board_projection_source_ref_length
        CHECK (length(source_ref) BETWEEN 1 AND 256);

CREATE UNIQUE INDEX tickets_tenant_source_unique
    ON tickets (tenant_id, source_kind, source_ref);
