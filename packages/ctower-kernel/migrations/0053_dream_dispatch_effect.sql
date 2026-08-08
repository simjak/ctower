-- gh#368: a nightly Routine emits a dream-dispatch intent; the external
-- substrate executes it and links the output digest back to Routine custody.
ALTER TABLE routine_revisions DROP CONSTRAINT routine_revisions_handler_kind_check;
ALTER TABLE routine_revisions ADD CONSTRAINT routine_revisions_handler_kind_check CHECK (
    handler_kind IN ('synthetic_four_stage', 'daily_backup', 'record_anchor', 'dream_dispatch')
);
ALTER TABLE operation_jobs DROP CONSTRAINT operation_jobs_operation_check;
ALTER TABLE operation_jobs ADD CONSTRAINT operation_jobs_operation_check CHECK (
    operation IN ('synthetic_four_stage', 'daily_backup', 'record_anchor', 'dream_dispatch')
);

CREATE TABLE routine_dream_dispatch_specs (
    revision_digest bytea PRIMARY KEY REFERENCES routine_revisions(revision_digest),
    scope_kind text NOT NULL CHECK (scope_kind IN ('project', 'fleet')),
    project_key text CHECK (project_key ~ '^[a-z][a-z0-9._-]*$'),
    skill_path text NOT NULL CHECK (skill_path = 'skills/dreamer/SKILL.md'),
    primary_model_ref text NOT NULL CHECK (primary_model_ref = 'gpt-5.6-sol'),
    primary_reasoning_effort text NOT NULL CHECK (primary_reasoning_effort = 'max'),
    fallback_model_ref text NOT NULL CHECK (fallback_model_ref = 'qwen3.8-max'),
    fallback_reasoning_effort text NOT NULL CHECK (fallback_reasoning_effort = 'max'),
    minimum_model_tier text NOT NULL CHECK (minimum_model_tier = 'hard'),
    excluded_model_families text[] NOT NULL CHECK (
        excluded_model_families = ARRAY['claude']::text[]
    ),
    CHECK (
        (scope_kind = 'project' AND project_key IS NOT NULL)
        OR (scope_kind = 'fleet' AND project_key IS NULL)
    )
);

CREATE TABLE runtime_dream_dispatch_effects (
    effect_id uuid PRIMARY KEY,
    occurrence_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    revision_digest bytea NOT NULL,
    routine_ref text NOT NULL CHECK (routine_ref ~ '^[a-z][a-z0-9._-]*@[1-9][0-9]*$'),
    scheduled_for timestamptz NOT NULL,
    scope_kind text NOT NULL CHECK (scope_kind IN ('project', 'fleet')),
    project_key text CHECK (project_key ~ '^[a-z][a-z0-9._-]*$'),
    skill_path text NOT NULL CHECK (skill_path = 'skills/dreamer/SKILL.md'),
    primary_model_ref text NOT NULL CHECK (primary_model_ref = 'gpt-5.6-sol'),
    primary_reasoning_effort text NOT NULL CHECK (primary_reasoning_effort = 'max'),
    fallback_model_ref text NOT NULL CHECK (fallback_model_ref = 'qwen3.8-max'),
    fallback_reasoning_effort text NOT NULL CHECK (fallback_reasoning_effort = 'max'),
    minimum_model_tier text NOT NULL CHECK (minimum_model_tier = 'hard'),
    excluded_model_families text[] NOT NULL CHECK (
        excluded_model_families = ARRAY['claude']::text[]
    ),
    emitted_at timestamptz NOT NULL,
    FOREIGN KEY (occurrence_id, tenant_id)
        REFERENCES routine_occurrences(occurrence_id, tenant_id),
    FOREIGN KEY (revision_digest) REFERENCES routine_dream_dispatch_specs(revision_digest),
    UNIQUE (effect_id, tenant_id),
    UNIQUE (tenant_id, revision_digest, scheduled_for),
    CHECK (
        (scope_kind = 'project' AND project_key IS NOT NULL)
        OR (scope_kind = 'fleet' AND project_key IS NULL)
    )
);

-- Provisioned by the substrate reporter, never by the consuming request. Policy
-- therefore evaluates observed lane/model facts rather than caller labels.
CREATE TABLE runtime_dream_lane_bindings (
    tenant_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    lane_ref text NOT NULL CHECK (char_length(lane_ref) BETWEEN 1 AND 128),
    crew_name text NOT NULL CHECK (crew_name ~ '^[a-z][a-z0-9._-]{1,95}$'),
    harness_ref text NOT NULL CHECK (char_length(harness_ref) BETWEEN 1 AND 128),
    model_ref text NOT NULL CHECK (char_length(model_ref) BETWEEN 1 AND 128),
    model_family text NOT NULL CHECK (model_family ~ '^[a-z][a-z0-9._-]*$'),
    reasoning_effort text NOT NULL CHECK (char_length(reasoning_effort) BETWEEN 1 AND 32),
    model_tier text NOT NULL CHECK (model_tier IN ('cheap', 'hard')),
    binding_source text NOT NULL CHECK (binding_source ~ '^[a-z][a-z0-9._-]*$'),
    probe_evidence text NOT NULL CHECK (probe_evidence ~ '^sha256:[0-9a-f]{64}$'),
    bound_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals(principal_id, tenant_id),
    UNIQUE (
        tenant_id, principal_id, lane_ref, crew_name, harness_ref, model_ref,
        model_family, reasoning_effort, model_tier
    )
);

