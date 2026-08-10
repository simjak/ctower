-- gh#400: first-class Request authority. Requests are independent from Tickets;
-- one atomic command records transport provenance, the Request, its initial facts,
-- the exact command result, audit event, and outbox intent.
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
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request'
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
            'knowledge_document', 'request'
        )
    );

ALTER TABLE inbound_events DROP CONSTRAINT inbound_events_initial_intent_check;
ALTER TABLE inbound_events ADD CONSTRAINT inbound_events_initial_intent_check CHECK (
    initial_intent IN ('discussion', 'create_ticket', 'link_ticket', 'create_request')
);
ALTER TABLE inbound_events DROP CONSTRAINT inbound_events_initial_outcome_check;
ALTER TABLE inbound_events ADD CONSTRAINT inbound_events_initial_outcome_check CHECK (
    initial_outcome IN (
        'discussion', 'ticket_created', 'ticket_linked', 'quarantined', 'request_created'
    )
);

CREATE TABLE request_number_allocators (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id),
    last_number bigint NOT NULL CHECK (last_number >= 0),
    advanced_at timestamptz NOT NULL
);

CREATE TABLE requests (
    request_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    request_number bigint NOT NULL CHECK (request_number > 0),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 65536),
    content_digest bytea NOT NULL CHECK (octet_length(content_digest) = 32),
    source_kind text NOT NULL CHECK (length(source_kind) BETWEEN 1 AND 64),
    source_ref text NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
    inbound_event_id uuid NOT NULL,
    submitted_by uuid NOT NULL,
    capture_command_id uuid NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (inbound_event_id, tenant_id)
        REFERENCES inbound_events(inbound_event_id, tenant_id),
    FOREIGN KEY (submitted_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (request_id, tenant_id),
    UNIQUE (tenant_id, request_number),
    UNIQUE (tenant_id, source_kind, source_ref),
    UNIQUE (inbound_event_id),
    UNIQUE (tenant_id, submitted_by, capture_command_id)
);

CREATE TABLE request_owner_facts (
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    owner_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, sequence),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (owner_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_priority_facts (
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    priority text NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    is_default boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, sequence),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_triage_facts (
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    disposition text NOT NULL CHECK (
        disposition IN ('UNTRIAGED', 'ACCEPTED', 'DUPLICATE', 'REJECTED')
    ),
    reason text,
    canonical_request_id uuid,
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, sequence),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (canonical_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    CHECK (
        (disposition IN ('UNTRIAGED', 'ACCEPTED') AND reason IS NULL
            AND canonical_request_id IS NULL)
        OR (disposition = 'REJECTED' AND length(reason) BETWEEN 1 AND 500
            AND canonical_request_id IS NULL)
        OR (disposition = 'DUPLICATE' AND length(reason) BETWEEN 1 AND 500
            AND canonical_request_id IS NOT NULL AND canonical_request_id <> request_id)
    )
);

CREATE TABLE request_ticket_relation_facts (
    relation_fact_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    request_version integer NOT NULL CHECK (request_version >= 2),
    ticket_id uuid NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('required', 'optional')),
    active boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);
CREATE INDEX request_ticket_relation_latest
    ON request_ticket_relation_facts (tenant_id, request_id, ticket_id, request_version DESC);

-- Machine-owned current-holder projection. The primary key is the database
-- chokepoint for the invariant that one fulfillment Ticket has at most one
-- current Request holder; callers can append facts but cannot write this table.
CREATE TABLE request_ticket_holders (
    tenant_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    request_id uuid NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('required', 'optional')),
    relation_fact_id uuid NOT NULL REFERENCES request_ticket_relation_facts(relation_fact_id),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, ticket_id),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id)
);

CREATE FUNCTION project_request_ticket_holder() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    affected integer;
BEGIN
    IF NEW.active THEN
        INSERT INTO public.request_ticket_holders (
            tenant_id, ticket_id, request_id, purpose, relation_fact_id, recorded_at
        ) VALUES (
            NEW.tenant_id, NEW.ticket_id, NEW.request_id, NEW.purpose,
            NEW.relation_fact_id, NEW.recorded_at
        )
        ON CONFLICT (tenant_id, ticket_id) DO UPDATE
        SET purpose = EXCLUDED.purpose,
            relation_fact_id = EXCLUDED.relation_fact_id,
            recorded_at = EXCLUDED.recorded_at
        WHERE public.request_ticket_holders.request_id = EXCLUDED.request_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN
            RAISE unique_violation
                USING MESSAGE = 'fulfillment Ticket already has a current Request holder';
        END IF;
    ELSE
        DELETE FROM public.request_ticket_holders
        WHERE tenant_id = NEW.tenant_id
          AND ticket_id = NEW.ticket_id
          AND request_id = NEW.request_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN
            RAISE check_violation
                USING MESSAGE = 'fulfillment Ticket is not held by the releasing Request';
        END IF;
    END IF;
    RETURN NEW;
