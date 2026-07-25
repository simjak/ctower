ALTER TABLE operation_jobs
    ADD CONSTRAINT operation_jobs_job_tenant_unique UNIQUE (job_id, tenant_id);

CREATE TABLE fixed_operation_attempts (
    attempt_id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    attempt_number integer NOT NULL CHECK (attempt_number BETWEEN 1 AND 8),
    fencing_token uuid NOT NULL,
    worker_ref text NOT NULL CHECK (
        worker_ref ~ '^[a-z][a-z0-9._:-]{2,127}$'
    ),
    claimed_at timestamptz NOT NULL,
    claim_expires_at timestamptz NOT NULL CHECK (claim_expires_at > claimed_at),
    FOREIGN KEY (job_id, tenant_id)
        REFERENCES operation_jobs(job_id, tenant_id),
    UNIQUE (attempt_id, tenant_id),
    UNIQUE (job_id, attempt_number),
    UNIQUE (job_id, fencing_token)
);

CREATE TABLE fixed_operation_results (
    result_id uuid PRIMARY KEY,
    job_id uuid NOT NULL UNIQUE,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    attempt_id uuid NOT NULL,
    fencing_token uuid NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('succeeded', 'failed')),
    ticket_id uuid,
    lifecycle_facts text[] NOT NULL,
    detail_code text NOT NULL CHECK (
        detail_code ~ '^[a-z][a-z0-9._-]{2,95}$'
    ),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (job_id, tenant_id)
        REFERENCES operation_jobs(job_id, tenant_id),
    FOREIGN KEY (attempt_id, tenant_id)
        REFERENCES fixed_operation_attempts(attempt_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    CHECK (
        (outcome = 'succeeded' AND ticket_id IS NOT NULL
            AND lifecycle_facts = ARRAY['resolved', 'closed']::text[])
        OR
        (outcome = 'failed' AND lifecycle_facts = ARRAY[]::text[])
    )
);

CREATE TRIGGER fixed_operation_attempts_immutable
    BEFORE UPDATE OR DELETE ON fixed_operation_attempts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER fixed_operation_results_immutable
    BEFORE UPDATE OR DELETE ON fixed_operation_results
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON fixed_operation_attempts, fixed_operation_results
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON fixed_operation_attempts, fixed_operation_results TO ctower_svc;
