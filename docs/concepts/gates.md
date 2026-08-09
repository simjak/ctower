# Gates

A **gate** is a check that decides whether work may move forward. It reads saved facts. It does not trust a
card move, a chat claim, or a successful process exit by itself.

## Why gates exist

Without a gate, “done” can mean “someone said it was done.” Ctower needs a result that another person can
inspect. A gate ties the decision to the exact version of the work that was checked.

## What the shipped proof gate checks

The current four-stage workflow uses one proof rule for the move into Close and for final resolution. It
checks that:

- completion criteria were frozen before the check;
- each criterion has current evidence;
- candidate-dependent evidence matches the current candidate digest; and
- each criterion that needs a verdict has a passing verdict.

A **criterion** is one condition that must be true. **Evidence** is a saved fact that supports a criterion.
A **verdict** is a recorded pass or fail decision. A **candidate digest** is the fingerprint of the exact
work being checked.

The person who froze the criteria cannot record the passing verdict. The current implementation does not
also compare the verdict writer with the person who supplied the evidence.

## How to use a gate

First freeze the criteria against the candidate. Then add evidence. Ask an allowed second principal to
record the verdict. Finally, request the move or resolution.

If proof is missing, old, mismatched, or self-approved, ctower refuses the command. It names the missing
condition and writes no partial result.

The browser can display proof that the record exposes, but it is not the authority for a verdict. Use the
protected command line or HTTP API for proof writes. See [Proof](proof.md) and the
[CLI reference](../reference/cli.md#ticket-proof).
