ALTER TABLE proof_verdicts ADD COLUMN proof_sequence integer;

UPDATE proof_verdicts AS verdict
SET proof_sequence = event.sequence
FROM events AS event
WHERE event.tenant_id = verdict.tenant_id
  AND event.aggregate_id = verdict.proof_id
  AND event.actor_principal_id = verdict.reviewer_id
  AND event.client_command_id = verdict.client_command_id
  AND event.kind = 'proof.changed';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM proof_verdicts WHERE proof_sequence IS NULL) THEN
        RAISE EXCEPTION 'proof verdict cannot be matched to its authoritative event sequence';
    END IF;
END
$$;

ALTER TABLE proof_verdicts ALTER COLUMN proof_sequence SET NOT NULL;
ALTER TABLE proof_verdicts ADD CONSTRAINT proof_verdicts_sequence_positive
    CHECK (proof_sequence >= 1);
ALTER TABLE proof_verdicts ADD CONSTRAINT proof_verdicts_sequence_unique
    UNIQUE (proof_id, proof_sequence);
