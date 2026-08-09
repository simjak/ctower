-- gh#392: preserve every accepted binding while allowing the operator to recover
-- on a new versioned lane reference. A lane itself remains bound exactly once.
ALTER TABLE runtime_dream_lane_bindings
    DROP CONSTRAINT runtime_dream_lane_bindings_pkey;
ALTER TABLE runtime_dream_lane_bindings
    ADD CONSTRAINT runtime_dream_lane_bindings_pkey
    PRIMARY KEY (tenant_id, principal_id, lane_ref);
