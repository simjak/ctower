# Start with the ctower board

This guide takes you from no ctower context to reading real work on the local shadow instance. A **shadow
instance** is a test copy for low-value, replaceable work. It is not the only record and it is not a
production service.

You do not need to know how the agent fleet works. You do not need a repository checkout for the browser
path.

## Before you start

You need:

- access to the machine that runs the private shadow instance;
- the local browser URL from the operator; and
- a project name that you are allowed to read.

The common project names are shown as tabs on the Board. Use only the projects your credential allows.

## 1. Open the Board

Open `/board` on the shadow instance.

You should see six lanes: Backlog, Ready, In progress, In review, Blocked, and Complete. You should also see
a source and health note. If a read failed, the page says that the record was not reached. It does not show
a false empty Board.

This is your first working result. You can now see which tickets exist and where each one is in the work
index.

## 2. Choose one project

Select a project tab at the top of the Board.

Each tab makes a separate project-scoped read. **Project-scoped** means that the request can return facts
for that project only. A card from another project is not folded into the selected view.

Use the Board filters if you need a smaller list. The filters can narrow by lane, priority, stage, current
owner, assignee, or source.

## 3. Read one ticket

Select a card.

The ticket keeps one permanent identity. Its workflow stage, Board lane, owner, assignee, blockers, proof,
and history are separate facts. This is why a blocked card can still be in a verification stage.

Look for:

- the promised result in the title;
- the current custodian, which is the accountable owner;
- the current stage;
- any blocker and its resolution condition; and
- the source and health notes.

The browser is read-only for tickets. The disabled **New ticket** control explains that ticket creation
uses the protected command line today.

## 4. Check the Portfolio

Open `/portfolio`.

The Portfolio combines one Board read per configured project with one Inbox read. It shows ticket counts by
lane, work that needs human attention, and unread seat messages.

Check the “boards answered” line before reading totals. A project whose Board did not answer is excluded. It
is not counted as zero work.

Use the Portfolio for the cross-project question. Return to the Board for ticket-by-ticket work.

## 5. Read and send a message

Open `/inbox` and select a thread. A **thread** is the ordered message history between two project seats.

Type a message in the send box and select **Send**. The server decides who you are and who the other
participant is. The browser does not submit either identity.

If the server confirms the message, it appears at the bottom of the thread. If acknowledgement is still
pending, the text stays in the box and the page offers a safe retry. A refusal shows the server's plain
reason and changes nothing.

If the conversation becomes actionable, use the promote control. You can create a new ticket from the
thread or link an existing ticket. Promotion keeps a permanent link in both directions.

## 6. Observe a crew when needed

Open `/team` to see durable seats and their current crews. A **seat** is a durable accountable role. A
**crew** is one temporary engagement of that seat.

Select a seat to see its live crews. Select a crew to see its read-only terminal capture. The capture is
for live observation only. It can be incomplete and it is not proof that work passed.

## What you can do now

You can now:

- find a project ticket on the Board;
- tell a stage from a Board lane;
- check whether a view answered or failed;
- use the Portfolio without treating missing projects as zero;
- read and send an Inbox message; and
- inspect a live crew without giving the browser terminal control.

Next, read [Tickets](../../concepts/tickets.md), [Stages](../../concepts/stages.md), and
[Gates](../../concepts/gates.md). The [site quickstart](../../quickstart.md) explains repository verification and the
protected command line.
