-- gh#381 Phase 1: replace the GitLab-shaped persistence path with the
-- provider-neutral connector progress, custody, observation, and receipt set.
CREATE TABLE connector_sync_progress (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    connector_registration_key text NOT NULL CHECK (
        connector_registration_key ~ '^[a-z][a-z0-9.-]{2,127}$'
    ),
    registration_revision_id uuid NOT NULL,
    revision_digest bytea NOT NULL CHECK (octet_length(revision_digest) = 32),
    cursor_token text NOT NULL CHECK (length(cursor_token) BETWEEN 1 AND 4096),
    project_event_cursor bigint NOT NULL CHECK (project_event_cursor >= 0),
    next_poll_at timestamptz NOT NULL,
    consecutive_failures integer NOT NULL DEFAULT 0 CHECK (
        consecutive_failures BETWEEN 0 AND 8
    ),
    claim_owner uuid,
    claim_fence bigint NOT NULL DEFAULT 0 CHECK (claim_fence >= 0),
    claim_expires_at timestamptz,
    claimed_at timestamptz,
    completed_at timestamptz,
    PRIMARY KEY (
        tenant_id, connector_registration_key, registration_revision_id
    ),
    FOREIGN KEY (registration_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    UNIQUE (tenant_id, connector_registration_key, revision_digest),
    CHECK (completed_at IS NULL OR claimed_at IS NULL OR completed_at >= claimed_at),
    CHECK ((claim_owner IS NULL) = (claim_expires_at IS NULL)),
    CHECK (claim_owner IS NULL OR claim_fence > 0)
);

CREATE TABLE connector_issue_links (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    connector_registration_key text NOT NULL CHECK (
        connector_registration_key ~ '^[a-z][a-z0-9.-]{2,127}$'
    ),
    source_registration_revision_id uuid NOT NULL,
    source_revision_digest bytea NOT NULL CHECK (octet_length(source_revision_digest) = 32),
    connector_kind text NOT NULL CHECK (
        connector_kind ~ '^[a-z][a-z0-9.-]{2,63}$'
    ),
    external_ref text NOT NULL CHECK (length(external_ref) BETWEEN 1 AND 256),
    ticket_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    display_url text NOT NULL CHECK (display_url ~ '^https://'),
    linked_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, connector_registration_key, external_ref),
    FOREIGN KEY (source_registration_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (thread_id, tenant_id)
        REFERENCES inbound_threads(thread_id, tenant_id),
    UNIQUE (tenant_id, ticket_id),
    UNIQUE (tenant_id, connector_registration_key, external_ref, ticket_id)
);

CREATE TABLE connector_issue_observations (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    connector_registration_key text NOT NULL,
    registration_revision_id uuid NOT NULL,
    connector_kind text NOT NULL CHECK (
        connector_kind ~ '^[a-z][a-z0-9.-]{2,63}$'
    ),
    external_ref text NOT NULL CHECK (length(external_ref) BETWEEN 1 AND 256),
    payload_digest bytea NOT NULL CHECK (octet_length(payload_digest) = 32),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    description text NOT NULL CHECK (length(description) <= 60000),
    source_labels text[] NOT NULL CHECK (cardinality(source_labels) <= 100),
    reporter_reference text NOT NULL CHECK (length(reporter_reference) BETWEEN 1 AND 256),
    reporter_display_name text NOT NULL CHECK (
        length(reporter_display_name) BETWEEN 1 AND 255
    ),
    external_state text NOT NULL CHECK (external_state IN ('opened', 'closed')),
    display_url text NOT NULL CHECK (display_url ~ '^https://'),
    source_updated_at timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (
        tenant_id, connector_registration_key, registration_revision_id,
        external_ref, payload_digest
    ),
    FOREIGN KEY (registration_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (tenant_id, connector_registration_key, external_ref)
        REFERENCES connector_issue_links (
            tenant_id, connector_registration_key, external_ref
        )
);

CREATE TABLE connector_close_deliveries (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    connector_registration_key text NOT NULL,
    registration_revision_id uuid NOT NULL,
    connector_kind text NOT NULL CHECK (
        connector_kind ~ '^[a-z][a-z0-9.-]{2,63}$'
    ),
    external_ref text NOT NULL CHECK (length(external_ref) BETWEEN 1 AND 256),
    ticket_id uuid NOT NULL,
    command_id uuid NOT NULL,
    marker_present boolean NOT NULL CHECK (marker_present),
    comment_created boolean NOT NULL,
    issue_closed boolean NOT NULL CHECK (issue_closed),
    delivered_at timestamptz NOT NULL,
    PRIMARY KEY (
        tenant_id, connector_registration_key, registration_revision_id, command_id
    ),
    FOREIGN KEY (registration_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (command_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (
        tenant_id, connector_registration_key, external_ref, ticket_id
    ) REFERENCES connector_issue_links (
        tenant_id, connector_registration_key, external_ref, ticket_id
    ),
    UNIQUE (tenant_id, command_id)
);

INSERT INTO connector_sync_progress (
    tenant_id, connector_registration_key, registration_revision_id,
    revision_digest, cursor_token, project_event_cursor, next_poll_at,
    consecutive_failures, claim_owner, claim_fence, claim_expires_at,
    claimed_at, completed_at
)
SELECT tenant_id, integration_key, component_revision_id, revision_digest,
    jsonb_build_object(
        'page', page,
        'schema', 'ctower.gitlab-cursor/v1',
        'updated_after', updated_after
    )::text,
    project_event_cursor, next_poll_at, consecutive_failures, claim_owner,
    claim_fence, claim_expires_at, claimed_at, completed_at
FROM integration_gitlab_sync_progress;

INSERT INTO connector_issue_links (
    tenant_id, connector_registration_key, source_registration_revision_id,
    source_revision_digest, connector_kind, external_ref, ticket_id, thread_id,
    display_url, linked_at
)
SELECT tenant_id, integration_key, source_component_revision_id,
    source_revision_digest, 'gitlab-issue',
    'gitlab:' || gitlab_project_id::text || ':' || issue_iid::text,
    ticket_id, thread_id, web_url, linked_at
FROM integration_gitlab_issue_links;

INSERT INTO connector_issue_observations (
    tenant_id, connector_registration_key, registration_revision_id,
    connector_kind, external_ref, payload_digest, title, description,
    source_labels, reporter_reference, reporter_display_name, external_state,
    display_url, source_updated_at, observed_at
)
SELECT tenant_id, integration_key, component_revision_id, 'gitlab-issue',
    'gitlab:' || gitlab_project_id::text || ':' || issue_iid::text,
    payload_digest, title, body, labels, '@' || reporter_username,
    reporter_name, issue_state, web_url, source_updated_at, observed_at
FROM integration_gitlab_issue_observations;

INSERT INTO connector_close_deliveries (
    tenant_id, connector_registration_key, registration_revision_id,
    connector_kind, external_ref, ticket_id, command_id, marker_present,
    comment_created, issue_closed, delivered_at
)
SELECT tenant_id, integration_key, component_revision_id, 'gitlab-issue',
    'gitlab:' || gitlab_project_id::text || ':' || issue_iid::text,
    ticket_id, event_id, true, comment_created, issue_closed, delivered_at
FROM integration_gitlab_close_deliveries;

DROP TABLE integration_gitlab_close_deliveries;
DROP TABLE integration_gitlab_issue_observations;
DROP TABLE integration_gitlab_issue_links;
DROP TABLE integration_gitlab_sync_progress;

CREATE INDEX connector_observations_latest
    ON connector_issue_observations (
        tenant_id, connector_registration_key, registration_revision_id,
        external_ref, source_updated_at DESC, observed_at DESC
    );

CREATE TRIGGER connector_issue_links_immutable
    BEFORE UPDATE OR DELETE ON connector_issue_links
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER connector_issue_observations_immutable
    BEFORE UPDATE OR DELETE ON connector_issue_observations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER connector_close_deliveries_immutable
    BEFORE UPDATE OR DELETE ON connector_close_deliveries
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON connector_sync_progress, connector_issue_links,
    connector_issue_observations, connector_close_deliveries
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON connector_sync_progress TO ctower_svc;
GRANT UPDATE (
    cursor_token, project_event_cursor, next_poll_at, consecutive_failures,
    claim_owner, claim_fence, claim_expires_at, claimed_at, completed_at
) ON connector_sync_progress TO ctower_svc;
GRANT SELECT, INSERT ON connector_issue_links, connector_issue_observations,
    connector_close_deliveries TO ctower_svc;
GRANT SELECT ON connector_sync_progress, connector_issue_links,
    connector_issue_observations, connector_close_deliveries TO ctower_projection;
