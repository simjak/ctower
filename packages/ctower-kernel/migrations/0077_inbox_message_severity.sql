-- Make the authored inbox severity durable in both authority facts and the
-- disposable read projection. Existing historical messages are informational
-- because severity was not authored before this migration.
ALTER TABLE inbox_messages
    ADD COLUMN severity text NOT NULL DEFAULT 'info'
        CHECK (severity IN ('P0', 'P1', 'info'));

ALTER TABLE inbox_projection_messages
    ADD COLUMN severity text NOT NULL DEFAULT 'info'
        CHECK (severity IN ('P0', 'P1', 'info'));
