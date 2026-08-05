-- AC-PD-10 / INV-66: a checkpoint definition MAY declare its delivery surface.
-- NULL = explicitly undeclared (STATE_UNKNOWN); a non-null value is always
-- one of {"declared": "absent"} or {"declared": "present", ...identity...}.
-- ADD COLUMN does not touch existing immutable rows or fire the
-- refuse_immutable_control_fact_mutation trigger on this table.
ALTER TABLE project_delivery_checkpoint_definitions
    ADD COLUMN landing_boundary jsonb CHECK (
        landing_boundary IS NULL OR (
            jsonb_typeof(landing_boundary) = 'object'
            AND landing_boundary ? 'declared'
            AND landing_boundary->>'declared' IN ('present', 'absent')
            AND (
                (landing_boundary->>'declared' = 'absent' AND NOT landing_boundary ? 'identity')
                OR (landing_boundary->>'declared' = 'present' AND landing_boundary ? 'identity')
            )
        )
    ),
    ADD COLUMN non_production_environments jsonb CHECK (
        non_production_environments IS NULL OR (
            jsonb_typeof(non_production_environments) = 'object'
            AND non_production_environments ? 'declared'
            AND non_production_environments->>'declared' IN ('present', 'absent')
            AND (
                (non_production_environments->>'declared' = 'absent'
                    AND NOT non_production_environments ? 'environments')
                OR (non_production_environments->>'declared' = 'present'
                    AND jsonb_typeof(non_production_environments->'environments') = 'array')
            )
        )
    ),
    ADD COLUMN externally_effective_outcome jsonb CHECK (
        externally_effective_outcome IS NULL OR (
            jsonb_typeof(externally_effective_outcome) = 'object'
            AND externally_effective_outcome ? 'declared'
            AND externally_effective_outcome->>'declared' IN ('present', 'absent')
            AND (
                (externally_effective_outcome->>'declared' = 'absent'
                    AND NOT externally_effective_outcome ? 'identity')
                OR (externally_effective_outcome->>'declared' = 'present'
                    AND externally_effective_outcome ? 'identity')
            )
        )
    );
