ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access'
    )
);
ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN (
            'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
            'inbound_thread', 'inbound_event', 'access'
        )
    );

ALTER TABLE tickets
    ADD COLUMN project_key text NOT NULL DEFAULT 'ctower'
        CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$');

CREATE TABLE project_seats (
    principal_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    seat_key text NOT NULL CHECK (seat_key ~ '^[a-z][a-z0-9._-]{1,95}$'),
    granted_by uuid NOT NULL,
    granted_at timestamptz NOT NULL,
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (granted_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, project_key, seat_key),
    UNIQUE (principal_id, tenant_id)
);

WITH ranked_commanders AS (
    SELECT commander.principal_id, commander.tenant_id, commander.created_at,
        operator.principal_id AS operator_id,
        row_number() OVER (
            PARTITION BY commander.tenant_id
            ORDER BY commander.created_at, commander.principal_id
        ) AS ordinal
    FROM principals AS commander
    JOIN LATERAL (
        SELECT principal_id
        FROM principals
        WHERE tenant_id = commander.tenant_id AND kind = 'operator'
        ORDER BY created_at, principal_id
        LIMIT 1
    ) AS operator ON true
    WHERE commander.kind = 'commander'
)
INSERT INTO project_seats (
    principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
)
SELECT principal_id, tenant_id, 'ctower',
    CASE WHEN ordinal = 1 THEN 'ctower-commander'
         ELSE 'ctower-commander-' || left(replace(principal_id::text, '-', ''), 12)
    END,
    operator_id, created_at
FROM ranked_commanders;

CREATE TABLE seat_credential_issuances (
    credential_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    principal_id uuid NOT NULL,
    credential_ref text NOT NULL CHECK (length(credential_ref) BETWEEN 1 AND 512),
    event_id uuid NOT NULL,
    issued_by uuid NOT NULL,
    issued_at timestamptz NOT NULL,
    FOREIGN KEY (credential_id) REFERENCES principal_credentials(credential_id),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES project_seats(principal_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (issued_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (event_id),
    UNIQUE (credential_id, tenant_id)
);

CREATE TABLE seat_credential_scopes (
    credential_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    scope text NOT NULL CHECK (scope IN ('capture', 'transition', 'evidence')),
    PRIMARY KEY (credential_id, scope),
    FOREIGN KEY (credential_id, tenant_id)
        REFERENCES seat_credential_issuances(credential_id, tenant_id)
);

CREATE TABLE seat_credential_revocations (
    credential_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    event_id uuid NOT NULL,
    revoked_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    revoked_at timestamptz NOT NULL,
    FOREIGN KEY (credential_id, tenant_id)
        REFERENCES seat_credential_issuances(credential_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (revoked_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (event_id)
);

CREATE TRIGGER project_seats_immutable
    BEFORE UPDATE OR DELETE ON project_seats
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER seat_credential_issuances_immutable
    BEFORE UPDATE OR DELETE ON seat_credential_issuances
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER seat_credential_scopes_immutable
    BEFORE UPDATE OR DELETE ON seat_credential_scopes
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER seat_credential_revocations_immutable
    BEFORE UPDATE OR DELETE ON seat_credential_revocations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON project_seats, seat_credential_issuances,
    seat_credential_scopes, seat_credential_revocations
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON project_seats, seat_credential_issuances,
    seat_credential_scopes, seat_credential_revocations
    TO ctower_svc;
GRANT SELECT ON project_seats, seat_credential_issuances,
    seat_credential_scopes, seat_credential_revocations
    TO ctower_projection;
