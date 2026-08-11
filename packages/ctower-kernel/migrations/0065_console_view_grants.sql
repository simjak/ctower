-- Console Phase 1 follows the fleet-beat migrations accepted on current main.
ALTER TABLE human_sessions
    ADD COLUMN csrf_digest bytea CHECK (
        csrf_digest IS NULL OR octet_length(csrf_digest) = 32
    );

CREATE TABLE console_session_allows (
    allowance_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    seat_principal_id uuid NOT NULL,
    crew_name text NOT NULL CHECK (crew_name ~ '^[a-z][a-z0-9._-]{1,95}$'),
    assignment_ticket_id uuid NOT NULL,
    assignment_kind text NOT NULL CHECK (length(assignment_kind) BETWEEN 1 AND 128),
    assignment_interval_sequence integer NOT NULL CHECK (assignment_interval_sequence >= 1),
    recorded_work_session_id uuid NOT NULL,
    runtime_attempt_id uuid NOT NULL,
    runner_id text NOT NULL CHECK (length(runner_id) BETWEEN 1 AND 128),
    runner_epoch bigint NOT NULL CHECK (runner_epoch >= 1),
    adapter_key text NOT NULL CHECK (adapter_key = 'tmux-v1'),
    opaque_backend_ref text NOT NULL CHECK (length(opaque_backend_ref) BETWEEN 1 AND 256),
    backend_incarnation text NOT NULL CHECK (length(backend_incarnation) BETWEEN 1 AND 128),
    sensitivity_class text NOT NULL CHECK (sensitivity_class = 'restricted'),
    loop_kind text NOT NULL CHECK (loop_kind = 'standard'),
    allowed_by uuid NOT NULL,
    allowed_at timestamptz NOT NULL,
    FOREIGN KEY (seat_principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (allowed_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (
        assignment_ticket_id, assignment_kind, assignment_interval_sequence
    ) REFERENCES assignment_intervals(ticket_id, assignment_kind, interval_sequence),
    FOREIGN KEY (assignment_ticket_id, tenant_id)
        REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (recorded_work_session_id, tenant_id)
        REFERENCES ticket_work_sessions(session_id, tenant_id),
    UNIQUE (recorded_work_session_id),
    UNIQUE (allowance_id, tenant_id)
);

CREATE TABLE console_session_revocations (
    allowance_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    revoked_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    revoked_at timestamptz NOT NULL,
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id),
    FOREIGN KEY (revoked_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE console_global_kill_switch_facts (
    fact_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    enabled boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (fact_id, tenant_id)
);
CREATE INDEX console_global_kill_switch_latest
    ON console_global_kill_switch_facts (tenant_id, recorded_at DESC, fact_id DESC);

CREATE TABLE console_view_denials (
    denial_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_principal_id uuid NOT NULL,
    allowance_id uuid,
    code text NOT NULL CHECK (length(code) BETWEEN 1 AND 128),
    denied_at timestamptz NOT NULL,
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id)
);
CREATE INDEX console_view_denials_actor_window
    ON console_view_denials (tenant_id, actor_principal_id, denied_at DESC);

CREATE TABLE console_view_suspensions (
    suspension_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_principal_id uuid NOT NULL,
    denial_count integer NOT NULL CHECK (denial_count >= 3),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    suspended_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    CHECK (expires_at > suspended_at)
);
CREATE INDEX console_view_suspensions_actor_expiry
    ON console_view_suspensions (tenant_id, actor_principal_id, expires_at DESC);

CREATE TABLE console_view_grants (
    grant_id uuid PRIMARY KEY,
    grant_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    actor_principal_id uuid NOT NULL,
    human_binding_id uuid NOT NULL,
    human_session_id uuid NOT NULL,
    allowance_id uuid NOT NULL,
    policy_revision text NOT NULL CHECK (policy_revision ~ '^[a-z][a-z0-9._-]{2,127}$'),
    issuer text NOT NULL CHECK (issuer = 'ctower-control-plane'),
    not_before timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    maximum_uses integer NOT NULL CHECK (maximum_uses = 1),
    nonce uuid NOT NULL UNIQUE,
    continuous_view_started_at timestamptz NOT NULL,
    renewed_from_grant_id uuid REFERENCES console_view_grants(grant_id),
    granted_at timestamptz NOT NULL,
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (human_binding_id, tenant_id)
        REFERENCES human_role_bindings(binding_id, tenant_id),
    FOREIGN KEY (human_session_id, tenant_id)
        REFERENCES human_sessions(session_id, tenant_id),
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id),
    CHECK (not_before = granted_at),
    CHECK (expires_at > not_before AND expires_at <= not_before + interval '5 minutes'),
    CHECK (expires_at <= continuous_view_started_at + interval '30 minutes'),
    UNIQUE (grant_id, tenant_id)
);
CREATE INDEX console_view_grants_actor_session
    ON console_view_grants (
        tenant_id, actor_principal_id, human_session_id, allowance_id, grant_sequence DESC
    );

CREATE TABLE console_view_grant_revocations (
    grant_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    revoked_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    revoked_at timestamptz NOT NULL,
    FOREIGN KEY (grant_id, tenant_id) REFERENCES console_view_grants(grant_id, tenant_id),
    FOREIGN KEY (revoked_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE console_stream_opens (
    stream_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    grant_id uuid NOT NULL UNIQUE,
    actor_principal_id uuid NOT NULL,
    human_session_id uuid NOT NULL,
    allowance_id uuid NOT NULL,
    opened_at timestamptz NOT NULL,
    FOREIGN KEY (grant_id, tenant_id) REFERENCES console_view_grants(grant_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (human_session_id, tenant_id)
        REFERENCES human_sessions(session_id, tenant_id),
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id),
    UNIQUE (stream_id, tenant_id)
);
CREATE INDEX console_stream_opens_actor_session
    ON console_stream_opens (tenant_id, actor_principal_id, human_session_id, opened_at DESC);

CREATE TABLE console_stream_closes (
    stream_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    code text NOT NULL CHECK (code IN (
        'expired', 'revoked', 'fenced', 'rate_limited', 'slow_consumer',
        'reauthentication_required', 'globally_disabled', 'output_unavailable',
        'client_disconnected'
    )),
    gap_required boolean NOT NULL,
    closed_at timestamptz NOT NULL,
    FOREIGN KEY (stream_id, tenant_id) REFERENCES console_stream_opens(stream_id, tenant_id)
);

CREATE SEQUENCE console_source_positions_sequence;

CREATE TABLE console_output_objects (
    cursor bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_position bigint NOT NULL DEFAULT nextval('console_source_positions_sequence') UNIQUE,
    object_id uuid NOT NULL UNIQUE,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    allowance_id uuid NOT NULL,
    source_cursor bigint NOT NULL CHECK (source_cursor >= 0),
    source_generation bigint NOT NULL CHECK (source_generation >= 1),
    ciphertext bytea NOT NULL,
    content_nonce bytea NOT NULL CHECK (octet_length(content_nonce) = 12),
    wrapped_data_key bytea NOT NULL,
    wrapping_nonce bytea NOT NULL CHECK (octet_length(wrapping_nonce) = 12),
    wrapping_key_reference text NOT NULL CHECK (length(wrapping_key_reference) BETWEEN 1 AND 256),
    data_key_reference uuid NOT NULL UNIQUE,
    object_sha256 bytea NOT NULL CHECK (octet_length(object_sha256) = 32),
    decoded_bytes integer NOT NULL CHECK (decoded_bytes BETWEEN 1 AND 16384),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id),
    UNIQUE (allowance_id, source_generation, source_cursor),
    UNIQUE (cursor, tenant_id)
);

CREATE TABLE console_output_access_facts (
    access_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    object_id uuid NOT NULL REFERENCES console_output_objects(object_id),
    grant_id uuid NOT NULL,
    stream_id uuid NOT NULL,
    access_kind text NOT NULL CHECK (access_kind IN ('open', 'reconnect', 'replay', 'forensic')),
    outcome text NOT NULL CHECK (outcome = 'authorized'),
    accessed_by uuid NOT NULL,
    accessed_at timestamptz NOT NULL,
    FOREIGN KEY (grant_id, tenant_id) REFERENCES console_view_grants(grant_id, tenant_id),
    FOREIGN KEY (stream_id, tenant_id) REFERENCES console_stream_opens(stream_id, tenant_id),
    FOREIGN KEY (accessed_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE console_output_recovery_facts (
    access_id uuid PRIMARY KEY REFERENCES console_output_access_facts(access_id),
    recovered_at timestamptz NOT NULL
);

CREATE TABLE console_output_gap_facts (
    gap_id uuid PRIMARY KEY,
    cursor bigint NOT NULL DEFAULT nextval('console_output_objects_cursor_seq') UNIQUE,
    source_position bigint NOT NULL DEFAULT nextval('console_source_positions_sequence') UNIQUE,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    allowance_id uuid NOT NULL,
    source_cursor bigint NOT NULL CHECK (source_cursor >= 0),
    source_generation bigint NOT NULL CHECK (source_generation >= 1),
    advances_source_position boolean NOT NULL,
    reason text NOT NULL CHECK (reason IN (
        'cursor_unavailable', 'source_truncated', 'unprovable_range',
        'slow_consumer', 'rate_limited'
    )),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id)
);

CREATE FUNCTION recover_console_output_object(p_access_id uuid, p_recovered_at timestamptz)
RETURNS SETOF console_output_objects
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
    INSERT INTO public.console_output_recovery_facts (access_id, recovered_at)
    SELECT access.access_id, p_recovered_at
    FROM public.console_output_access_facts AS access
    WHERE access.access_id = p_access_id AND access.outcome = 'authorized';
    IF NOT FOUND THEN
        RETURN;
    END IF;
    RETURN QUERY SELECT object.*
    FROM public.console_output_objects AS object
    JOIN public.console_output_access_facts AS access
      ON access.tenant_id = object.tenant_id
     AND access.object_id = object.object_id
    WHERE access.access_id = p_access_id;
END
$function$;
ALTER FUNCTION recover_console_output_object(uuid, timestamptz)
    OWNER TO console_output_reader;
REVOKE ALL ON FUNCTION recover_console_output_object(uuid, timestamptz)
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT EXECUTE ON FUNCTION recover_console_output_object(uuid, timestamptz) TO ctower_svc;

CREATE TABLE console_adapter_observation_facts (
    observation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    allowance_id uuid NOT NULL,
    project_key text NOT NULL,
    runtime_attempt_id uuid NOT NULL,
    runner_id text NOT NULL,
    runner_epoch bigint NOT NULL CHECK (runner_epoch >= 1),
    backend_incarnation text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('matched', 'fenced', 'unavailable')),
    observed_at timestamptz NOT NULL,
    FOREIGN KEY (allowance_id, tenant_id)
        REFERENCES console_session_allows(allowance_id, tenant_id)
);

CREATE FUNCTION lock_console_authority_anchors(
    p_tenant_id uuid,
    p_actor_principal_id uuid,
    p_human_binding_id uuid,
    p_human_session_id uuid,
    p_allowance_id uuid
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    v_target_principal_id uuid;
    v_assignment_ticket_id uuid;
    v_assignment_kind text;
    v_assignment_interval_sequence integer;
    v_recorded_work_session_id uuid;
BEGIN
    PERFORM tenant_id FROM public.tenants
    WHERE tenant_id = p_tenant_id FOR UPDATE;

    SELECT allowance.seat_principal_id,
        allowance.assignment_ticket_id,
        allowance.assignment_kind,
        allowance.assignment_interval_sequence,
        allowance.recorded_work_session_id
    INTO v_target_principal_id, v_assignment_ticket_id, v_assignment_kind,
        v_assignment_interval_sequence, v_recorded_work_session_id
    FROM public.console_session_allows AS allowance
    WHERE allowance.allowance_id = p_allowance_id
      AND allowance.tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    PERFORM principal_id FROM public.principals
    WHERE tenant_id = p_tenant_id
      AND principal_id IN (p_actor_principal_id, v_target_principal_id)
    ORDER BY principal_id FOR UPDATE;
    PERFORM binding_id FROM public.human_role_bindings
    WHERE binding_id = p_human_binding_id AND tenant_id = p_tenant_id FOR UPDATE;
    PERFORM session_id FROM public.human_sessions
    WHERE session_id = p_human_session_id AND tenant_id = p_tenant_id FOR UPDATE;
    PERFORM ticket_id FROM public.assignment_intervals
    WHERE ticket_id = v_assignment_ticket_id
      AND assignment_kind = v_assignment_kind
      AND interval_sequence = v_assignment_interval_sequence
    FOR UPDATE;
    PERFORM session_id FROM public.ticket_work_sessions
    WHERE session_id = v_recorded_work_session_id AND tenant_id = p_tenant_id FOR UPDATE;
    PERFORM allowance_id FROM public.console_session_allows
    WHERE allowance_id = p_allowance_id AND tenant_id = p_tenant_id FOR UPDATE;
    RETURN true;
END
$function$;
REVOKE ALL ON FUNCTION lock_console_authority_anchors(uuid, uuid, uuid, uuid, uuid)
    FROM PUBLIC, ctower_svc, ctower_projection, console_output_reader;
GRANT EXECUTE ON FUNCTION lock_console_authority_anchors(uuid, uuid, uuid, uuid, uuid)
    TO ctower_svc;

CREATE TRIGGER console_session_allows_immutable
    BEFORE UPDATE OR DELETE ON console_session_allows
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_session_revocations_immutable
    BEFORE UPDATE OR DELETE ON console_session_revocations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_global_kill_switch_facts_immutable
    BEFORE UPDATE OR DELETE ON console_global_kill_switch_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_view_denials_immutable
    BEFORE UPDATE OR DELETE ON console_view_denials
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_view_suspensions_immutable
    BEFORE UPDATE OR DELETE ON console_view_suspensions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_view_grants_immutable
    BEFORE UPDATE OR DELETE ON console_view_grants
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_view_grant_revocations_immutable
    BEFORE UPDATE OR DELETE ON console_view_grant_revocations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_stream_opens_immutable
    BEFORE UPDATE OR DELETE ON console_stream_opens
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_stream_closes_immutable
    BEFORE UPDATE OR DELETE ON console_stream_closes
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_output_objects_immutable
    BEFORE UPDATE OR DELETE ON console_output_objects
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_output_access_facts_immutable
    BEFORE UPDATE OR DELETE ON console_output_access_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_output_recovery_facts_immutable
    BEFORE UPDATE OR DELETE ON console_output_recovery_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_output_gap_facts_immutable
    BEFORE UPDATE OR DELETE ON console_output_gap_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER console_adapter_observation_facts_immutable
    BEFORE UPDATE OR DELETE ON console_adapter_observation_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON console_session_allows, console_session_revocations,
    console_global_kill_switch_facts, console_view_denials, console_view_suspensions,
    console_view_grants,
    console_view_grant_revocations, console_stream_opens, console_stream_closes,
    console_output_objects, console_output_access_facts, console_output_recovery_facts,
    console_output_gap_facts,
    console_adapter_observation_facts
    FROM PUBLIC, ctower_svc, ctower_projection, console_output_reader;
REVOKE ALL ON SEQUENCE console_output_objects_cursor_seq
    FROM PUBLIC, ctower_svc, ctower_projection, console_output_reader;
REVOKE ALL ON SEQUENCE console_source_positions_sequence
    FROM PUBLIC, ctower_svc, ctower_projection, console_output_reader;
REVOKE ALL ON SEQUENCE console_view_grants_grant_sequence_seq
    FROM PUBLIC, ctower_svc, ctower_projection, console_output_reader;

GRANT INSERT, SELECT ON console_session_allows, console_session_revocations,
    console_global_kill_switch_facts, console_view_denials, console_view_grants,
    console_view_suspensions,
    console_view_grant_revocations, console_stream_opens, console_stream_closes,
    console_output_access_facts, console_output_gap_facts, console_adapter_observation_facts
    TO ctower_svc;
GRANT INSERT ON console_output_objects TO ctower_svc;
GRANT SELECT (
    cursor, source_position, object_id, tenant_id, allowance_id,
    source_cursor, source_generation,
    object_sha256, decoded_bytes, recorded_at
) ON console_output_objects TO ctower_svc;
GRANT USAGE, SELECT ON SEQUENCE console_output_objects_cursor_seq TO ctower_svc;
GRANT USAGE, SELECT ON SEQUENCE console_source_positions_sequence TO ctower_svc;
GRANT USAGE, SELECT ON SEQUENCE console_view_grants_grant_sequence_seq TO ctower_svc;
GRANT SELECT ON console_output_objects, console_output_access_facts TO console_output_reader;
GRANT INSERT ON console_output_recovery_facts TO console_output_reader;
