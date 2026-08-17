-- T4: the per-harness credential pool's observation ledger.
--
-- One appended sweep of one harness profile's credential store, projected through a
-- strict named-field allowlist. AUTH != QUOTA != REACH, so every entry carries three
-- orthogonal states and no column collapses them: a capped account passes login, a dead
-- lineage may hold untouched quota, and an entry with both fine can still be unreachable
-- because the provider's CDN is challenging our egress. An entry is selectable only when
-- all three axes are clear, which is a derived read and never a stored verdict.
--
-- The table's shape is itself the projection allowlist. OAuth entries in a harness's own
-- auth.json carry access_token and refresh_token *adjacent to* the metadata being read, so
-- there is deliberately no column any credential value could land in: a credential is
-- representable here only as `secret_fingerprint`, and only as a fingerprint. Rows are
-- appended and never updated or deleted; the harness owns its auth state, ctower owns this
-- history, and neither writes the other's file.
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'runtime.dream_dispatch_consumed',
    'runtime.dream_lane_bound', 'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'ruling.recorded', 'estate.import_changed', 'company.record_appended',
    'pools.observation_recorded'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling', 'company_record',
        'pool_observation'
    )
);

ALTER TABLE durability_subject_heads
    DROP CONSTRAINT durability_subject_heads_subject_kind_check;
ALTER TABLE durability_subject_heads
    ADD CONSTRAINT durability_subject_heads_subject_kind_check CHECK (
        subject_kind IN (
            'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
            'inbound_thread', 'inbound_event', 'access', 'session',
            'attention_finding', 'attention_finding_disposition', 'inbox_thread',
            'knowledge_document', 'request', 'ruling', 'company_record',
            'pool_observation'
        )
    );

CREATE TABLE pool_observations (
    observation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    harness_key text NOT NULL CHECK (harness_key IN ('hermes', 'claude-code')),
    profile_key text NOT NULL CHECK (profile_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    observed_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    actor_principal_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (actor_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    UNIQUE (observation_id, tenant_id),
    UNIQUE (event_id)
);
CREATE INDEX pool_observations_latest
    ON pool_observations (tenant_id, harness_key, profile_key, observed_at DESC);

-- Quota is tracked per entry and carries that account's own clock: a pool holding two
-- exhausted entries and one near-full entry has three different reset times and is not
-- one word. `quota_reset_at IS NULL` under `quota_state = 'capped'` is the explicit
-- capped(reset_unknown) case, which is waiting with no predictable return, not availability.
CREATE TABLE pool_observation_entries (
    observation_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    entry_ordinal integer NOT NULL CHECK (entry_ordinal BETWEEN 0 AND 63),
    provider_key text NOT NULL CHECK (provider_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    subscription_identity text CHECK (length(subscription_identity) BETWEEN 3 AND 254),
    entry_label text CHECK (length(entry_label) BETWEEN 1 AND 128),
    registration_state text NOT NULL
        CHECK (registration_state IN ('enrolled', 'discovered')),
    auth_state text NOT NULL
        CHECK (auth_state IN ('healthy', 'lineage-dead', 'chain-burned')),
    quota_state text NOT NULL
        CHECK (quota_state IN ('available', 'capped', 'unfunded', 'unknown')),
    quota_reset_at timestamptz,
    reach_state text NOT NULL CHECK (reach_state IN ('ok', 'edge-challenged', 'unknown')),
    request_count bigint NOT NULL CHECK (request_count >= 0),
    last_status_observed text CHECK (last_status_observed ~ '^[a-z][a-z0-9._-]{0,63}$'),
    secret_fingerprint text CHECK (secret_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (observation_id, entry_ordinal),
    CONSTRAINT pool_observation_entries_reset_requires_cap
        CHECK (quota_reset_at IS NULL OR quota_state = 'capped'),
    FOREIGN KEY (observation_id, tenant_id)
        REFERENCES pool_observations(observation_id, tenant_id)
);
CREATE INDEX pool_observation_entries_identity
    ON pool_observation_entries (tenant_id, provider_key, subscription_identity);

CREATE TRIGGER pool_observations_immutable
    BEFORE UPDATE OR DELETE ON pool_observations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER pool_observation_entries_immutable
    BEFORE UPDATE OR DELETE ON pool_observation_entries
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON pool_observations, pool_observation_entries
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON pool_observations, pool_observation_entries TO ctower_svc;
GRANT SELECT ON pool_observations, pool_observation_entries TO ctower_projection;
