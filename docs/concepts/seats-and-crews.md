# Seats and crews

A **seat** is a durable role and principal. It can hold authority and remain accountable across many pieces
of work. A **crew** is one temporary engagement of a seat.

## Why ctower keeps them separate

One seat may work through several crews over time. A crew can stop, restart, or use another model or
harness. A **harness** is the program environment that runs the work. None of those changes should create a
new accountable role or rewrite old history.

The separation answers two different questions:

- Seat: who is responsible?
- Crew: which current engagement is doing the work?

Recorded work sessions keep the ticket, seat, crew, model, harness, worktree, branch, state changes, token
counts, duration, outcome, and evidence reference. They do not turn terminal text into proof.

## How to use the views

Open `/team` in the local shadow browser to see the organization view. Select a seat to open
`/team/<seat>`. That page groups the live crews for the seat. Select a crew to open `/crew/<crew-name>`.

The browser joins several local sources for these views. It labels missing and unreachable data instead of
showing a false empty result. The view is read-only.

For recorded session facts, use:

```text
ctl session ticket <ticket-id> --project-key <project>
ctl session project <project>
```

Session writes are separate protected commands. They record activity. They do not assign ticket custody,
pass a gate, or close a ticket.
