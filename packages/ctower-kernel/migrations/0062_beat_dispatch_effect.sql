-- gh#433: fixed fleet beats are immutable Routine revisions whose queued
-- occurrences emit full-prompt intents for the external director substrate.
ALTER TABLE routine_revisions ADD COLUMN schedule_minutes smallint[];
ALTER TABLE routine_revisions ADD COLUMN schedule_hours smallint[];
ALTER TABLE routine_revisions DROP CONSTRAINT routine_revisions_schedule_kind_check;
ALTER TABLE routine_revisions ADD CONSTRAINT routine_revisions_schedule_kind_check CHECK (
    schedule_kind IN ('daily', 'hourly', 'minute_hour_set')
);
ALTER TABLE routine_revisions DROP CONSTRAINT routine_revisions_check;
ALTER TABLE routine_revisions ADD CONSTRAINT routine_revisions_schedule_shape_check CHECK (
    (schedule_kind = 'daily' AND local_time IS NOT NULL
        AND schedule_minutes IS NULL AND schedule_hours IS NULL)
    OR (schedule_kind = 'hourly' AND local_time IS NULL
        AND schedule_minutes IS NULL AND schedule_hours IS NULL)
    OR (schedule_kind = 'minute_hour_set' AND local_time IS NULL
        AND cardinality(schedule_minutes) >= 1
        AND schedule_minutes <@ ARRAY[
            0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,
            20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,
            40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59
        ]::smallint[]
        AND (schedule_hours IS NULL OR (
            cardinality(schedule_hours) >= 1
            AND schedule_hours <@ ARRAY[
                0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23
            ]::smallint[]
        )))
);

ALTER TABLE routine_revisions DROP CONSTRAINT routine_revisions_handler_kind_check;
ALTER TABLE routine_revisions ADD CONSTRAINT routine_revisions_handler_kind_check CHECK (
    handler_kind IN (
        'synthetic_four_stage', 'daily_backup', 'record_anchor',
        'dream_dispatch', 'beat_dispatch'
    )
);
ALTER TABLE operation_jobs DROP CONSTRAINT operation_jobs_operation_check;
ALTER TABLE operation_jobs ADD CONSTRAINT operation_jobs_operation_check CHECK (
    operation IN (
        'synthetic_four_stage', 'daily_backup', 'record_anchor',
        'dream_dispatch', 'beat_dispatch'
    )
);

CREATE TABLE routine_beat_dispatch_specs (
    revision_digest bytea PRIMARY KEY REFERENCES routine_revisions(revision_digest),
    beat_key text NOT NULL CHECK (beat_key ~ '^[a-z][a-z0-9._-]*$'),
    prompt_source text NOT NULL CHECK (
        prompt_source = 'state/beats/' || beat_key || '.txt'
    ),
    prompt_sha256 bytea NOT NULL CHECK (octet_length(prompt_sha256) = 32),
    prompt text NOT NULL CHECK (octet_length(prompt) BETWEEN 1 AND 16384),
    target_session text NOT NULL CHECK (
        target_session IN ('commander', 'mc-commander-manibo')
    ),
    UNIQUE (beat_key)
);

CREATE TABLE runtime_beat_dispatch_effects (
    effect_id uuid PRIMARY KEY,
    occurrence_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    revision_digest bytea NOT NULL,
    routine_ref text NOT NULL CHECK (
        routine_ref ~ '^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$'
    ),
    scheduled_for timestamptz NOT NULL,
    beat_key text NOT NULL CHECK (beat_key ~ '^[a-z][a-z0-9._-]*$'),
    prompt_source text NOT NULL,
    prompt_sha256 bytea NOT NULL CHECK (octet_length(prompt_sha256) = 32),
    prompt text NOT NULL CHECK (octet_length(prompt) BETWEEN 1 AND 16384),
    target_session text NOT NULL CHECK (
        target_session IN ('commander', 'mc-commander-manibo')
    ),
    emitted_at timestamptz NOT NULL,
    FOREIGN KEY (occurrence_id, tenant_id)
        REFERENCES routine_occurrences(occurrence_id, tenant_id),
    FOREIGN KEY (revision_digest) REFERENCES routine_beat_dispatch_specs(revision_digest),
    UNIQUE (effect_id, tenant_id),
    UNIQUE (tenant_id, revision_digest, scheduled_for),
    CHECK (prompt_source = 'state/beats/' || beat_key || '.txt')
);

CREATE INDEX runtime_beat_dispatch_effects_tenant_schedule
    ON runtime_beat_dispatch_effects (tenant_id, scheduled_for, effect_id);

CREATE TRIGGER routine_beat_dispatch_specs_immutable
    BEFORE UPDATE OR DELETE ON routine_beat_dispatch_specs
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();
CREATE TRIGGER runtime_beat_dispatch_effects_immutable
    BEFORE UPDATE OR DELETE ON runtime_beat_dispatch_effects
    FOR EACH ROW EXECUTE FUNCTION refuse_immutable_control_fact_mutation();

REVOKE ALL ON routine_beat_dispatch_specs, runtime_beat_dispatch_effects
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT INSERT, SELECT ON routine_beat_dispatch_specs, runtime_beat_dispatch_effects TO ctower_svc;
GRANT SELECT ON routine_beat_dispatch_specs, runtime_beat_dispatch_effects TO ctower_projection;
