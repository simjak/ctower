# Boards and portfolio

The **Board** is the read-only list of tickets for one project. The **Portfolio** is the read-only summary
across all configured projects.

Both are **projections**. A projection is a view rebuilt from saved facts. You do not drag a card to change
truth. You change the ticket, and the view updates from that change.

## Why there are two views

The Board helps a person work inside one project. The Portfolio helps an operator see where work and human
attention are concentrated across projects. Keeping them separate avoids mixing project authority while
still giving one cross-project view.

## The six Board lanes

- **Backlog** contains tickets that have not been admitted to active work.
- **Ready** contains admitted tickets with no active workflow.
- **In progress** contains active work stages.
- **In review** contains active verification stages.
- **Blocked** contains tickets with an open blocker that affects the Board.
- **Complete** contains resolved or closed tickets.

Blocked is an overlay. The card keeps the lane it will return to after the blocker is resolved. Complete
takes precedence over an old blocker.

The Board derives In review from the stage's activity class, not from the stage name. An **activity class**
states whether a stage is work or verification.

## What the Portfolio shows

Open `/portfolio` to see ticket counts by lane and project, items that need a human, and unread seat
messages. The view reads each configured project Board and one Inbox projection.

An unreachable Board is not shown as a project with zero work. It is excluded from totals and marked as not
reached. An Inbox identity that cannot receive messages is not shown as zero unread. Threads that cannot be
linked to a project stay in a separate unlinked count.

## How to use the views

Open `/board` and choose a project tab. Use the lane, priority, stage, owner, assignee, and source filters to
narrow the list. Select a card to open the ticket.

Open `/portfolio` when you need a cross-project check. Select a project row to move into its Board. The
Portfolio has no write controls.

From the command line, use `ctl board query <project>`. All filters are optional and combine. See the
[CLI reference](../reference/cli.md#board-and-health).

Always read the health and source notes. A missing or stale source is not an empty project.
