# Morning digest

The morning digest is one read-only operator artifact for a Europe/Vilnius civil date. It answers four
questions in a fixed order:

1. Which recorded Requests still need an operator decision?
2. Which Rulings were recorded during the prior civil day, and what Request execution followed?
3. Which related Tickets expose the current proof timeline?
4. Which accepted open Requests resemble each other and still need an explicit merge decision?

The digest does not persist an answer. It folds accepted Request and Ruling reads at their named
watermarks, derives a stable artifact key, and hashes the canonical content. Repeating the read therefore
creates no new authority or projection row.

## Open decisions

A blocked Request carrying the recorded `operator-decision-required` marker enters this section. Every row
uses the complete record-derived operator decision brief: the issue in plain language, origin, choices with
completeness, recommendation, and safe default. The digest copies that accepted read shape and accepts no
caller or model prose.

## Yesterday's Rulings and execution

“Yesterday” means the prior Europe/Vilnius civil day, including daylight-saving boundaries. Ruling words
stay byte-exact. Execution appears only from the Ruling's typed Request relation. An authoritative absent
relation means zero executions; an unavailable Request source or unresolved relation keeps the Ruling
visible and marks execution `UNKNOWN`. Text similarity never creates a relationship.

## Proof

Each open decision or recorded prior-day execution with a Ticket relation closes the digest with direct
links to that Ticket's timeline. Unrelated historical Requests stay out. The current proof count is copied
from the Request read. An unavailable count remains `UNKNOWN`, not zero. Because recorded executions also
define which Requests belong here, an incomplete Request or prior-day Ruling/execution reading makes the
proof total `UNKNOWN` while preserving every visible proof row.

## Near-duplicate Requests

Each accepted open resemblance pair appears once, even though accepted Request reads expose the link from
both sides. The deterministic line names both permanent numbers and the current candidate state, then says
which Request should receive `request same`. An accepted operator `same` or commander duplicate triage removes
the pair; pending merge facts and unrelated text do not affect the section. The digest only projects the
persisted D57 link. It performs no text comparison, inference, model call, or external egress.

## Partial and unknown sources

Every section publishes its state, visible count, nullable total, and unreached scopes; the artifact carries
both source watermarks. A complete empty source has total `0`. A partial or failed source has total `null`,
while every answered row remains visible. The text renderer says `UNKNOWN total` for the latter.

The operator-only [CLI command](../reference/cli.md#morning-digest) and
[HTTP operation](../reference/http-api.md#morning-digest) expose the same strict artifact. Notification
delivery and scheduling stay outside ctower: Mission Control sends the rendered text through its existing
durable-first notification rail. Only the director may switch or retire the interim schedule. This feature
adds no Slack/Hermes path.
