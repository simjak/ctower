ALTER TABLE principals DROP CONSTRAINT principals_kind_check;
ALTER TABLE principals ADD CONSTRAINT principals_kind_check CHECK (kind IN (
    'bootstrap_installer', 'operator', 'commander', 'agent', 'reviewer', 'runner',
    'control_worker', 'migration_importer', 'fence_observer', 'viewer'
));

CREATE TABLE human_role_bindings (
    binding_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    oidc_issuer text NOT NULL CHECK (length(oidc_issuer) BETWEEN 1 AND 512),
    oidc_subject text NOT NULL CHECK (length(oidc_subject) BETWEEN 1 AND 255),
    role text NOT NULL CHECK (role IN ('operator', 'commander', 'viewer')),
    project_keys text[] NOT NULL DEFAULT '{}',
    granted_by uuid NOT NULL,
    granted_at timestamptz NOT NULL,
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (granted_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, oidc_issuer, oidc_subject),
    UNIQUE (binding_id, tenant_id)
);

CREATE TABLE human_role_binding_revocations (
    binding_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    revoked_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    revoked_at timestamptz NOT NULL,
    FOREIGN KEY (binding_id, tenant_id)
        REFERENCES human_role_bindings(binding_id, tenant_id),
    FOREIGN KEY (revoked_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE human_sessions (
    session_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    session_digest bytea NOT NULL UNIQUE CHECK (octet_length(session_digest) = 32),
    principal_id uuid NOT NULL,
    binding_id uuid NOT NULL,
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (binding_id, tenant_id)
        REFERENCES human_role_bindings(binding_id, tenant_id),
    UNIQUE (session_id, tenant_id)
);

CREATE TABLE human_session_revocations (
    session_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    revoked_at timestamptz NOT NULL,
    FOREIGN KEY (session_id, tenant_id) REFERENCES human_sessions(session_id, tenant_id)
);

CREATE TRIGGER human_role_bindings_immutable
    BEFORE UPDATE OR DELETE ON human_role_bindings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER human_role_binding_revocations_immutable
    BEFORE UPDATE OR DELETE ON human_role_binding_revocations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER human_sessions_immutable
    BEFORE UPDATE OR DELETE ON human_sessions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER human_session_revocations_immutable
    BEFORE UPDATE OR DELETE ON human_session_revocations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON human_role_bindings, human_role_binding_revocations,
    human_sessions, human_session_revocations
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON human_role_bindings, human_role_binding_revocations,
    human_sessions, human_session_revocations
    TO ctower_svc;
GRANT SELECT ON human_role_bindings, human_role_binding_revocations,
    human_sessions, human_session_revocations
    TO ctower_projection;
