-- gh#346: one Catalog-revision-pinned GitLab Issue co-source with durable
-- bounded cursors, immutable issue/ticket custody links, source observations,
-- and replay-safe proof-gated close delivery receipts.
CREATE TABLE integration_gitlab_sync_progress (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    integration_key text NOT NULL CHECK (
        integration_key ~ '^[a-z][a-z0-9.-]{2,127}$'
    ),
    component_revision_id uuid NOT NULL,
    revision_digest bytea NOT NULL CHECK (octet_length(revision_digest) = 32),
    gitlab_project_id bigint NOT NULL CHECK (gitlab_project_id >= 1),
    updated_after timestamptz NOT NULL,
    page integer NOT NULL CHECK (page >= 1),
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
    PRIMARY KEY (tenant_id, integration_key, component_revision_id),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    UNIQUE (tenant_id, integration_key, revision_digest),
    CHECK (completed_at IS NULL OR claimed_at IS NULL OR completed_at >= claimed_at),
    CHECK ((claim_owner IS NULL) = (claim_expires_at IS NULL)),
    CHECK (claim_owner IS NULL OR claim_fence > 0)
);

CREATE TABLE integration_gitlab_issue_links (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    integration_key text NOT NULL CHECK (
        integration_key ~ '^[a-z][a-z0-9.-]{2,127}$'
    ),
    source_component_revision_id uuid NOT NULL,
    source_revision_digest bytea NOT NULL CHECK (octet_length(source_revision_digest) = 32),
    gitlab_project_id bigint NOT NULL CHECK (gitlab_project_id >= 1),
    issue_iid bigint NOT NULL CHECK (issue_iid >= 1),
    ticket_id uuid NOT NULL,
    thread_id uuid NOT NULL,
    web_url text NOT NULL CHECK (web_url ~ '^https://'),
    linked_at timestamptz NOT NULL,
    PRIMARY KEY (
        tenant_id, integration_key, gitlab_project_id, issue_iid
    ),
    FOREIGN KEY (source_component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (thread_id, tenant_id)
        REFERENCES inbound_threads(thread_id, tenant_id),
    UNIQUE (tenant_id, ticket_id),
    UNIQUE (
        tenant_id, integration_key, gitlab_project_id, issue_iid, ticket_id
    )
);

CREATE TABLE integration_gitlab_issue_observations (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    integration_key text NOT NULL,
    component_revision_id uuid NOT NULL,
    gitlab_project_id bigint NOT NULL,
    issue_iid bigint NOT NULL,
    payload_digest bytea NOT NULL CHECK (octet_length(payload_digest) = 32),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    body text NOT NULL CHECK (length(body) <= 60000),
    labels text[] NOT NULL CHECK (cardinality(labels) <= 100),
    reporter_username text NOT NULL CHECK (
        reporter_username ~ '^[A-Za-z0-9_.-]{1,255}$'
    ),
    reporter_name text NOT NULL CHECK (length(reporter_name) BETWEEN 1 AND 255),
    issue_state text NOT NULL CHECK (issue_state IN ('opened', 'closed')),
    web_url text NOT NULL CHECK (web_url ~ '^https://'),
    source_updated_at timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (
        tenant_id, integration_key, component_revision_id,
        gitlab_project_id, issue_iid, payload_digest
    ),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (
        tenant_id, integration_key, gitlab_project_id, issue_iid
    ) REFERENCES integration_gitlab_issue_links (
        tenant_id, integration_key, gitlab_project_id, issue_iid
    )
);

CREATE TABLE integration_gitlab_close_deliveries (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    integration_key text NOT NULL,
    component_revision_id uuid NOT NULL,
    gitlab_project_id bigint NOT NULL,
    issue_iid bigint NOT NULL,
    ticket_id uuid NOT NULL,
    event_id uuid NOT NULL,
    comment_created boolean NOT NULL,
    issue_closed boolean NOT NULL CHECK (issue_closed),
    delivered_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, integration_key, component_revision_id, event_id),
    FOREIGN KEY (component_revision_id, tenant_id)
        REFERENCES catalog_component_revisions(component_revision_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (
        tenant_id, integration_key, gitlab_project_id, issue_iid, ticket_id
    ) REFERENCES integration_gitlab_issue_links (
        tenant_id, integration_key, gitlab_project_id, issue_iid, ticket_id
    ),
    UNIQUE (tenant_id, event_id)
);

CREATE INDEX integration_gitlab_observations_latest
    ON integration_gitlab_issue_observations (
        tenant_id, integration_key, component_revision_id,
        gitlab_project_id, issue_iid, source_updated_at DESC, observed_at DESC
    );

CREATE TRIGGER integration_gitlab_issue_links_immutable
    BEFORE UPDATE OR DELETE ON integration_gitlab_issue_links
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER integration_gitlab_issue_observations_immutable
    BEFORE UPDATE OR DELETE ON integration_gitlab_issue_observations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER integration_gitlab_close_deliveries_immutable
    BEFORE UPDATE OR DELETE ON integration_gitlab_close_deliveries
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON integration_gitlab_sync_progress,
    integration_gitlab_issue_links, integration_gitlab_issue_observations,
    integration_gitlab_close_deliveries
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON integration_gitlab_sync_progress TO ctower_svc;
GRANT UPDATE (
    updated_after, page, project_event_cursor, next_poll_at,
    consecutive_failures, claim_owner, claim_fence, claim_expires_at,
    claimed_at, completed_at
) ON integration_gitlab_sync_progress TO ctower_svc;
GRANT SELECT, INSERT ON integration_gitlab_issue_links,
    integration_gitlab_issue_observations, integration_gitlab_close_deliveries
    TO ctower_svc;
GRANT SELECT ON integration_gitlab_sync_progress,
    integration_gitlab_issue_links, integration_gitlab_issue_observations,
    integration_gitlab_close_deliveries
    TO ctower_projection;