END
$$;
REVOKE ALL ON FUNCTION project_request_ticket_holder() FROM PUBLIC;
CREATE TRIGGER request_ticket_relation_holder_projection
    AFTER INSERT ON request_ticket_relation_facts
    FOR EACH ROW EXECUTE FUNCTION project_request_ticket_holder();

CREATE TABLE request_blocker_facts (
    blocker_fact_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    request_version integer NOT NULL CHECK (request_version >= 1),
    blocker_key text NOT NULL CHECK (length(blocker_key) BETWEEN 1 AND 256),
    active boolean NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);
CREATE INDEX request_blocker_latest
    ON request_blocker_facts (tenant_id, request_id, blocker_key, request_version DESC);

CREATE TABLE request_closure_evaluations (
    evaluation_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    request_version integer NOT NULL CHECK (request_version >= 1),
    outcome text NOT NULL CHECK (outcome IN ('open', 'done')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    dependency_digest bytea NOT NULL CHECK (octet_length(dependency_digest) = 32),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_attention_facts (
    attention_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    kind text NOT NULL CHECK (
        kind IN ('request_triage_required', 'request_execution_link_required',
                 'request_import_attention')
    ),
    active boolean NOT NULL,
    owner_id uuid NOT NULL,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (owner_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_import_manifests (
    manifest_digest bytea PRIMARY KEY CHECK (octet_length(manifest_digest) = 32),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    archive_ref text NOT NULL CHECK (length(archive_ref) BETWEEN 1 AND 512),
    ledger_digest bytea NOT NULL CHECK (octet_length(ledger_digest) = 32),
    rows_digest bytea NOT NULL CHECK (octet_length(rows_digest) = 32),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    maximum_request_number bigint NOT NULL CHECK (maximum_request_number >= 0),
    project_counts jsonb NOT NULL CHECK (jsonb_typeof(project_counts) = 'object'),
    owner_mapping_digest bytea NOT NULL CHECK (octet_length(owner_mapping_digest) = 32),
    target_authority_digest bytea NOT NULL CHECK (octet_length(target_authority_digest) = 32),
    observed_file_size bigint NOT NULL CHECK (observed_file_size >= 0),
    manifest_artifact jsonb NOT NULL CHECK (jsonb_typeof(manifest_artifact) = 'object'),
    public_key_digest bytea NOT NULL CHECK (octet_length(public_key_digest) = 32),
    fence_digest bytea NOT NULL CHECK (octet_length(fence_digest) = 32),
    sealed_at timestamptz NOT NULL,
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_cutover_epoch_facts (
    epoch_fact_id uuid PRIMARY KEY,
    manifest_digest bytea NOT NULL REFERENCES request_import_manifests(manifest_digest),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    sequence integer NOT NULL CHECK (sequence >= 1),
    state text NOT NULL CHECK (state IN ('prepared', 'completed')),
    fence_digest bytea NOT NULL CHECK (octet_length(fence_digest) = 32),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (manifest_digest, sequence),
    UNIQUE (tenant_id, command_id)
);

-- Applying this migration to an existing portfolio fences native Request
-- capture before the new binary can be exposed. Fresh tenants have no legacy
-- Request ledger and therefore need no cutover fence.
CREATE TABLE request_native_capture_fences (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id),
    reason text NOT NULL CHECK (reason = 'legacy-request-ledger-cutover'),
    fenced_at timestamptz NOT NULL
);
INSERT INTO request_native_capture_fences (tenant_id, reason, fenced_at)
SELECT tenant_id, 'legacy-request-ledger-cutover', transaction_timestamp() FROM tenants;

CREATE TABLE request_import_rows (
    manifest_digest bytea NOT NULL REFERENCES request_import_manifests(manifest_digest),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    source_request_number bigint NOT NULL CHECK (source_request_number > 0),
    batch_index integer NOT NULL CHECK (batch_index >= 0),
    request_id uuid NOT NULL,
    source_row_digest bytea NOT NULL CHECK (octet_length(source_row_digest) = 32),
    content_digest bytea NOT NULL CHECK (octet_length(content_digest) = 32),
    original_owner_digest bytea NOT NULL CHECK (octet_length(original_owner_digest) = 32),
    relationships_digest bytea NOT NULL CHECK (octet_length(relationships_digest) = 32),
    fence_digest bytea NOT NULL CHECK (octet_length(fence_digest) = 32),
    imported_by uuid NOT NULL,
    command_id uuid NOT NULL,
    imported_at timestamptz NOT NULL,
    PRIMARY KEY (manifest_digest, source_request_number),
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (imported_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, request_id),
    UNIQUE (tenant_id, command_id)
);

CREATE TABLE request_import_batch_proofs (
    manifest_digest bytea NOT NULL REFERENCES request_import_manifests(manifest_digest),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    batch_index integer NOT NULL CHECK (batch_index >= 0),
    proof_digest bytea NOT NULL CHECK (octet_length(proof_digest) = 32),
    target_watermark bigint NOT NULL CHECK (target_watermark >= 1),
    source_count integer NOT NULL CHECK (source_count BETWEEN 1 AND 25),
    cumulative_count bigint NOT NULL CHECK (cumulative_count >= source_count),
    proof_artifact jsonb NOT NULL CHECK (jsonb_typeof(proof_artifact) = 'object'),
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (manifest_digest, batch_index),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE request_owner_aliases (
    request_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    source_owner text NOT NULL CHECK (length(source_owner) BETWEEN 1 AND 256),
    source_owner_digest bytea NOT NULL CHECK (octet_length(source_owner_digest) = 32),
    manifest_digest bytea NOT NULL REFERENCES request_import_manifests(manifest_digest),
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (owner_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, source_owner, request_id)
);

CREATE TABLE request_refinement_facts (
    refinement_fact_id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    target_request_id uuid NOT NULL,
    manifest_digest bytea NOT NULL REFERENCES request_import_manifests(manifest_digest),
    source_relationship_digest bytea NOT NULL
        CHECK (octet_length(source_relationship_digest) = 32),
    recorded_by uuid NOT NULL,
    command_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    FOREIGN KEY (request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (target_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (recorded_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    CHECK (request_id <> target_request_id),
    UNIQUE (manifest_digest, request_id, target_request_id)
);

CREATE INDEX requests_project_number ON requests (tenant_id, project_key, request_number);

CREATE TRIGGER request_owner_facts_immutable
    BEFORE UPDATE OR DELETE ON request_owner_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_priority_facts_immutable
    BEFORE UPDATE OR DELETE ON request_priority_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_triage_facts_immutable
    BEFORE UPDATE OR DELETE ON request_triage_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_ticket_relation_facts_immutable
    BEFORE UPDATE OR DELETE ON request_ticket_relation_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_blocker_facts_immutable
    BEFORE UPDATE OR DELETE ON request_blocker_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_closure_evaluations_immutable
    BEFORE UPDATE OR DELETE ON request_closure_evaluations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_attention_facts_immutable
    BEFORE UPDATE OR DELETE ON request_attention_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_import_manifests_immutable
    BEFORE UPDATE OR DELETE ON request_import_manifests
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_cutover_epoch_facts_immutable
    BEFORE UPDATE OR DELETE ON request_cutover_epoch_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_native_capture_fences_immutable
    BEFORE UPDATE OR DELETE ON request_native_capture_fences
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_import_rows_immutable
    BEFORE UPDATE OR DELETE ON request_import_rows
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_import_batch_proofs_immutable
    BEFORE UPDATE OR DELETE ON request_import_batch_proofs
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_owner_aliases_immutable
    BEFORE UPDATE OR DELETE ON request_owner_aliases
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_refinement_facts_immutable
    BEFORE UPDATE OR DELETE ON request_refinement_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON request_number_allocators, requests, request_owner_facts,
    request_priority_facts, request_triage_facts, request_ticket_relation_facts,
    request_ticket_holders,
    request_blocker_facts, request_closure_evaluations, request_attention_facts,
    request_import_manifests, request_cutover_epoch_facts, request_native_capture_fences,
    request_import_rows,
    request_import_batch_proofs, request_owner_aliases, request_refinement_facts
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON request_number_allocators, requests, request_owner_facts,
    request_priority_facts, request_triage_facts, request_ticket_relation_facts,
    request_blocker_facts, request_closure_evaluations, request_attention_facts,
    request_import_manifests, request_cutover_epoch_facts, request_import_rows,
    request_import_batch_proofs, request_owner_aliases, request_refinement_facts
    TO ctower_svc;
GRANT SELECT ON request_ticket_holders, request_native_capture_fences TO ctower_svc;
GRANT UPDATE (last_number, advanced_at) ON request_number_allocators TO ctower_svc;
GRANT UPDATE (version) ON requests TO ctower_svc;
GRANT SELECT ON requests, request_owner_facts, request_priority_facts,
    request_triage_facts, request_ticket_relation_facts, request_ticket_holders,
    request_blocker_facts,
    request_closure_evaluations, request_attention_facts, request_import_manifests,
    request_cutover_epoch_facts, request_native_capture_fences, request_import_rows,
    request_import_batch_proofs,
    request_owner_aliases, request_refinement_facts
    TO ctower_projection;
