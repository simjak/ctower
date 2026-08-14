# Refusals

ctower refuses with a typed problem document rather than a generic error. The `code` field is a closed
enumeration of **96 values** declared in `contracts/http/openapi.yaml`. If you see a code that is not on this
page, the contract changed and this page is a defect. Twelve codes from the project-seat credential surface
(`credential-*`, `seat-*`, `project-grant-required`, `project-scope-denied`) are not yet grouped below; the
ones you are most likely to meet are described in
[Project credential commands](../reference/cli.md#project-seat-credentials).

The point of the enumeration is that a caller can branch on it. This page groups every code by **what you
should do about it**.

## The problem document

| Field | Required | Notes |
|---|---|---|
| `type` | yes | URI identifying the problem type |
| `title` | yes | Short human summary |
| `status` | yes | HTTP status, 400–599 |
| `code` | yes | One of the 96 values below |
| `detail` | yes | Human-readable specifics |
| `command_id` | no | Correlates to your idempotency key |
| `current_version` | no | The server's actual version, on version conflicts |
| `unmet_facts` | no | Exactly which preconditions were missing |
| `prohibited_classes` | no | Exactly which prohibited data classes were detected, by stable name |

The CLI writes the problem document to **stderr** and exits `69`.

## Decision table

| If the code is… | It means | Do |
|---|---|---|
| `durability_pending` | Committed here, not yet acknowledged off host | **Wait and replay the same key.** Honour `Retry-After`. This is not an error |
| `version-conflict` | Someone else changed the aggregate | Re-read, re-evaluate your intent, re-issue with `current_version` |
| `idempotency-conflict` | Same key, different semantics | You have a bug. Do not retry. Either replay the original content or use a new key for genuinely new content |
| `validation-error` | The request shape is wrong | Fix the request. Never retry unchanged |
| `unauthorized`, `tenant-scope-denied` | Credential or scope problem | Escalate. Do not retry with the same credential |
| `prohibited-data-class` | The submission carries data ctower may not hold | **Terminal for that item.** Do not redact and resubmit; record the named class and stop |
| anything `workflow-*` | A pin, predicate, or declared-transition problem | Read `unmet_facts`. Satisfy the named fact, then act |
| anything `proof-*` | Criteria, evidence, or verdict problem | Read below. Most are permanent until you produce different evidence |
| anything `*-unchanged` | The mutation would be a no-op | Treat as already-done, not as failure |
| anything `*-conflict` on an ID you supplied | You reused an ID for different content | Use a fresh ID for genuinely new content |
| everything else | A domain refusal | Read `detail`. Do not retry unchanged |

The default is: **a typed refusal is permanent until you change something.** `durability_pending` is the
only code on this page that a plain retry can resolve.

## The catalogue

### Authorization and scope (2)

`tenant-scope-denied`, `unauthorized`

Escalate. Retrying with the same credential produces the same refusal.

### Request shape and replay (4)

`idempotency-conflict`, `request-body-too-large`, `validation-error`, `version-conflict`

`request-body-too-large` means the body exceeded the declared bound; send less, do not retry unchanged.
Only `version-conflict` is recoverable in-loop, and only by re-reading first. See
[Rule 2](operating-contract.md#rule-2-you-supply-the-expected-version-and-you-read-it-back-from-refusals).

### Durability (1)

`durability_pending`

The one retryable code. See [Durability and acceptance](../concepts/durability.md).

### Bootstrap (4)

`bootstrap-consumed`, `bootstrap-expired`, `bootstrap-nonempty`, `bootstrap-origin`

The first-tenant ceremony is one-use. `bootstrap-consumed` means it already ran — that is a correct refusal,
not a race to retry through.

### Work and tickets (15)

`ticket-comment-ineligible`, `ticket-comment-invalid`, `work-assignment-kind-refused`,
`work-assignment-target-ineligible`, `work-assignment-unchanged`, `work-blocker-already-resolved`,
`work-blocker-id-conflict`, `work-blocker-owner-ineligible`, `work-blocker-unknown`, `work-intent-unmet`,
`work-priority-unchanged`, `work-relation-cycle`, `work-relation-exists`, `work-reopen-unmet`,
`work-ticket-terminal`

Notable ones:

- `work-intent-unmet` and `work-reopen-unmet` — the precondition for the intent is not satisfied. The
  refusal is the answer; do not poll for it to become true on its own.
- `work-assignment-unchanged` and `work-priority-unchanged` — your mutation is a no-op. The desired state
  already holds. Treat as success for planning purposes.
- `work-ticket-terminal` — the episode is closed or cancelled. Reopen creates a new episode; it does not
  reactivate the old one.
- `work-relation-cycle` and `work-relation-exists` — the graph refuses rather than silently deduplicating.

### Workflow (9)

`workflow-already-started`, `workflow-not-terminal`, `workflow-pin-mismatch`,
`workflow-predicate-unsatisfied`, `workflow-run-not-started`, `workflow-state-conflict`,
`workflow-terminal`, `workflow-transition-not-declared`, `workflow-version-unknown`

Notable ones:

- `workflow-pin-mismatch` — the digest you supplied is not the pinned revision's digest. Common cause:
  hashing the pack file instead of using the canonical workflow-graph digest. Recomputing the same wrong way
  will fail identically.
- `workflow-predicate-unsatisfied` — the transition is declared but its guard is not met. **`unmet_facts`
  names exactly what is missing.** Satisfy that, then transition.
- `workflow-transition-not-declared` — the graph has no such edge. This is a modelling error, not a state
  problem.
- `workflow-already-started`, `workflow-run-not-started`, `workflow-terminal`, `workflow-not-terminal` —
  ordering errors. Read the run state before re-issuing.

### Proof (17)

`proof-candidate-author-mismatch`, `proof-candidate-digest-invalid`, `proof-candidate-digest-not-current`,
`proof-candidate-unchanged`, `proof-criteria-already-frozen`, `proof-criteria-invalid`,
`proof-criteria-policy-mismatch`, `proof-criterion-unknown`, `proof-current-evidence-missing`,
`proof-evidence-digest-mismatch`, `proof-evidence-id-conflict`, `proof-incomplete`, `proof-policy-mismatch`,
`proof-policy-pin-mismatch`, `proof-protected-authority-required`, `proof-self-review-refused`,
`proof-verdict-id-conflict`

Notable ones:

- `proof-self-review-refused` — you froze the criteria, so you are the candidate's author and cannot record
  a verdict on this ticket. This is structural. There is no retry, no flag, and no custody manoeuvre that
  satisfies it: a different principal must record the verdict. It does **not** fire when you approve
  evidence you produced yourself but did not author the candidate for — that case is
  [specified and not enforced](../concepts/proof.md#verdicts-and-independence).
- `proof-candidate-digest-not-current` — the candidate moved. Your evidence is about an older artifact.
  Produce evidence for the current candidate; do not resubmit.
- `proof-evidence-digest-mismatch` — the content you supplied does not hash to the `artifact_digest` you
  claimed. Nothing was written.
- `proof-criteria-already-frozen` — criteria are frozen by design. They are superseded, never edited.
- `proof-incomplete` and `proof-current-evidence-missing` — a gate or resolution needs current proof that
  does not exist. Often the aftermath of
  [invalidation](../concepts/proof.md#invalidation): evidence that used to be valid no longer is.
- `proof-protected-authority-required` — the operation needs protected authority you do not hold.

### CompanyBundle (12)

`bundle-base-conflict`, `bundle-compatibility-refused`, `bundle-digest-mismatch`, `bundle-grant-refused`,
`bundle-independence-refused`, `bundle-no-effect-refused`, `bundle-not-active`, `bundle-plan-mismatch`,
`bundle-recovery-unavailable`, `bundle-reference-invalid`, `bundle-schema-invalid`,
`bundle-security-refused`

`bundle-plan-mismatch` and `bundle-base-conflict` mean the plan you are applying no longer matches the
active base. Re-plan and apply the fresh `plan_digest`; the active pointer was not moved. See the
[CompanyBundle guide](../guides/company-bundle.md).

### Migration and cutover (14)

`i1-7c-required`, `migration-alias-conflict`, `migration-capability-denied`,
`migration-correction-conflict`, `migration-digest-mismatch`, `migration-export-nondeterminism`,
`migration-fence-detected`, `migration-import-finalization-refused`, `migration-operation-drift`,
`migration-relation-invalid`, `migration-run-conflict`, `migration-signature-invalid`,
`migration-source-selection-drift`, `migration-source-tainted`

`i1-7c-required` is the refusal returned by the refusal-only cutover operations. It is the designed
response, not a transient state.

### Intake (3)

`intake-already-promoted`, `intake-promotion-ineligible`, `intake-source-conflict`

`intake-already-promoted` is usually success arriving twice: read the event and use the ticket it already
produced. `intake-promotion-ineligible` means this event cannot become a ticket in its current state — read
the thread rather than retrying. `intake-source-conflict` means the same source reference is already
recorded against different content; nothing changed.

### Prohibited data classes (1)

`prohibited-data-class`

Intake and Evidence refuse five prohibited classes before any byte, event, object, Evidence, or outbox row
commits. The refusal carries `prohibited_classes` — one or more of `credential_material`,
`production_customer_data`, `phi_hipaa_covered`, `pii_beyond_staff_identity`, `live_incident_indicator` — and
never echoes the offending content back to you.

This one is **terminal for the item**, not for the credential: nothing was written, so there is no state to
reconcile, and there is no flag that admits it. Carry a typed vault/credential reference instead of a secret
value, a source-host artifact ID instead of customer content, a de-identified control reference instead of
anything clinical, a staff work handle instead of personal identity, and a
retrospective control reference instead of a live incident indicator.

### Projections and operations (2)

`poison-not-found`, `project-delivery-unavailable`

`project-delivery-unavailable` means the projection would not be trustworthy. It is deliberately preferred
over serving a stale row.

## Local reason codes

Exit `74` is a **local** failure and does not produce a problem document. Instead the CLI emits a
`local_failure` object with a `reason_code` matching `^[a-z][a-z0-9_]{0,63}$`. These are your machine's
problem, not the server's:

| Reason | Meaning |
|---|---|
| `keyring_unavailable` | No usable Secret Service backend; the mutation was never spooled or sent |
| `credential_identity_mismatch` | The spooled command was enqueued under a different authority; quarantined without sending |
| `corrupt_record` | A spool record failed integrity checks; replay is blocked and untrusted fields are omitted |
| `format_incompatible` | A legacy spool record cannot satisfy the current chain contract |

Reason codes are normalized and truncated to 64 characters, and never carry detail that could leak a secret.

## Related

- [The agent operating contract](operating-contract.md) — the rules these codes serve.
- [Proof](../concepts/proof.md) — why the `proof-*` family exists.
- [HTTP API reference](../reference/http-api.md) — which operations return which statuses.
