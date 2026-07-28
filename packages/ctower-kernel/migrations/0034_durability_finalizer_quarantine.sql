CREATE TABLE durability_finalizer_attempts (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
    outcome text NOT NULL CHECK (outcome IN ('retry_scheduled', 'quarantined')),
    problem_code text NOT NULL CHECK (problem_code ~ '^[a-z][a-z0-9-]{0,63}$'),
    attempted_at timestamptz NOT NULL,
    next_attempt_at timestamptz,
    PRIMARY KEY (tenant_id, principal_id, client_command_id, attempt_number),
    FOREIGN KEY (tenant_id, principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    CHECK (
        (outcome = 'retry_scheduled' AND next_attempt_at > attempted_at)
        OR (outcome = 'quarantined' AND next_attempt_at IS NULL)
    )
);

CREATE INDEX durability_finalizer_attempts_next
    ON durability_finalizer_attempts (next_attempt_at)
    WHERE outcome = 'retry_scheduled';

CREATE TRIGGER durability_finalizer_attempts_immutable
    BEFORE UPDATE OR DELETE ON durability_finalizer_attempts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_durability_mutation();

GRANT INSERT, SELECT ON durability_finalizer_attempts TO ctower_svc;
