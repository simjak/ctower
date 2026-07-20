ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created',
    'ticket.created',
    'ticket.custody_transferred',
    'proof.changed',
    'workflow.changed'
));

CREATE TABLE proof_bundles (
    proof_id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    candidate_digest bytea NOT NULL CHECK (octet_length(candidate_digest) = 32),
    candidate_author_id uuid NOT NULL,
    frozen_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (candidate_author_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (ticket_id, tenant_id),
    UNIQUE (proof_id, tenant_id)
);

CREATE TABLE proof_criteria (
    proof_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    criterion_key text NOT NULL CHECK (criterion_key ~ '^[a-z][a-z0-9._-]*$'),
    description text NOT NULL CHECK (length(description) BETWEEN 1 AND 500),
    candidate_dependent boolean NOT NULL,
    requires_verdict boolean NOT NULL,
    frozen_by uuid NOT NULL,
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (proof_id, criterion_key),
    FOREIGN KEY (proof_id, tenant_id) REFERENCES proof_bundles(proof_id, tenant_id),
    FOREIGN KEY (frozen_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (proof_id, tenant_id, criterion_key)
);

CREATE TABLE proof_objects (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    content bytea NOT NULL,
    producer_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, artifact_digest),
    FOREIGN KEY (producer_id, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE proof_evidence (
    evidence_id uuid PRIMARY KEY,
    proof_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    criterion_key text NOT NULL,
    candidate_digest bytea NOT NULL CHECK (octet_length(candidate_digest) = 32),
    artifact_digest bytea NOT NULL CHECK (octet_length(artifact_digest) = 32),
    producer_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (proof_id, tenant_id, criterion_key)
        REFERENCES proof_criteria(proof_id, tenant_id, criterion_key),
    FOREIGN KEY (tenant_id, artifact_digest)
        REFERENCES proof_objects(tenant_id, artifact_digest),
    FOREIGN KEY (producer_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (evidence_id, tenant_id)
);

CREATE TABLE proof_verdicts (
    verdict_id uuid PRIMARY KEY,
    proof_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    criterion_key text NOT NULL,
    candidate_digest bytea NOT NULL CHECK (octet_length(candidate_digest) = 32),
    reviewer_id uuid NOT NULL,
    decision text NOT NULL CHECK (decision IN ('pass', 'fail')),
    protected boolean NOT NULL CHECK (protected),
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (proof_id, tenant_id, criterion_key)
        REFERENCES proof_criteria(proof_id, tenant_id, criterion_key),
    FOREIGN KEY (reviewer_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (verdict_id, tenant_id)
);

CREATE TABLE proof_invalidations (
    invalidation_id uuid PRIMARY KEY,
    proof_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    target_kind text NOT NULL CHECK (target_kind IN ('evidence', 'verdict')),
    target_id uuid NOT NULL,
    candidate_digest bytea NOT NULL CHECK (octet_length(candidate_digest) = 32),
    reason text NOT NULL CHECK (reason = 'candidate-digest-changed'),
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (proof_id, tenant_id) REFERENCES proof_bundles(proof_id, tenant_id),
    UNIQUE (proof_id, target_kind, target_id, candidate_digest)
);

CREATE TABLE workflow_runs (
    workflow_run_id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workflow_key text NOT NULL CHECK (workflow_key ~ '^[a-z][a-z0-9._-]*$'),
    workflow_revision integer NOT NULL CHECK (workflow_revision >= 1),
    initial_stage text NOT NULL CHECK (initial_stage ~ '^[a-z][a-z0-9._-]*$'),
    current_stage text NOT NULL CHECK (current_stage ~ '^[a-z][a-z0-9._-]*$'),
    activity_class text NOT NULL CHECK (activity_class IN ('work', 'verification')),
    version integer NOT NULL CHECK (version >= 1),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    UNIQUE (ticket_id, tenant_id),
    UNIQUE (workflow_run_id, tenant_id)
);

CREATE TABLE workflow_transition_facts (
    transition_id uuid PRIMARY KEY,
    workflow_run_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    fact_sequence integer NOT NULL CHECK (fact_sequence >= 1),
    source_stage text NOT NULL CHECK (source_stage ~ '^[a-z][a-z0-9._-]*$'),
    destination_stage text NOT NULL CHECK (destination_stage ~ '^[a-z][a-z0-9._-]*$'),
    predicate_ref text NOT NULL CHECK (predicate_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    activity_class text NOT NULL CHECK (activity_class IN ('work', 'verification')),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (workflow_run_id, tenant_id)
        REFERENCES workflow_runs(workflow_run_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (workflow_run_id, fact_sequence)
);

CREATE TABLE lifecycle_facts (
    lifecycle_fact_id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    fact_sequence integer NOT NULL CHECK (fact_sequence IN (1, 2)),
    state text NOT NULL CHECK (state IN ('resolved', 'closed')),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (ticket_id, fact_sequence),
    UNIQUE (ticket_id, state)
);

CREATE INDEX proof_bundle_ticket ON proof_bundles (tenant_id, ticket_id);
CREATE INDEX workflow_run_ticket ON workflow_runs (tenant_id, ticket_id);

GRANT SELECT, INSERT, UPDATE ON proof_bundles, workflow_runs TO ctower_svc;
GRANT INSERT, SELECT ON proof_criteria, proof_objects, proof_evidence, proof_verdicts,
    proof_invalidations, workflow_transition_facts, lifecycle_facts TO ctower_svc;
