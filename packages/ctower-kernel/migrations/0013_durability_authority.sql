ALTER TABLE command_results
    ADD CONSTRAINT command_results_tenant_principal_command_unique
    UNIQUE (tenant_id, principal_id, client_command_id);

CREATE TABLE durability_policy_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    policy_ref text NOT NULL CHECK (policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    mode text NOT NULL CHECK (mode IN ('pending_only', 'cutover_rpo0')),
    standby_application_name text NOT NULL CHECK (standby_application_name = 'ctower_i1_ack'),
    standby_identity text NOT NULL CHECK (length(standby_identity) BETWEEN 1 AND 128),
    commit_deadline_ms integer NOT NULL CHECK (commit_deadline_ms BETWEEN 100 AND 30000),
    retry_after_seconds integer NOT NULL CHECK (retry_after_seconds BETWEEN 1 AND 60),
    configured_at timestamptz NOT NULL
);

INSERT INTO durability_policy_state (
    singleton,
    policy_ref,
    mode,
    standby_application_name,
    standby_identity,
    commit_deadline_ms,
    retry_after_seconds,
    configured_at
) VALUES (
    true,
    'ctower.pending-only@1',
    'pending_only',
    'ctower_i1_ack',
    'unconfigured',
    1500,
    1,
    transaction_timestamp()
);

CREATE TABLE durability_subject_heads (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    subject_kind text NOT NULL CHECK (subject_kind IN ('ticket', 'work', 'workflow', 'proof')),
    subject_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, subject_kind, subject_id),
    FOREIGN KEY (tenant_id, principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id)
);

WITH ranked_heads AS (
    SELECT
        link.tenant_id,
        link.subject_kind,
        link.subject_id,
        event.actor_principal_id AS principal_id,
        event.client_command_id,
        event.server_time AS updated_at,
        row_number() OVER (
            PARTITION BY link.tenant_id, link.subject_kind, link.subject_id
            ORDER BY event.record_position DESC, event.event_id DESC
        ) AS rank
    FROM event_links AS link
    JOIN events AS event
      ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
    JOIN command_results AS result
      ON result.tenant_id = event.tenant_id
     AND result.principal_id = event.actor_principal_id
     AND result.client_command_id = event.client_command_id
)
INSERT INTO durability_subject_heads (
    tenant_id, subject_kind, subject_id, principal_id, client_command_id, updated_at
)
SELECT tenant_id, subject_kind, subject_id, principal_id, client_command_id, updated_at
FROM ranked_heads
WHERE rank = 1;

CREATE TABLE durability_acknowledgements (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    request_sha256 bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    command_root bytea NOT NULL CHECK (octet_length(command_root) = 32),
    acceptance_position bigint GENERATED ALWAYS AS IDENTITY,
    policy_ref text NOT NULL CHECK (policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    standby_application_name text NOT NULL CHECK (standby_application_name = 'ctower_i1_ack'),
    standby_identity text NOT NULL CHECK (length(standby_identity) BETWEEN 1 AND 128),
    standby_system_identifier numeric(20, 0) NOT NULL CHECK (standby_system_identifier > 0),
    standby_timeline_id integer NOT NULL CHECK (standby_timeline_id >= 1),
    standby_replay_lsn pg_lsn NOT NULL,
    acknowledged_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, principal_id, client_command_id),
    UNIQUE (acceptance_position),
    FOREIGN KEY (tenant_id, principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id)
);

CREATE TABLE durability_target_observations (
    observation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    request_sha256 bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    command_root bytea NOT NULL CHECK (octet_length(command_root) = 32),
    policy_ref text NOT NULL CHECK (policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    standby_application_name text NOT NULL,
    expected_standby_identity text NOT NULL CHECK (length(expected_standby_identity) BETWEEN 1 AND 128),
    observed_standby_identity text,
    standby_system_identifier numeric(20, 0),
    standby_timeline_id integer,
    standby_replay_lsn pg_lsn,
    standby_in_recovery boolean,
    request_matches boolean NOT NULL,
    command_root_matches boolean NOT NULL,
    replay_visible boolean NOT NULL,
    receipt_visible boolean NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('matched', 'pending', 'integrity_mismatch')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    observed_at timestamptz NOT NULL,
    FOREIGN KEY (tenant_id, principal_id, client_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    CHECK (
        standby_timeline_id IS NULL OR standby_timeline_id >= 1
    ),
    CHECK (
        standby_system_identifier IS NULL OR standby_system_identifier > 0
    )
);

CREATE INDEX durability_subject_heads_command
    ON durability_subject_heads (tenant_id, principal_id, client_command_id);
CREATE INDEX durability_acknowledgements_root
    ON durability_acknowledgements (tenant_id, command_root);
CREATE INDEX durability_acknowledgements_accepted_order
    ON durability_acknowledgements (acceptance_position, tenant_id);
CREATE INDEX durability_target_observations_command_time
    ON durability_target_observations (tenant_id, principal_id, client_command_id, observed_at DESC);

CREATE FUNCTION refuse_immutable_durability_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'durability evidence is immutable' USING ERRCODE = '55000';
END
$$;

CREATE TRIGGER durability_acknowledgements_immutable
    BEFORE UPDATE OR DELETE ON durability_acknowledgements
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_durability_mutation();
CREATE TRIGGER durability_target_observations_immutable
    BEFORE UPDATE OR DELETE ON durability_target_observations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_durability_mutation();

GRANT SELECT ON durability_policy_state TO ctower_svc;
GRANT INSERT, SELECT ON durability_subject_heads TO ctower_svc;
GRANT UPDATE (principal_id, client_command_id, updated_at)
    ON durability_subject_heads TO ctower_svc;
GRANT INSERT, SELECT ON durability_acknowledgements TO ctower_svc;
GRANT INSERT, SELECT ON durability_target_observations TO ctower_svc;
GRANT USAGE, SELECT ON SEQUENCE durability_acknowledgements_acceptance_position_seq
    TO ctower_svc;
