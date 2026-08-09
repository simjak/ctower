# The operator's ctower quickstart

Ctower is a shadow copy of work for now. Use it to inspect low-value, replaceable work. Keep Mission Control and GitHub or GitLab as the other records until the shadow label is removed.

## See your work

Open `/board`. It is the read-only dashboard for tickets. The tabs at the top switch between `manibo`, `ctower`, and `bh-loop`. A healthy board sorts tickets into Backlog, Ready, In progress, In review, Blocked, and Complete. Open a card to see that ticket.

Open `/inbox` to see messages addressed to the current ctower identity. A thread can carry a permanent link to the ticket made from it.

On the served shadow instance checked on 7 August 2026, all five URLs returned a page: `/board`, each of its three project tabs, and `/inbox`. The pages also reported current read problems instead of showing false empty lists. The `ctower` and `manibo` tabs could not read one board field. The `bh-loop` tab received `0 of 0` and refused to call that an empty project. `/inbox` reported that its record call returned 404.

The browser has no write authority. The New ticket control is disabled and says why. The separate Inbox
controls ask the server-authorized send and promotion operations to append a message or create/link a
ticket; their server actions hold the development credential and the API still decides authorization. See
the [dogfood Inbox controls reference](reference/dogfood-inbox-controls.md).

## How a ticket moves

The process that runs today has four steps:

1. **Capture:** record the promise, source, priority, and accountable owner.
2. **Frame:** agree what must be true and lock those checks to this version of the work.
3. **Verify:** attach proof and record a pass from an allowed second person.
4. **Close:** ask ctower to resolve and then close the ticket.

The accountable Commander keeps ownership from capture through close. Agents use `ctowerctl` to request each move. The person who set the checks cannot record the pass. Ctower makes the move only when the next step is allowed and its requirements are present.

## The close gate

No evidence, no close. Moving a card does not prove completion.

Before close, ctower checks that the ticket has evidence for the current version of the work and a required passing decision. Missing, old, mismatched, or self-approved proof causes a refusal. Nothing moves, and the refusal names what is missing.

## Where evidence lives

Evidence lives on the ticket, not in chat, a status file, or a terminal. The ticket record keeps the named check, the exact work version, the proof's fingerprint, who supplied it, who recorded the decision, and the ordered history of ownership and changes.

Use the ticket page when its record is readable. Until then, agents and operators can inspect the same ticket and its history with `ctowerctl`. External proof such as a test run or source-host record stays at its source; the ticket keeps the exact reference that joins it to this work.
