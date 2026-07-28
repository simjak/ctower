ALTER TABLE durability_policy_state
    DROP CONSTRAINT durability_policy_state_mode_check,
    ADD CONSTRAINT durability_policy_state_mode_check
        CHECK (mode IN ('pending_only', 'development_offhost_ack', 'cutover_rpo0'));
