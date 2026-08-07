# Record-backed landing boundary check

A stage gate that does not constrain the real landing is theater. External SCM stays authoritative for the
merge it performs, so this repository binds it the only way it can: one status check on the change, which
resolves the ticket bound to it and reports whether the record already holds the proof that must precede
landing.

The check is a **pure reader**. It writes no authoritative state, mints no Evidence, fills no slot, and
passes no gate, so its verdict is never itself proof.

!!! warning "Current maturity"

    The check is built and proved against fixtures. The record read surface that supplies its input is
    Increment 2 carriage, so on this repository today the check has no answer to read, reports every fact
    as `STATE_UNKNOWN`, and refuses. Making it **required** in repository settings is an operator ceremony
    and has deliberately not been performed — a required check with no record answer would block every
    pull request.

## What it reports

The check resolves the **landing-boundary predecessor set**: every stage the ticket's own pinned Workflow
graph places before the stage carrying the landing boundary, with every required slot of each stage filled,
valid, and current on the candidate digest the change's head revision resolves to.

The set is derived from the pinned graph alone. No stage key, group key, or evidence kind appears in the
check, so a package that renames a stage — or a non-engineering Workflow that declares a different graph —
changes the reported set with no change to the check.

Each fact is reported separately as `pass`, `fail`, `flagged`, or `STATE_UNKNOWN`, named by its stage and its
unmet slot. The check is green only when every fact passes. `STATE_UNKNOWN` is a failure, never a caveat in a
green body and never an omitted row: an unproven fact and a disproven one both mean the record does not carry
the proof.

Refusal names are composed from the stage keys the record supplies:

| Reported name | Meaning |
|---|---|
| `missing-<stage>-evidence` | That stage's required slot set is unfilled, superseded, self-reported, not current, or unknown |
| `flagged-<stage>-verdict-tier` | A security-class or release-gating verdict on that stage was signed below the policy tier |
| `record-unavailable` | No record answer was supplied, or the record declared itself unavailable |
| `record-answers-a-different-change` | The answer does not name this repository, pull request, and head revision |
| `record-payload-invalid` | The answer does not satisfy its typed contract |
| `change-not-bound-to-ticket` | The record holds no Change fact binding this pull request to a ticket |
| `candidate-digest-unresolved` | The head revision resolves to no candidate |
| `pinned-workflow-unresolved`, `pinned-workflow-invalid`, `pinned-workflow-digest-mismatch` | The ticket's pinned graph is absent, unparseable, or does not match its digest |
| `landing-boundary-undeclared`, `landing-boundary-unreachable` | The checkpoint never declared its landing boundary, or the pinned graph places no path to it |

For `engineering.software-factory@1`, whose authored sequence is linear into `merge`, the set runs from
`intake` through `release-preflight`, so the two facts it carries at that boundary are the review fact and
the documentation fact over preflight: `missing-risk-derived-review-evidence` and
`missing-documentation-evidence`.

## What does not satisfy a fact

No label, comment, administrator merge, re-run, follow-up ticket, passing repository quality gate, or
reviewer assertion that documentation exists substitutes for a fact, and no protected operator waiver
reaches one. The record answer the check reads has no field for any of them, and the typed contract forbids
unknown fields, so a bypass cannot be expressed to the check at all.

The check never reads a branch name, a pull-request title, or a body. It resolves the ticket from the
record's own Change fact, so a change can never report its own evidence.

## Verdict-tier visibility

The routing chain degrades rather than stalls, so a security-class or release-gating verdict can be signed
by a weaker model than the policy tier while still looking, in the record, exactly like a full signature.
The check reads the model that actually signed and flags such a verdict for re-verification rather than
accepting it silently. The flagged stage's fact is not passing, so the check is red until the verdict is
re-signed at or above its floor.

The ranking and the per-class floors are authored data in `tools/landing_boundary/policy.toml`: tiers with a
rank, the models in each tier, and the minimum tier each verdict class owes. A model absent from every tier
ranks below all of them. A verdict class with no declared floor is never flagged on tier grounds.

## Running it

The reader is the module `tools.landing_boundary`. It takes the change identity from the checkout and the
facts from the record's answer:

```bash
python -m tools.landing_boundary \
  --repository simjak/ctower \
  --pull-request 199 \
  --head-revision "$(git rev-parse HEAD)" \
  --record path/to/record-answer.json
```

It exits `0` only when every fact passes, `1` on any refusal, and `2` on a malformed change identity or an
unreadable tier policy. `--json` emits the same verdict as a deterministic typed document.

The `landing boundary` workflow runs exactly that command on every pull request and reads the record answer
path from the `CTOWER_LANDING_BOUNDARY_RECORD` repository variable.

## Operator ceremony: making the check required

Do this only once the record answers with real facts, or every pull request will be blocked.

1. Confirm the check reports a green verdict for a change whose ticket carries current review and
   documentation evidence, and refuses by name for one that does not.
2. Set the `CTOWER_LANDING_BOUNDARY_RECORD` repository variable to the path the record-read step writes on
   the runner.
3. In repository settings, add `landing boundary (record-backed)` to the branch protection rule for `main`
   as a required status check.
4. Leave administrator bypass off. The documentation fact is waivable at no tier, and an administrator merge
   satisfies nothing the check reports.

See [SPEC.md](https://github.com/simjak/ctower/blob/main/SPEC.md) for the record-backed landing boundary
narrative and [DECISIONS.md](https://github.com/simjak/ctower/blob/main/DECISIONS.md) for the decision that
grants it.
