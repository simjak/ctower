-- gh#347: Workflow emits a review-dispatch intent; Work records substrate
-- consumption; Proof verdicts are linked back without executing an agent here.
CREATE TABLE workflow_review_model_bindings (
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    model_ref text NOT NULL CHECK (char_length(model_ref) BETWEEN 1 AND 128),
    model_family text NOT NULL CHECK (model_family ~ '^[a-z][a-z0-9._-]*$'),
    bound_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (tenant_id, principal_id, model_ref, model_family)
);

CREATE TABLE workflow_review_dispatch_effects (
    effect_id uuid PRIMARY KEY,
    workflow_run_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    workflow_version integer NOT NULL CHECK (workflow_version >= 2),
    destination_stage text NOT NULL CHECK (destination_stage ~ '^[a-z][a-z0-9._-]*$'),
    candidate_digest bytea NOT NULL CHECK (octet_length(candidate_digest) = 32),
    author_principal_id uuid NOT NULL,
    author_model_ref text NOT NULL CHECK (char_length(author_model_ref) BETWEEN 1 AND 128),
    author_family text NOT NULL CHECK (author_family ~ '^[a-z][a-z0-9._-]*$'),
    repository text NOT NULL CHECK (char_length(repository) BETWEEN 1 AND 256),
    change_identity text NOT NULL CHECK (char_length(change_identity) BETWEEN 1 AND 128),
    pr_reference text NOT NULL CHECK (char_length(pr_reference) BETWEEN 1 AND 256),
    routing_policy_ref text NOT NULL
        CHECK (routing_policy_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    reviewer_family_rule text NOT NULL CHECK (reviewer_family_rule = 'different_from_author'),
    emitted_at timestamptz NOT NULL,
    FOREIGN KEY (workflow_run_id, tenant_id)
        REFERENCES workflow_runs(workflow_run_id, tenant_id),
    FOREIGN KEY (ticket_id, tenant_id) REFERENCES tickets(ticket_id, tenant_id),
    FOREIGN KEY (author_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, author_principal_id, author_model_ref, author_family)
        REFERENCES workflow_review_model_bindings (
            tenant_id, principal_id, model_ref, model_family
        ),
    UNIQUE (workflow_run_id, destination_stage, candidate_digest),
    UNIQUE (effect_id, tenant_id),
    UNIQUE (effect_id, tenant_id, author_family)
);

CREATE TABLE workflow_review_dispatch_lenses (
    effect_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    lens_key text NOT NULL CHECK (lens_key ~ '^[a-z][a-z0-9._-]*$'),
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    PRIMARY KEY (effect_id, lens_key),
    FOREIGN KEY (effect_id, tenant_id)
        REFERENCES workflow_review_dispatch_effects(effect_id, tenant_id),
    UNIQUE (effect_id, ordinal)
);

CREATE TABLE workflow_review_dispatch_consumptions (
    effect_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    reviewer_principal_id uuid NOT NULL,
    author_family text NOT NULL CHECK (author_family ~ '^[a-z][a-z0-9._-]*$'),
    reviewer_model_ref text NOT NULL CHECK (char_length(reviewer_model_ref) BETWEEN 1 AND 128),
    reviewer_family text NOT NULL CHECK (reviewer_family ~ '^[a-z][a-z0-9._-]*$'),
    crew_name text NOT NULL CHECK (crew_name ~ '^[a-z][a-z0-9._-]{1,95}$'),
    consumed_by uuid NOT NULL,
    consumed_at timestamptz NOT NULL,
    CHECK (author_family <> reviewer_family),
    FOREIGN KEY (effect_id, tenant_id)
        REFERENCES workflow_review_dispatch_effects(effect_id, tenant_id),
    FOREIGN KEY (effect_id, tenant_id, author_family)
        REFERENCES workflow_review_dispatch_effects(effect_id, tenant_id, author_family),
    FOREIGN KEY (reviewer_principal_id, tenant_id)
        REFERENCES principals(principal_id, tenant_id),
    FOREIGN KEY (tenant_id, reviewer_principal_id, reviewer_model_ref, reviewer_family)
        REFERENCES workflow_review_model_bindings (
            tenant_id, principal_id, model_ref, model_family
        ),
    FOREIGN KEY (consumed_by, tenant_id) REFERENCES principals(principal_id, tenant_id)
);

CREATE TABLE workflow_review_dispatch_verdict_links (
    effect_id uuid NOT NULL,
    verdict_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    linked_at timestamptz NOT NULL,
    PRIMARY KEY (effect_id, verdict_id),
    FOREIGN KEY (effect_id, tenant_id)
        REFERENCES workflow_review_dispatch_effects(effect_id, tenant_id),
    FOREIGN KEY (verdict_id, tenant_id) REFERENCES proof_verdicts(verdict_id, tenant_id),
    UNIQUE (verdict_id)
);

CREATE FUNCTION link_review_dispatch_verdict() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO workflow_review_dispatch_verdict_links (
        effect_id, verdict_id, tenant_id, linked_at
    )
    SELECT effect.effect_id, NEW.verdict_id, NEW.tenant_id, NEW.recorded_at
    FROM workflow_review_dispatch_effects AS effect
    JOIN workflow_review_dispatch_consumptions AS consumption
      ON consumption.effect_id = effect.effect_id
     AND consumption.tenant_id = effect.tenant_id
    JOIN workflow_review_dispatch_lenses AS lens
      ON lens.effect_id = effect.effect_id
     AND lens.tenant_id = effect.tenant_id
    WHERE effect.tenant_id = NEW.tenant_id
      AND effect.ticket_id = (
          SELECT bundle.ticket_id FROM proof_bundles AS bundle
          WHERE bundle.proof_id = NEW.proof_id AND bundle.tenant_id = NEW.tenant_id
      )
      AND effect.candidate_digest = NEW.candidate_digest
      AND consumption.reviewer_principal_id = NEW.reviewer_id
      AND lens.lens_key = NEW.criterion_key
    ON CONFLICT (verdict_id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER proof_verdict_links_review_dispatch
    AFTER INSERT ON proof_verdicts
    FOR EACH ROW EXECUTE FUNCTION link_review_dispatch_verdict();

CREATE INDEX workflow_review_dispatch_ticket
    ON workflow_review_dispatch_effects (tenant_id, ticket_id, emitted_at, effect_id);

CREATE TRIGGER workflow_review_model_bindings_immutable
    BEFORE UPDATE OR DELETE ON workflow_review_model_bindings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER workflow_review_dispatch_effects_immutable
    BEFORE UPDATE OR DELETE ON workflow_review_dispatch_effects
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER workflow_review_dispatch_lenses_immutable
    BEFORE UPDATE OR DELETE ON workflow_review_dispatch_lenses
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER workflow_review_dispatch_consumptions_immutable
    BEFORE UPDATE OR DELETE ON workflow_review_dispatch_consumptions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER workflow_review_dispatch_verdict_links_immutable
    BEFORE UPDATE OR DELETE ON workflow_review_dispatch_verdict_links
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON workflow_review_model_bindings, workflow_review_dispatch_effects,
    workflow_review_dispatch_lenses,
    workflow_review_dispatch_consumptions, workflow_review_dispatch_verdict_links
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON workflow_review_model_bindings, workflow_review_dispatch_effects,
    workflow_review_dispatch_lenses,
    workflow_review_dispatch_consumptions, workflow_review_dispatch_verdict_links
    TO ctower_svc;
GRANT SELECT ON workflow_review_model_bindings, workflow_review_dispatch_effects,
    workflow_review_dispatch_lenses,
    workflow_review_dispatch_consumptions, workflow_review_dispatch_verdict_links
    TO ctower_projection;
