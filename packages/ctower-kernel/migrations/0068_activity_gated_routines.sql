-- CT-I1-033 (R3000/R2999): company/project-scoped activity-gated Routines.
-- Closed typed gate set evaluated inside the scheduler scan; every evaluation
-- appends a fire/skip/degraded fact standing on a named watermark.

CREATE TABLE routine_activity_gates (
    revision_digest bytea PRIMARY KEY REFERENCES routine_revisions(revision_digest),
    gate_kind text NOT NULL CHECK (gate_kind IN (
        'always', 'new_movement_since_watermark', 'open_tickets_above'
    )),
    gate_source text CHECK (gate_source IN ('events', 'tickets')),
    gate_threshold integer CHECK (gate_threshold >= 0),
    gate_project_key text CHECK (gate_project_key ~ '^[a-z][a-z0-9-]{2,63}$'),
    CHECK (
        (gate_kind = 'always'
            AND gate_source IS NULL AND gate_threshold IS NULL AND gate_project_key IS NULL)
        OR (gate_kind = 'new_movement_since_watermark'
            AND gate_source IS NOT NULL
            AND gate_threshold IS NULL AND gate_project_key IS NULL)
        OR (gate_kind = 'open_tickets_above'
            AND (gate_source IS NULL OR gate_source = 'tickets')
            AND gate_threshold IS NOT NULL)
    )
);

CREATE TABLE routine_gate_watermarks (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    revision_digest bytea NOT NULL REFERENCES routine_revisions(revision_digest),
    watermark_kind text NOT NULL CHECK (watermark_kind IN (
        'events.server_time', 'tickets.server_time', 'tickets.nonterminal'
    )),
    watermark_position timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, revision_digest, watermark_kind)
);

CREATE TABLE routine_gate_evaluations (
    evaluation_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    revision_digest bytea NOT NULL,
    scheduled_for timestamptz NOT NULL,
    gate_kind text NOT NULL CHECK (gate_kind IN (
        'always', 'new_movement_since_watermark', 'open_tickets_above'
    )),
    result text NOT NULL CHECK (result IN ('fired', 'skipped', 'degraded')),
    watermark_kind text NOT NULL CHECK (watermark_kind IN (
        'none', 'events.server_time', 'tickets.server_time', 'tickets.nonterminal'
    )),
    watermark_position timestamptz,
    observed_count integer NOT NULL CHECK (observed_count >= -1),
    detail text NOT NULL CHECK (length(detail) BETWEEN 1 AND 500),
    evaluated_at timestamptz NOT NULL,
    FOREIGN KEY (revision_digest) REFERENCES routine_revisions(revision_digest),
    UNIQUE (tenant_id, revision_digest, scheduled_for)
);

CREATE INDEX routine_gate_evaluations_tenant_time
    ON routine_gate_evaluations (tenant_id, evaluated_at, evaluation_id);

-- The movement gate stands on the event spine; give it an indexable position.
CREATE INDEX events_tenant_server_time ON events (tenant_id, server_time);

-- mc-cron.* registrations are the migrated external schedules; their dispatch
-- facts cite prompt sources that name the external twin.
ALTER TABLE routine_beat_dispatch_specs DROP CONSTRAINT routine_beat_dispatch_specs_check;
ALTER TABLE routine_beat_dispatch_specs ADD CONSTRAINT routine_beat_dispatch_specs_check CHECK (
    prompt_source = 'state/beats/' || beat_key || '.txt'
    OR prompt_source = 'crontab/' || beat_key || '.txt'
);
ALTER TABLE runtime_beat_dispatch_effects DROP CONSTRAINT runtime_beat_dispatch_effects_routine_ref_check;
ALTER TABLE runtime_beat_dispatch_effects ADD CONSTRAINT runtime_beat_dispatch_effects_routine_ref_check CHECK (
    routine_ref ~ '^(ctower|mc-cron)\.[a-z][a-z0-9._-]*@[1-9][0-9]*$'
);
ALTER TABLE runtime_beat_dispatch_effects DROP CONSTRAINT runtime_beat_dispatch_effects_check;
ALTER TABLE runtime_beat_dispatch_effects ADD CONSTRAINT runtime_beat_dispatch_effects_check CHECK (
    prompt_source = 'state/beats/' || beat_key || '.txt'
    OR prompt_source = 'crontab/' || beat_key || '.txt'
);

-- Retirement already deletes the active trigger; mc-cron.* refs may retire the
-- same append-only way (rollback path for every migrated schedule).
ALTER TABLE routine_retirements DROP CONSTRAINT routine_retirements_routine_ref_check;
ALTER TABLE routine_retirements ADD CONSTRAINT routine_retirements_routine_ref_check CHECK (
    routine_ref ~ '^(ctower\.beat|mc-cron)\.[a-z][a-z0-9._-]*@[1-9][0-9]*$'
);

CREATE TRIGGER routine_activity_gates_immutable
    BEFORE UPDATE OR DELETE ON routine_activity_gates
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER routine_gate_evaluations_immutable
    BEFORE UPDATE OR DELETE ON routine_gate_evaluations
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON routine_activity_gates, routine_gate_watermarks, routine_gate_evaluations
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT, UPDATE ON routine_gate_watermarks TO ctower_svc;
GRANT SELECT ON routine_gate_watermarks TO ctower_projection;
GRANT INSERT, SELECT ON routine_activity_gates, routine_gate_evaluations TO ctower_svc;
GRANT SELECT ON routine_activity_gates, routine_gate_evaluations TO ctower_projection;
