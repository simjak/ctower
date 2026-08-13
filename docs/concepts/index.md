# Concepts

This section explains the words that ctower uses. Each page answers three questions:

1. What is it?
2. Why does it exist?
3. How do I use it?

Start with [Tickets](tickets.md). Then read [Stages](stages.md) and [Gates](gates.md). Those three
ideas explain how ctower keeps work and proof together.

| You want to understand | Read |
|---|---|
| The permanent record for one promised result | [Tickets](tickets.md) |
| Captured operator intent and outcome accountability | [Requests](requests.md) |
| Safe review of suggested Request maintenance | [Request-maintenance proposals](request-maintenance-proposals.md) |
| Dated, byte-exact operator agreements and corrections | [Rulings](rulings.md) |
| Daily decisions, Rulings, executions, and proof | [Morning digest](morning-digest.md) |
| The steps that work follows | [Stages](stages.md) |
| The checks that can allow or refuse a move | [Gates](gates.md) |
| Durable roles and the short-lived teams that fill them | [Seats and crews](seats-and-crews.md) |
| Two-person messages and turning a thread into work | [Chat](chat.md) |
| The read-only view of a live work terminal | [Terminal read](terminal-read.md) |
| Exact grants, encrypted output, and bounded private Console streams | [Console view grants](console-viewer.md) |
| Work that becomes due on a schedule | [Routines](routines.md) |
| The nightly review that produces a durable output | [Dream cycle](dream-cycle.md) |
| One project's work and the cross-project summary | [Boards and portfolio](board.md) |

## A few more terms

A **workflow** is a versioned set of stages and allowed moves. Versioned means that a saved copy has a
fixed identity. A ticket keeps using the exact workflow version that it started with.

**Evidence** is a saved fact that supports a completion claim. A test result is one example. A **verdict**
is a recorded pass or fail decision about that evidence. Read [Proof](proof.md) for the full explanation.

A **projection** is a read-only view built from saved facts. The Board and Portfolio are projections. You
cannot edit them directly.

A **refusal** is a safe no. Ctower changes nothing and tells you which rule was not met.

## Current boundary

Ctower is pre-alpha. The browser described here is a local shadow view for replaceable work. A **shadow
view** is a copy used for testing and inspection. It is not the final product and it is not the only record
of the work. The command line and HTTP API remain the exact public development surfaces.

These pages explain current behavior. The [CLI reference](../reference/cli.md) lists exact commands and
flags. The [HTTP API reference](../reference/http-api.md) lists exact operations.
