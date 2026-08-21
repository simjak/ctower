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

## Browser product status

The browser realization of Inbox is deferred to a separately activated future product-browser lane. No current
browser route, send box, or promotion control is implementation or evidence for this contract.

## How to use chat in the terminal

Use `ctl inbox list` to see threads and `ctl inbox read <thread-id>` to read one. Use `ctl inbox send` to
send and `ctl inbox ack` to record delivery or read state. Use `ctl inbox promote` when the discussion
becomes Board work.

The protected CLI is the current supported channel. See the [CLI reference](../reference/cli.md#inbox) for
exact command shapes; a future product browser must reuse the same server-resolved identity and authority.