CREATE TABLE runtime_dream_dispatch_consumptions (
    effect_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    event_id uuid NOT NULL,
    executor_principal_id uuid NOT NULL,
    lane_ref text NOT NULL CHECK (char_length(lane_ref) BETWEEN 1 AND 128),
    crew_name text NOT NULL CHECK (crew_name ~ '^[a-z][a-z0-9._-]{1,95}$'),
    harness_ref text NOT NULL CHECK (char_length(harness_ref) BETWEEN 1 AND 128),
    model_ref text NOT NULL CHECK (char_length(model_ref) BETWEEN 1 AND 128),
    model_family text NOT NULL CHECK (model_family ~ '^[a-z][a-z0-9._-]*$'),
    reasoning_effort text NOT NULL CHECK (char_length(reasoning_effort) BETWEEN 1 AND 32),
    model_tier text NOT NULL CHECK (model_tier IN ('cheap', 'hard')),
    output_digest bytea NOT NULL CHECK (octet_length(output_digest) = 32),
    consumed_at timestamptz NOT NULL,
    FOREIGN KEY (effect_id, tenant_id)
        REFERENCES runtime_dream_dispatch_effects(effect_id, tenant_id),
    FOREIGN KEY (event_id, tenant_id) REFERENCES events(event_id, tenant_id),
    FOREIGN KEY (
        tenant_id, executor_principal_id, lane_ref, crew_name, harness_ref,
        model_ref, model_family, reasoning_effort, model_tier
    ) REFERENCES runtime_dream_lane_bindings (
        tenant_id, principal_id, lane_ref, crew_name, harness_ref,
        model_ref, model_family, reasoning_effort, model_tier
    ),
    UNIQUE (event_id)
);

CREATE FUNCTION enforce_dream_dispatch_model_requirement() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    effect runtime_dream_dispatch_effects%ROWTYPE;
BEGIN
    SELECT * INTO STRICT effect FROM runtime_dream_dispatch_effects
    WHERE effect_id = NEW.effect_id AND tenant_id = NEW.tenant_id;
    IF NEW.model_ref NOT IN (effect.primary_model_ref, effect.fallback_model_ref)
       OR (NEW.model_ref = effect.primary_model_ref
           AND NEW.reasoning_effort <> effect.primary_reasoning_effort)
       OR (NEW.model_ref = effect.fallback_model_ref
           AND NEW.reasoning_effort <> effect.fallback_reasoning_effort)
       OR NEW.model_tier <> effect.minimum_model_tier
       OR NEW.model_family = ANY(effect.excluded_model_families) THEN
        RAISE EXCEPTION 'dream dispatch model requirement mismatch'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER runtime_dream_dispatch_consumption_requirement
    BEFORE INSERT ON runtime_dream_dispatch_consumptions
    FOR EACH ROW EXECUTE FUNCTION enforce_dream_dispatch_model_requirement();

ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created', 'ticket.created', 'ticket.custody_transferred',
    'ticket.comment_added', 'proof.changed', 'workflow.changed', 'work.changed',
    'routine.occurrence_recorded', 'runtime.dream_dispatch_consumed',
    'attention.poison_disposition_recorded',
    'catalog.component_published', 'catalog.bundle_activated', 'migration.changed',
    'intake.inbound_event_recorded', 'intake.inbound_event_promoted',
    'access.seat_credential_issued', 'access.seat_credential_revoked',
    'session.started', 'session.transitioned', 'session.closed',
    'ticket.change_reference_recorded', 'ticket.label_applied',
    'attention.finding_appended', 'attention.finding_disposition_recorded',
    'thread.opened', 'message.appended', 'message.delivered', 'message.read',
    'thread.promoted_to_ticket', 'knowledge.document_registered'
));

CREATE INDEX runtime_dream_dispatch_effects_tenant_schedule
    ON runtime_dream_dispatch_effects (tenant_id, scheduled_for, effect_id);

CREATE TRIGGER routine_dream_dispatch_specs_immutable
    BEFORE UPDATE OR DELETE ON routine_dream_dispatch_specs
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER runtime_dream_dispatch_effects_immutable
    BEFORE UPDATE OR DELETE ON runtime_dream_dispatch_effects
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER runtime_dream_lane_bindings_immutable
    BEFORE UPDATE OR DELETE ON runtime_dream_lane_bindings
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER runtime_dream_dispatch_consumptions_immutable
    BEFORE UPDATE OR DELETE ON runtime_dream_dispatch_consumptions
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON routine_dream_dispatch_specs, runtime_dream_dispatch_effects,
    runtime_dream_lane_bindings, runtime_dream_dispatch_consumptions
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON routine_dream_dispatch_specs, runtime_dream_dispatch_effects,
    runtime_dream_lane_bindings, runtime_dream_dispatch_consumptions TO ctower_svc;
GRANT SELECT ON routine_dream_dispatch_specs, runtime_dream_dispatch_effects,
    runtime_dream_lane_bindings, runtime_dream_dispatch_consumptions TO ctower_projection;
