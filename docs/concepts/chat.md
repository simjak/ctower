# Chat

Ctower **chat** is a two-person thread in **Inbox**, the place for durable messages that are not Board
work, between **project seats**, durable project-scoped roles that can send and receive those messages. A
**thread** is the ordered list of messages shared by the same two participants.

## Why chat exists

Work often starts as a short exchange. Ctower keeps that exchange durable without forcing every message
onto the Board. When the exchange becomes actionable, an authorized user can promote the thread into a new
ticket or link it to an existing ticket.

Both message directions use the same thread. Reading a thread does not mark it read. Delivery and read
acknowledgements are separate saved facts.

## How to use chat in the browser

Open `/inbox`. Select a thread. Type in the send box and select **Send**.

The browser sends only the message text and the thread identity. The server reads the recipient from its
own record and derives the sender from its credential. A pending acknowledgement does not appear as a sent
message. The text remains in the box so the same command can be retried safely.

Use the promote control to create a ticket from the first message or link an existing ticket. A thread can
be promoted only once. A refusal leaves the thread and ticket unchanged.

## How to use chat in the terminal

Use `ctl inbox list` to see threads and `ctl inbox read <thread-id>` to read one. Use `ctl inbox send` to
send and `ctl inbox ack` to record delivery or read state. Use `ctl inbox promote` when the discussion
becomes Board work.

The local browser controls are a server-mediated dogfood surface. They are not a general chat product. See
the [CLI reference](../reference/cli.md#inbox) for exact command shapes.
