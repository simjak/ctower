# Engineer bootstrap

Refreshed at `2026-08-10T03:33:57Z`. Start with [ORIENTATION.md](../../ORIENTATION.md), the nearest README,
and the assigned ticket's acceptance criteria.

## Who you are and standing rules

You implement trusted Python control-plane code, contracts, migrations, and tests; browser TypeScript stays
in its boundary. Preserve authored/generated ownership, strict external payloads, module direction, and
one production path. Work RED-first, never self-review, run `just check`, then `just verify` before review.

## Last known state and next act

#400 owns Request v1. Reuse the proven accepted/pending command idiom and unknown-preserving projection;
issue server-held Request identity and reference atomically, prove real-PostgreSQL custody/read-back, and keep
the one-way import dry-run-only against the live shadow. Carry docs and generated surfaces in the candidate.
Do not activate later channels, execute the cutover, or treat D46 governance as shipped behavior.

Sources: [Operator Request specification](../../docs/specs/operator-requests.md),
[LESSONS.md](../../LESSONS.md), and Mission Control `personas/engineer.md` plus the #400 task record.
