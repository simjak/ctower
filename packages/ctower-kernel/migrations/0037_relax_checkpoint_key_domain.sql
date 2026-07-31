-- Relax checkpoint_key CHECK constraints to the authored contract domain.
--
-- contracts/components/checkpoint.schema.json authorizes checkpoint_key values
-- matching ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$.  Migration 0027 constrained both
-- project_delivery_checkpoint_definitions and project_delivery_projection_rows
-- to the narrower I1/I2 increment pattern ^I[12]\.[0-9]+$, which made
-- catalog.apply() raise an uncaught psycopg CheckViolation for any non-increment
-- key that catalog.plan() and catalog.validate() had already accepted.
--
-- This additive migration relaxes both CHECK constraints to match the authored
-- contract pattern exactly, so validation and storage agree on the domain.

ALTER TABLE project_delivery_checkpoint_definitions
    DROP CONSTRAINT project_delivery_checkpoint_definitions_checkpoint_key_check;

ALTER TABLE project_delivery_checkpoint_definitions
    ADD CONSTRAINT project_delivery_checkpoint_definitions_checkpoint_key_check
    CHECK (checkpoint_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$');

ALTER TABLE project_delivery_projection_rows
    DROP CONSTRAINT project_delivery_projection_rows_checkpoint_key_check;

ALTER TABLE project_delivery_projection_rows
    ADD CONSTRAINT project_delivery_projection_rows_checkpoint_key_check
    CHECK (checkpoint_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$');
