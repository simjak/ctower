# Stages

A **stage** is one named step in a workflow. A **workflow** is the versioned set of stages and allowed
moves for a kind of work.

## Why stages exist

Work often needs more than one kind of activity. Planning, making, and checking are different jobs. Stages
make that order visible. They also let ctower refuse a move that the selected workflow does not allow.

A stage is not a Board lane. A stage describes the process step. A lane describes where the ticket appears
in the work index.

## The four stages that run today

The shipped development workflow has four stages:

1. **Capture** records the promise, source, priority, and accountable owner.
2. **Frame** records what must be true for the work to count as done.
3. **Verify** records evidence and a pass or fail verdict.
4. **Close** ends the ticket after ctower checks the current proof again.

Each move has a named condition. Capture to Frame needs an admitted, unblocked ticket. Frame to Verify needs
frozen completion criteria. Verify to Close needs current proof.

## How to use stages

Open a Board card to see the current stage. You can also use
`ctl ticket query <ticket-id> --project-key <project>`.

Authorized command-line users start the workflow and request each move. Ctower checks the saved workflow
version. It refuses an undeclared move or a move whose condition is not met. A refusal changes nothing.

The current workflow stays pinned to the exact version selected at start. **Pinned** means fixed to one
saved version and digest. A digest is a content fingerprint. Later workflow edits do not silently change a
ticket that is already in progress.

See [Gates](gates.md) for the checks that control proof-based moves and the
[CLI reference](../reference/cli.md#workflow) for exact commands.
