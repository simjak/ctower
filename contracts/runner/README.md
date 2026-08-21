# Runner (harness-adapter seam) contracts

The authored data half of the harness-adapter seam (CT-I1-041, D72). The base seam contracts live
here: `harness-spec.schema.json`, the closed `harness-capability.schema.json` vocabulary it draws
from, and `credential-lease.schema.json`. CT-I1-044 adds a separate, refusal-oriented survey
contract and data document; it does not register a later-wave binding.

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

`later-wave-harness-survey.schema.json` and `later-wave-harness-survey.json` are authored
revision-pinned evidence for the four CT-I1-044 candidates. Every unanswered fact is explicit
`unverified`, so `configure`/`provide` remains undecidable and registration is refused. The
`deepseek` entry is a model disposition, not a HarnessSpec: its adapter work is zero and its
serving truth remains inherited from the Hermes profile route.

The survey schema is closed over exact revision-pinned source snapshots, exact question
ID/prompt pairs, the observation timestamp paired with those snapshots, and the complete
45-pair dependency matrix in `later-wave-harness-survey.matrix.json`. The matrix defines the
finite answer domains, candidate context, legal combinations, and two semantic families:
referential equality across fields (route/probe target, route/identity, and credential
pool/cache relationships) and evidence-type support for every verified answer kind. The
schema compiles those matrix laws into fail-closed refusals: a value that names an
incompatible route or cites an evidence source that cannot entail the claim is rejected,
rather than being accepted because another field looks plausible. It rejects non-null values
for `unverified` answers, unsupported evidence for a verified claim, unresolved evidence IDs,
contradictory refusal/liveness reasons, and candidate role/registration/liveness or answer
combinations that contradict the four declared dispositions. `tests/conformance/harness-adapter/test_survey_registration.py` is a
validation-only conformance proof: its bounded Hypothesis searches generate 278 pair-rule,
92 referential, and 91 evidence-support violations and must find zero that validate; it does
not execute or bind a harness.
