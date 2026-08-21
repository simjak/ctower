# Seats and crews

A **seat** is a durable accountable role. A **principal** is the authenticated human or machine identity
that holds the seat and acts through it. A **crew** is one temporary engagement of a seat.

## Why ctower keeps them separate

One seat may work through several crews over time. A crew can stop, restart, or use another model or
harness. A **harness** is the program environment that runs the work. None of those changes should create a
new accountable role or rewrite old history.

The separation answers two different questions:

- Seat: who is responsible?
- Crew: which current engagement is doing the work?

Recorded work sessions keep the ticket, seat, crew, model, harness, worktree, branch, state changes, token
counts, duration, outcome, and evidence reference. They do not turn terminal text into proof.

## Current read path

The browser organization and crew views are deferred to the separately activated CT-I2-005/I2.4 product
lane. No current browser route is implementation or evidence for these facts. Use the protected CLI below for
recorded session facts; it preserves explicit missing and unreachable states rather than showing a false empty
result.

For recorded session facts, use:

```text
ctl session ticket <ticket-id> --project-key <project>
ctl session project <project>
```

Session writes are separate protected commands. They record activity. They do not assign ticket custody,
pass a gate, or close a ticket.
