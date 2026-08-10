# Tickets

A **ticket** is the permanent record for one promised result. It keeps the same identity when the worker,
stage, priority, or owner changes.

## Why tickets exist

A chat message or terminal session can disappear. A ticket does not depend on either one. It keeps the
title, project, source, priority, current owner, proof, workflow, and ordered history together.

This lets a new person answer simple questions without reconstructing an old session:

- What result was promised?
- Who is accountable now?
- What step is active?
- What proof supports completion?
- What changed, and in what order?

## The parts you will see

- **Priority** states urgency. The available values are `P0`, `P1`, and `P2`.
- **Source** states where the work came from.
- **Custodian** is the one person or agent accountable for the ticket now.
- **Assignee** is a person or agent doing a specific part of the work. This can differ from the custodian.
- **Version** is a number that changes after an accepted update. Ctower uses it to refuse an update based
  on an old copy of the ticket.
- **Timeline** is the ordered history. Old events are not rewritten.

## How a ticket changes

A new ticket starts open. It can be admitted into active work, deferred until a later review time, blocked,
unblocked, resolved, closed, or reopened. Reopening starts a new lifecycle episode. A **lifecycle episode**
is one open-to-close period on the same ticket.

The workflow stage and the Board lane are separate facts. A blocked ticket keeps its stage. Changing an
assignee does not change the ticket identity or erase proof.

## How to use a ticket

On the local shadow browser, open `/board` and select a card. The ticket page shows the record that the
browser can read. The browser does not create or edit tickets.

From the command line, use:

```text
ctl ticket query <ticket-id> --project-key <project>
ctl ticket timeline <ticket-id> --project-key <project>
ctl ticket assignments <ticket-id> --project-key <project>
```

Use `ticket create` or `ticket capture` to create a ticket when you have an authorized command-line
credential. Writes may be queued when off-host acknowledgement is still pending. Do not repeat a write
with a new command identity. Drain the local spool instead.

See the [CLI reference](../reference/cli.md#ticket-capture-and-reads) for exact flags.
