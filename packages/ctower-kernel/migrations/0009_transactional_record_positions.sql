ALTER TABLE events ALTER COLUMN record_position DROP IDENTITY;
ALTER TABLE events DROP CONSTRAINT events_record_position_unique;

WITH committed_order AS (
    SELECT event_id, row_number() OVER (ORDER BY record_position, event_id)::bigint AS position
    FROM events
)
UPDATE events AS event
SET record_position = committed_order.position
FROM committed_order
WHERE committed_order.event_id = event.event_id;

ALTER TABLE events ADD CONSTRAINT events_record_position_unique UNIQUE (record_position);

CREATE TABLE record_position_ledger (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    last_position bigint NOT NULL CHECK (last_position >= 0)
);

INSERT INTO record_position_ledger (singleton, last_position)
SELECT true, count(*)::bigint FROM events;

GRANT SELECT ON record_position_ledger TO ctower_svc, ctower_projection;
GRANT UPDATE (last_position) ON record_position_ledger TO ctower_svc;
