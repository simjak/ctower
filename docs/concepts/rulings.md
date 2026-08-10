# Rulings and the Agreements ledger

A **Ruling** is a dated, citable record of an operator agreement. It preserves the operator's words exactly;
it is not a setting, a Ticket, or a Request.

## Why it exists

Teams need to point at the exact agreement that governed a later choice. Editing a note destroys what was
actually agreed. Ctower therefore gives each Ruling a stable UUID, server timestamp, project-seat
attribution, exact UTF-8 bytes, and digest.

## Correction means append

A Ruling is never edited or deleted. If an agreement changes, append a new Ruling with `--supersedes` set to
the old Ruling ID. Reads then show the predecessor on the new fact and the successor on the old fact. Both
wordings remain citable.

```text
old Ruling ──superseded by──> new Ruling
    │                              │
 exact words remain          new exact words
```

Only an existing active project seat can append. Tenant, Project, principal, and seat are derived from the
authenticated credential; the payload cannot claim them. An identity that is not a project seat receives
`ruling-seat-not-found`, and ctower creates no identity for it.

## Reading honestly

Only off-host-accepted Rulings appear in `ruling list` or `ruling get`. The list names requested, answered,
and unanswered Projects and carries the Record watermark. It sorts newest first by server date and then by
stable ID. A pending append is not silently treated as an agreement.

Use the [CLI reference](../reference/cli.md#rulings) for exact commands and the
[HTTP API reference](../reference/http-api.md#rulings) for generated operations.
