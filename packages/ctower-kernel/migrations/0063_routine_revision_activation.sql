-- gh#433: a corrected immutable Routine revision replaces only the tenant's
-- active trigger. Historical revisions, occurrences, and effects remain facts.
ALTER TABLE routine_revisions
    DROP CONSTRAINT routine_revisions_routine_ref_key;
CREATE INDEX routine_revisions_ref
    ON routine_revisions (routine_ref, registered_at, revision_digest);

ALTER TABLE routine_beat_dispatch_specs
    DROP CONSTRAINT routine_beat_dispatch_specs_beat_key_key;
CREATE INDEX routine_beat_dispatch_specs_key
    ON routine_beat_dispatch_specs (beat_key, revision_digest);

GRANT DELETE ON routine_triggers TO ctower_svc;
