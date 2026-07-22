ALTER TABLE durability_acknowledgements
    ADD CONSTRAINT durability_acknowledgements_identity_position_unique
    UNIQUE (tenant_id, principal_id, client_command_id, acceptance_position);

CREATE TABLE durability_acceptance_finalizations (
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
    finalized_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, principal_id, client_command_id),
    UNIQUE (acceptance_position),
    FOREIGN KEY (tenant_id, principal_id, client_command_id, acceptance_position)
        REFERENCES durability_acknowledgements (
            tenant_id, principal_id, client_command_id, acceptance_position
        )
);

CREATE TRIGGER durability_acceptance_finalizations_immutable
    BEFORE UPDATE OR DELETE ON durability_acceptance_finalizations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_durability_mutation();

GRANT INSERT, SELECT ON durability_acceptance_finalizations TO ctower_svc;

CREATE FUNCTION durability_primary_live_evidence()
RETURNS TABLE (
    matching_sender_count bigint,
    application_name text,
    replication_state text,
    sync_state text,
    replay_lsn pg_lsn,
    primary_flush_lsn pg_lsn,
    system_identifier numeric,
    timeline_id integer,
    synchronous_standby_names text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
    SELECT
        count(*) AS matching_sender_count,
        min(sender.application_name) AS application_name,
        min(sender.state) AS replication_state,
        min(sender.sync_state) AS sync_state,
        min(sender.replay_lsn::text)::pg_lsn AS replay_lsn,
        pg_current_wal_flush_lsn() AS primary_flush_lsn,
        (pg_control_system()).system_identifier,
        (pg_control_checkpoint()).timeline_id,
        current_setting('synchronous_standby_names') AS synchronous_standby_names
    FROM pg_stat_replication AS sender
    WHERE sender.application_name = 'ctower_i1_ack'
$$;

CREATE FUNCTION durability_standby_live_evidence()
RETURNS TABLE (
    matching_receiver_count bigint,
    receiver_status text,
    cluster_name text,
    in_recovery boolean,
    replay_paused boolean,
    replay_lsn pg_lsn,
    system_identifier numeric,
    timeline_id integer
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
    SELECT
        count(*) AS matching_receiver_count,
        min(receiver.status) AS receiver_status,
        current_setting('cluster_name') AS cluster_name,
        pg_is_in_recovery() AS in_recovery,
        pg_is_wal_replay_paused() AS replay_paused,
        pg_last_wal_replay_lsn() AS replay_lsn,
        (pg_control_system()).system_identifier,
        (pg_control_checkpoint()).timeline_id
    FROM pg_stat_wal_receiver AS receiver
$$;

ALTER FUNCTION durability_primary_live_evidence() OWNER TO ctower_durability_probe;
ALTER FUNCTION durability_standby_live_evidence() OWNER TO ctower_durability_probe;
REVOKE ALL ON FUNCTION durability_primary_live_evidence() FROM PUBLIC;
REVOKE ALL ON FUNCTION durability_standby_live_evidence() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION durability_primary_live_evidence() TO ctower_svc;
GRANT EXECUTE ON FUNCTION durability_standby_live_evidence() TO ctower_svc;
