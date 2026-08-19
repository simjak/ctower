# Runner (harness-adapter seam) contracts

The authored data half of the harness-adapter seam (CT-I1-041, D72). Three contracts live here and
nothing else does: `harness-spec.schema.json`, the closed `harness-capability.schema.json`
vocabulary it draws from, and `credential-lease.schema.json`.

A `HarnessSpec` is **data**. It is parsed without executing package code — the shape D11 already
requires of every extension manifest — so a binding that cannot declare a capability does not
discover one at runtime, and an unknown, incompatible, revoked, or digest-mismatched spec is a
refusal rather than a fallback to a generic process.

Three fields carry most of the seam's weight:

- `survey` is the answered capability survey. It decides, per layer, whether ctower **configures**
  a layer the harness already ships or **provides** one it lacks — read from the answers and never
  from the harness's name. An unanswered survey leaves that role undecidable, which is a refusal
  rather than a gap, so the binding does not enter the conformance suite.
- `layers` declares the role the survey implies, and the two must agree. **Never both**: a native
  layer plus ctower's own over one credential set is not redundancy, it is a race over single-use
  refresh chains, which is the failure that revokes every grant derived from one login at once.
- `liveness_sources` declares what each observed fact is drawn from, and whether that source proves
  `serving` or only the `request`. A request-only source is recorded as a conflict and never as
  serving truth.

`credential-lease.schema.json` is what the sibling `CredentialPool` Interface returns from
`acquire`. It carries three orthogonal entry axes — `auth`, `quota`, `reach` — because a capped
account passes login and refuses work, a dead lineage may sit on untouched quota, and an entry with
both healthy can still be unreachable behind a challenged edge. It carries `secret_fingerprint` and
no field a credential value can occupy: secrets are references, never values.

These contracts activate no dispatch. Execution stays `not_exercised` at the component level;
`ctower-runner-sdk` parses this data and `ctower-runner` binds `hermes` to it.
