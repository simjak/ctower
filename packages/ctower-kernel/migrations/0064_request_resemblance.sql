-- gh#431: Request capture always records the new wording, speaks a local-compute
-- resemblance, and leaves merge authority to literal operator `same` or
-- commander duplicate triage. Links and merge provenance are immutable facts.
CREATE TABLE request_resemblance_links (
    link_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    source_request_id uuid NOT NULL,
    candidate_request_id uuid NOT NULL,
    similarity double precision NOT NULL CHECK (similarity BETWEEN 0.72 AND 1.0),
    algorithm_ref text NOT NULL CHECK (algorithm_ref = 'ctower.local-hashed-subword/v1'),
    source_embedding_digest bytea NOT NULL CHECK (octet_length(source_embedding_digest) = 32),
    candidate_embedding_digest bytea NOT NULL CHECK (octet_length(candidate_embedding_digest) = 32),
    linked_by uuid NOT NULL,
    command_id uuid NOT NULL,
    linked_at timestamptz NOT NULL,
    FOREIGN KEY (source_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (candidate_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (linked_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, source_request_id),
    CHECK (source_request_id <> candidate_request_id)
);
CREATE INDEX request_resemblance_candidate
    ON request_resemblance_links (tenant_id, candidate_request_id, source_request_id);

CREATE TABLE request_merge_facts (
    merge_fact_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    duplicate_request_id uuid NOT NULL,
    duplicate_request_number bigint NOT NULL CHECK (duplicate_request_number > 0),
    duplicate_content text NOT NULL CHECK (length(duplicate_content) BETWEEN 1 AND 65536),
    duplicate_content_digest bytea NOT NULL CHECK (octet_length(duplicate_content_digest) = 32),
    duplicate_created_at timestamptz NOT NULL,
    canonical_request_id uuid NOT NULL,
    canonical_request_number bigint NOT NULL CHECK (canonical_request_number > 0),
    canonical_content text NOT NULL CHECK (length(canonical_content) BETWEEN 1 AND 65536),
    canonical_content_digest bytea NOT NULL CHECK (octet_length(canonical_content_digest) = 32),
    canonical_created_at timestamptz NOT NULL,
    trigger_kind text NOT NULL CHECK (trigger_kind IN ('operator_same', 'commander_triage')),
    merge_wording text NOT NULL CHECK (length(merge_wording) BETWEEN 1 AND 500),
    merged_by uuid NOT NULL,
    command_id uuid NOT NULL,
    merged_at timestamptz NOT NULL,
    FOREIGN KEY (duplicate_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (canonical_request_id, tenant_id) REFERENCES requests(request_id, tenant_id),
    FOREIGN KEY (merged_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, duplicate_request_id),
    CHECK (duplicate_request_id <> canonical_request_id)
);

CREATE TRIGGER request_resemblance_links_immutable
    BEFORE UPDATE OR DELETE ON request_resemblance_links
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_merge_facts_immutable
    BEFORE UPDATE OR DELETE ON request_merge_facts
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON request_resemblance_links, request_merge_facts
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT, INSERT ON request_resemblance_links, request_merge_facts TO ctower_svc;
GRANT SELECT ON request_resemblance_links, request_merge_facts TO ctower_projection;
