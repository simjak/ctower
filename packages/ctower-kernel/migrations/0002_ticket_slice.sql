CREATE TABLE tenants (
    tenant_id uuid PRIMARY KEY,
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z][a-z0-9-]{1,62}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL
);

CREATE TABLE principals (
    principal_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    kind text NOT NULL CHECK (kind IN ('bootstrap_installer', 'operator', 'commander')),
    display_name text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    disabled boolean NOT NULL DEFAULT false,
    credential_ref text,
    vault_ref text,
    created_at timestamptz NOT NULL,
    UNIQUE (tenant_id, display_name),
    UNIQUE (principal_id, tenant_id)
);

CREATE TABLE principal_credentials (
    credential_id uuid PRIMARY KEY,
    principal_id uuid NOT NULL REFERENCES principals(principal_id),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    credential_digest bytea NOT NULL UNIQUE CHECK (octet_length(credential_digest) = 32),
    created_at timestamptz NOT NULL,
    revoked_at timestamptz,
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE bootstrap_capability (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    capability_digest bytea NOT NULL UNIQUE CHECK (octet_length(capability_digest) = 32),
    allowed_origin inet NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    consumed_command_id uuid,
    consumed_request_sha256 bytea CHECK (
        consumed_request_sha256 IS NULL OR octet_length(consumed_request_sha256) = 32
    ),
    receipt_body jsonb,
    CHECK (
        (consumed_at IS NULL AND consumed_command_id IS NULL AND consumed_request_sha256 IS NULL
            AND receipt_body IS NULL)
        OR
        (consumed_at IS NOT NULL AND consumed_command_id IS NOT NULL
            AND consumed_request_sha256 IS NOT NULL AND receipt_body IS NOT NULL)
    )
);

CREATE TABLE tickets (
    ticket_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    source_kind text NOT NULL CHECK (length(source_kind) BETWEEN 1 AND 64),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    priority text NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    custodian_principal_id uuid NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    durability_state text NOT NULL CHECK (durability_state = 'durability_pending'),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (custodian_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (created_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (ticket_id, tenant_id)
);

CREATE TABLE lifecycle_episodes (
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    episode_number integer NOT NULL CHECK (episode_number = 1),
    state text NOT NULL CHECK (state = 'open'),
    opened_at timestamptz NOT NULL,
    PRIMARY KEY (ticket_id, episode_number),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id)
);

CREATE TABLE assignment_intervals (
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    interval_sequence integer NOT NULL CHECK (interval_sequence >= 1),
    assignment_kind text NOT NULL CHECK (assignment_kind = 'ticket_custodian'),
    principal_id uuid NOT NULL,
    assigned_at timestamptz NOT NULL,
    released_at timestamptz,
    changed_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    client_command_id uuid NOT NULL,
    PRIMARY KEY (ticket_id, assignment_kind, interval_sequence),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (changed_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    CHECK (released_at IS NULL OR released_at >= assigned_at)
);

CREATE UNIQUE INDEX one_current_ticket_custodian
    ON assignment_intervals (ticket_id)
    WHERE assignment_kind = 'ticket_custodian' AND released_at IS NULL;

CREATE TABLE priority_facts (
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    fact_sequence integer NOT NULL CHECK (fact_sequence = 1),
    priority text NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    changed_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    client_command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (ticket_id, fact_sequence),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (changed_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE events (
    event_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    stream_id text NOT NULL,
    aggregate_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    kind text NOT NULL CHECK (kind IN (
        'bootstrap.first_tenant_created',
        'ticket.created',
        'ticket.custody_transferred'
    )),
    schema_version integer NOT NULL CHECK (schema_version = 1),
    actor_principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    request_sha256 bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    correlation_id uuid NOT NULL,
    causation_id uuid,
    origin text NOT NULL CHECK (origin IN ('api', 'bootstrap')),
    server_time timestamptz NOT NULL,
    payload jsonb NOT NULL,
    prev_hash bytea NOT NULL CHECK (octet_length(prev_hash) = 32),
    event_hash bytea NOT NULL CHECK (octet_length(event_hash) = 32),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, stream_id, sequence),
    UNIQUE (tenant_id, event_hash)
);

CREATE TABLE command_results (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    request_sha256 bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    status_code integer NOT NULL CHECK (status_code BETWEEN 200 AND 299),
    response_body jsonb NOT NULL,
    event_ids uuid[] NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (principal_id, client_command_id),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE outbox (
    outbox_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    event_id uuid NOT NULL REFERENCES events(event_id),
    topic text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (event_id, topic)
);

CREATE INDEX events_timeline ON events (tenant_id, aggregate_id, sequence);
CREATE INDEX tickets_tenant ON tickets (tenant_id, ticket_id);
