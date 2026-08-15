-- CT-I1-024 / D59: Request-maintenance proposals are immutable facts that
-- remain separate from Request authority until one operator confirms them.
ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'routine.retired',
    'runtime.dream_dispatch_consumed', 'runtime.dream_lane_bound',
    'attention.poison_disposition_recorded', 'catalog.component_published',
    'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered', 'request.changed',
    'ruling.recorded', 'request.proposal_changed'
));

ALTER TABLE event_links DROP CONSTRAINT event_links_subject_kind_check;
ALTER TABLE event_links ADD CONSTRAINT event_links_subject_kind_check CHECK (
    subject_kind IN (
        'ticket', 'work', 'workflow', 'proof', 'catalog', 'migration',
        'inbound_thread', 'inbound_event', 'access', 'session',
        'attention_finding', 'attention_finding_disposition', 'inbox_thread',
        'knowledge_document', 'request', 'ruling', 'request_proposal'
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
            'knowledge_document', 'request', 'ruling', 'request_proposal'
        )
    );

CREATE TABLE request_maintenance_proposals (
    proposal_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    project_key text NOT NULL CHECK (project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    kind text NOT NULL CHECK (
        kind IN ('duplicate', 'completed-but-open', 'supersession', 'kill', 'keep')
    ),
    basis text NOT NULL CHECK (basis IN ('recorded-evidence', 'similarity')),
    target_request_id uuid NOT NULL,
    target_expected_version integer NOT NULL CHECK (target_expected_version >= 1),
    target_text text NOT NULL CHECK (length(target_text) BETWEEN 1 AND 65536),
    related_request_id uuid,
    related_expected_version integer,
    related_text text,
    source_record_position bigint NOT NULL CHECK (source_record_position >= 0),
    proposer_principal_id uuid NOT NULL,
    seat_credential_id uuid,
    ambiguity_reason text CHECK (
        ambiguity_reason IN (
            'evidence-conflicting-or-incomplete', 'duplicate-uncertain',
            'supersession-unclear', 'target-version-stale', 'completion-unproven'
        )
    ),
    proposal_version integer NOT NULL CHECK (proposal_version = 1),
    append_command_id uuid NOT NULL,
    append_event_id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (proposal_id, tenant_id),
    UNIQUE (tenant_id, proposer_principal_id, append_command_id),
    FOREIGN KEY (target_request_id, tenant_id, project_key)
        REFERENCES requests(request_id, tenant_id, project_key),
    FOREIGN KEY (related_request_id, tenant_id, project_key)
        REFERENCES requests(request_id, tenant_id, project_key),
    FOREIGN KEY (proposer_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (seat_credential_id, tenant_id)
        REFERENCES seat_credential_issuances(credential_id, tenant_id),
    FOREIGN KEY (append_event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (tenant_id, proposer_principal_id, append_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    CHECK (
        (kind IN ('duplicate', 'supersession')
            AND related_request_id IS NOT NULL
            AND related_expected_version >= 1
            AND length(related_text) BETWEEN 1 AND 65536
            AND related_request_id <> target_request_id)
        OR
        (kind IN ('completed-but-open', 'kill', 'keep')
            AND related_request_id IS NULL
            AND related_expected_version IS NULL
            AND related_text IS NULL)
    ),
    CHECK (basis = 'recorded-evidence' OR kind = 'duplicate')
);
CREATE INDEX request_maintenance_proposals_queue
    ON request_maintenance_proposals (
        tenant_id, project_key, created_at, proposal_id
    );

CREATE TABLE request_maintenance_proposal_evidence (
    evidence_pointer_id uuid PRIMARY KEY,
    proposal_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    pointer_kind text NOT NULL CHECK (pointer_kind IN ('record-event', 'proof-evidence')),
    record_event_id uuid,
    record_event_kind text,
    record_event_digest bytea,
    ticket_id uuid,
    proof_id uuid,
    evidence_id uuid,
    artifact_digest bytea,
    recorded_at timestamptz NOT NULL,
    UNIQUE (evidence_pointer_id, tenant_id),
    UNIQUE (proposal_id, evidence_pointer_id),
    FOREIGN KEY (proposal_id, tenant_id)
        REFERENCES request_maintenance_proposals(proposal_id, tenant_id),
    FOREIGN KEY (record_event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (proof_id, tenant_id) REFERENCES proof_bundles(proof_id, tenant_id),
    FOREIGN KEY (evidence_id, tenant_id) REFERENCES proof_evidence(evidence_id, tenant_id),
    FOREIGN KEY (tenant_id, artifact_digest)
        REFERENCES proof_objects(tenant_id, artifact_digest),
    CHECK (
        (pointer_kind = 'record-event'
            AND record_event_id IS NOT NULL
            AND length(record_event_kind) BETWEEN 1 AND 128
            AND octet_length(record_event_digest) = 32
            AND ticket_id IS NULL AND proof_id IS NULL
            AND evidence_id IS NULL AND artifact_digest IS NULL)
        OR
        (pointer_kind = 'proof-evidence'
            AND record_event_id IS NULL AND record_event_kind IS NULL
            AND record_event_digest IS NULL
            AND ticket_id IS NOT NULL AND proof_id IS NOT NULL
            AND evidence_id IS NOT NULL AND octet_length(artifact_digest) = 32)
    )
);

CREATE TABLE request_maintenance_proposal_decisions (
    decision_id uuid PRIMARY KEY,
    proposal_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    operation text NOT NULL CHECK (operation IN ('confirmed', 'rejected')),
    expected_proposal_version integer NOT NULL CHECK (expected_proposal_version = 1),
    decided_by uuid NOT NULL,
    decision_command_id uuid NOT NULL,
    decision_event_id uuid NOT NULL,
    reason text CHECK (reason IS NULL OR length(reason) BETWEEN 1 AND 500),
    target_command_id uuid,
    target_outcome text CHECK (target_outcome IN ('accepted', 'refused')),
    target_problem_code text,
    target_request_version integer,
    decided_at timestamptz NOT NULL,
    UNIQUE (proposal_id),
    UNIQUE (decision_id, tenant_id),
    UNIQUE (tenant_id, decided_by, decision_command_id),
    FOREIGN KEY (proposal_id, tenant_id)
        REFERENCES request_maintenance_proposals(proposal_id, tenant_id),
    FOREIGN KEY (decided_by, tenant_id) REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (decision_event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (tenant_id, decided_by, decision_command_id)
        REFERENCES command_results(tenant_id, principal_id, client_command_id),
    CHECK (
        (operation = 'rejected'
            AND target_command_id IS NULL AND target_outcome IS NULL
            AND target_problem_code IS NULL AND target_request_version IS NULL)
        OR
        (operation = 'confirmed' AND target_command_id IS NOT NULL
            AND target_outcome IS NOT NULL
            AND ((target_outcome = 'accepted' AND target_problem_code IS NULL
                    AND target_request_version >= 2)
                OR (target_outcome = 'refused' AND length(target_problem_code) >= 1
                    AND target_request_version IS NULL)))
    )
);

CREATE TRIGGER request_maintenance_proposals_immutable
    BEFORE UPDATE OR DELETE ON request_maintenance_proposals
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_maintenance_proposal_evidence_immutable
    BEFORE UPDATE OR DELETE ON request_maintenance_proposal_evidence
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER request_maintenance_proposal_decisions_immutable
    BEFORE UPDATE OR DELETE ON request_maintenance_proposal_decisions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON request_maintenance_proposals,
    request_maintenance_proposal_evidence,
    request_maintenance_proposal_decisions
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON request_maintenance_proposals,
    request_maintenance_proposal_evidence,
    request_maintenance_proposal_decisions TO ctower_svc;
GRANT SELECT ON request_maintenance_proposals,
    request_maintenance_proposal_evidence,
    request_maintenance_proposal_decisions TO ctower_projection;
