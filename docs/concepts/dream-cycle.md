# Dream cycle

The **dream cycle** is a nightly review routine. It asks a high-capability model to review recent work and
produce a durable output for one project or for the whole portfolio.

## Why the dream cycle exists

Teams repeat mistakes when lessons remain in chat or in one person's memory. The dream cycle creates a
scheduled review effect and joins its output fingerprint back to the exact routine occurrence that asked
for it.

The schedule creates an effect. It does not trust a caller to state which project, crew, model, or lane is
authorized. Ctower reads those facts from saved scope and binding records.

## What happens each night

At 02:00 UTC, four routines create one effect each: one for every configured project and one for the full
portfolio. Each effect names the review skill and the required model class. A project seat can see only its
project effect. An operator can see the project effects and the portfolio effect.

An authorized consumer runs the review and returns only a lowercase SHA-256 output digest. A **SHA-256
digest** is a fixed-length content fingerprint. Ctower records the digest, the occurrence, and the
substrate-reported execution facts together.

## How to use the cycle

List the effects you are allowed to see:

```text
ctl dream-dispatch list
```

After producing the review artifact, consume the effect with its digest:

```text
ctl dream-dispatch consume <effect-id> --output-digest sha256:<64-lowercase-hex-characters>
```

The operator performs a one-time lane-binding ceremony before consumption can prove the required execution
route. A mistaken binding cannot be edited or deleted. Recovery uses a new versioned lane reference.

The dream cycle does not close tickets, pass their gates, or grant cross-project access.
