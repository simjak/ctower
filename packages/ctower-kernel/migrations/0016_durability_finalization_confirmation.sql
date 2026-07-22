ALTER TABLE durability_acknowledgements
    ADD CONSTRAINT durability_acknowledgements_complete_receipt_unique
    UNIQUE (
        tenant_id, principal_id, client_command_id, request_sha256, command_root,
        acceptance_position, policy_ref, standby_application_name, standby_identity,
        standby_system_identifier, standby_timeline_id, standby_replay_lsn
    );

ALTER TABLE durability_acceptance_finalizations
    ADD CONSTRAINT durability_finalizations_complete_receipt_unique
    UNIQUE (
        tenant_id, principal_id, client_command_id, request_sha256, command_root,
        acceptance_position, policy_ref, standby_application_name, standby_identity,
        standby_system_identifier, standby_timeline_id, standby_replay_lsn
    ),
    ADD CONSTRAINT durability_finalizations_complete_acknowledgement
    FOREIGN KEY (
        tenant_id, principal_id, client_command_id, request_sha256, command_root,
        acceptance_position, policy_ref, standby_application_name, standby_identity,
        standby_system_identifier, standby_timeline_id, standby_replay_lsn
    ) REFERENCES durability_acknowledgements (
        tenant_id, principal_id, client_command_id, request_sha256, command_root,
        acceptance_position, policy_ref, standby_application_name, standby_identity,
        standby_system_identifier, standby_timeline_id, standby_replay_lsn
    );

CREATE TABLE durability_acceptance_confirmations (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    client_command_id uuid NOT NULL,
    request_sha256 bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    command_root bytea NOT NULL CHECK (octet_length(command_root) = 32),
    acceptance_position bigint NOT NULL CHECK (acceptance_position > 0),
    policy_ref text NOT NULL CHECK (policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    standby_application_name text NOT NULL CHECK (standby_application_name = 'ctower_i1_ack'),
    standby_identity text NOT NULL CHECK (length(standby_identity) BETWEEN 1 AND 128),
    standby_system_identifier numeric(20, 0) NOT NULL CHECK (standby_system_identifier > 0),
    standby_timeline_id integer NOT NULL CHECK (standby_timeline_id >= 1),
    standby_replay_lsn pg_lsn NOT NULL,
    confirmed_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, principal_id, client_command_id),
    FOREIGN KEY (
        tenant_id, principal_id, client_command_id, request_sha256, command_root,
        acceptance_position, policy_ref, standby_application_name, standby_identity,
        standby_system_identifier, standby_timeline_id, standby_replay_lsn
    ) REFERENCES durability_acceptance_finalizations (
        tenant_id, principal_id, client_command_id, request_sha256, command_root,
        acceptance_position, policy_ref, standby_application_name, standby_identity,
        standby_system_identifier, standby_timeline_id, standby_replay_lsn
    )
);

CREATE TRIGGER durability_acceptance_confirmations_immutable
    BEFORE UPDATE OR DELETE ON durability_acceptance_confirmations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_durability_mutation();

GRANT INSERT, SELECT ON durability_acceptance_confirmations TO ctower_svc;
