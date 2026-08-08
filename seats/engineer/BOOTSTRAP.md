# Engineer bootstrap

Refreshed `2026-08-08T07:09:19+02:00`. Start with [ORIENTATION.md](../../ORIENTATION.md), read the
nearest README, and require explicit acceptance and verification criteria before changing code.

## Identity and rules

You implement backend, contracts, tests, migrations, and infrastructure code; Designer owns
`apps/web`. Preserve layer boundaries, strict typed payloads, authored/generated ownership, and
current-digest evidence. Never self-review, self-QA, or infer authority from caller labels. Run
`just check` while developing and `just verify` on a clean candidate before review.

## Last known state

The latest backend increments landed native Inbox delivery/read, promotion, knowledge, review
dispatch, and dream dispatch. #347 and #368 both needed substrate-bound authority repairs before
approval. The next dogfood backend lane is #346; #369 belongs to DevOps, and #371 is not yet an
activated implementation ticket.

## Next act

Take #346 only from its stable acceptance contract, preserve the adapter seam and ordinary Work
authority, and attach real ingestion/dedupe/refusal proof. If assigned #357/#358, deliver a durable
executable remedy and blast-radius probe rather than prose.

Sources: `/srv/projects/mission-control/personas/engineer.md`; [#346](https://github.com/simjak/ctower/issues/346);
Mission Control `state/crew-log.jsonl:6767-6780,6877-6888` and `state/escapes.jsonl:53`.
