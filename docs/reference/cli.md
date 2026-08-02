# CLI reference

`ctowerctl`—also installed as `ctl`—is the protected development CLI. It exposes a closed set of authored
commands backed by the generated client. Unknown commands are usage errors; there is no arbitrary operation
dispatcher.

!!! warning "Development surface"
    The CLI is built and exercised as a verified wheel, but it is not published as a supported product
    package. The tested API is loopback-only and uses synthetic data.

## Requested journey: what is actually available

| Journey | Status | Current surface |
|---|---|---|
| Check the app is running | **Available** | `control health`; executed against the disposable loopback API by `just quickstart` |
| Create a project | **Unavailable** | No create-project operation or parser command exists. `project delivery query` is a read and currently accepts only `ctower` |
| Create a team or onboard another member | **Partially available** | There is no team or general member-management command. An Operator can issue or revoke one credential for an already configured project-seat identity with `credential seat issue/revoke` |
| Create a ticket | **Available** | `ticket create` or its alias `ticket capture` |
| Run the full workflow | **Available as a development fixture** | The tested path below reaches durable `resolved` and `closed` facts |

The unavailable rows are API and domain gaps, not undocumented flags. Adding examples for them would be
fiction.

## Run the executable reference

```bash
just quickstart
```

The run installs the CLI outside the checkout and executes `control health`, discovery, ticket creation,
admission, workflow start, all three transitions, criteria freeze, evidence, protected verdict, resolve,
and spool drains against a disposable PostgreSQL/API fixture. It ends with `4 passed` and removes its
temporary environment.

## Invocation

The grammar is `ctl [--base-url <url>] <area> <action> [<positional>] [--flags]`.

`--base-url` scopes every invocation, including local spool commands, because the spool is scoped per
origin. It may be omitted when the owner-only `~/.config/ctower/cli-instances.json` catalog declares exactly
one instance. Zero or multiple declared instances refuse with exit `64`; an explicit URL disambiguates. The
value must be absolute HTTP(S), may not contain credentials, query data, or a fragment, and may use cleartext
HTTP only on loopback.

Server commands read one bounded authority line from stdin. Authority is never a flag, environment value,
or output field. Commands in the tables below show grammar, not credential examples.

| Flag | Applies to | Notes |
|---|---|---|
| `--command-id` | Every mutation | Caller-supplied UUID becomes the idempotency key. Optional on every mutation; the CLI generates and prints one client-side when omitted |
| `--expected-version` | Version-guarded mutations | Optimistic concurrency; a mismatch is `version-conflict` |
| `--reason` | Authority and work mutations | Bounded metadata, never secret material |

## Exit codes

| Exit | Meaning | Safe response |
|---:|---|---|
| `0` | Read succeeded or mutation was accepted | Continue |
| `64` | Invocation or bounded input is invalid | Fix the command; nothing was sent |
| `69` | Typed permanent refusal or quarantine barrier | Read the problem code; do not retry unchanged |
| `74` | Local keyring, spool, filesystem, or integrity failure | Fix the local boundary; the command was not sent |
| `75` | Queued, temporarily unreachable, or `durability_pending` | Reuse the same command ID after waiting |

A mutation prints its `command_id`, local `state`, `reason_code`, and spool `sequence`, plus a current server
result when one exists. Exit `75` never means “try the same intent with a new ID.”

## Bootstrap

| Command | Required flags |
|---|---|
| `bootstrap first-tenant` | `--command-id`, `--tenant-name`, `--tenant-slug`, `--operator-name`, `--operator-credential-ref`, `--operator-vault-ref`, `--commander-name`, `--commander-vault-ref` |

This online-only, one-use ceremony creates the initial tenant and two principals. Every `*-ref` value is a
reference, never a secret value. It does not create a reusable onboarding flow.

## Project-seat credentials

| Command | Required input |
|---|---|
| `credential seat issue` | `--command-id`, `--credential-digest`, `--credential-ref`, `--display-name`, `--project-key`, one or more `--scope {capture,transition,evidence}`, and `--seat-key` |
| `credential seat revoke <credential_id>` | `--command-id` and `--reason` |

These are online-only Operator mutations and are never written to the replay spool. They bind or revoke a
credential for one configured `(project_key, seat_key)` identity; they do not create a project or team.
`--credential-ref` is an opaque secret-manager reference and `--credential-digest` is the lowercase
`sha256:` digest of bearer bytes retained outside ctower. Never put the bearer itself in a command,
environment variable, file, or documentation transcript.

## Ticket commands

### Create and read

| Command | Positional | Flags |
|---|---|---|
| `ticket create`, `ticket capture` | — | required `--priority {P0,P1,P2}`, `--source-kind`, `--source-ref`, `--title`; optional `--command-id`, `--initial-custodian-id` |
| `ticket query`, `ticket show` | `<ticket_id>` | — |
| `ticket timeline` | `<ticket_id>` | — |
| `ticket audit` | `<ticket_id>` | optional `--cursor`, `--limit` |
| `ticket assignments` | `<ticket_id>` | — |

Create generates a command ID when omitted. A Commander may establish their own initial custody. An
Operator must explicitly name an eligible Commander.

### Ownership and work

| Command | Required flags beyond `<ticket_id>` |
|---|---|
| `ticket comment add` | `--command-id`, `--body` |
| `ticket assign` | `--command-id`, `--expected-version`, `--reason`, `--kind`, `--to-principal-id`; optional `--scope-ref` |
| `ticket custody transfer` | `--command-id`, `--expected-version`, `--reason`, `--from-custodian-id`, `--to-custodian-id`, `--protected-transfer` |
| `ticket prioritize` | `--command-id`, `--expected-version`, `--reason`, `--priority`; optional `--urgent-evidence-ref` |
| `ticket admit`, `ticket reopen` | `--command-id`, `--expected-version`, `--reason` |
| `ticket defer` | the common mutation flags plus `--review-after` with a UTC offset |
| `ticket block` | the common mutation flags plus blocker ID/kind, reason class, owner, source, resolution condition, and an explicit board-impact choice |
| `ticket unblock` | the common mutation flags plus `--blocker-id`, `--resolution-evidence-ref` |
| `ticket relation add` | the common mutation flags plus `--kind`, `--target-ticket-id` |

Assignment and custody are different. Assignment names a worker role; custody names the single accountable
principal and is a protected atomic transfer.

### Workflow and proof

| Command | Required input |
|---|---|
| `ticket workflow list` | none; local installed-pack discovery |
| `ticket workflow start <ticket_id>` | `--command-id`; optional complete set of four ref/digest pairs |
| `ticket transition <ticket_id>` | `--command-id`, `--expected-version`, `--workflow-ref`, `--source-stage`, `--destination-stage` |
| `ticket criteria freeze <ticket_id>` | `--command-id`, `--expected-version`, exactly one candidate content/digest; optional criteria file |
| `ticket evidence add <ticket_id>` | `--command-id`, `--expected-version`, `--evidence-id`, exactly one content/file; optional criterion and digests |
| `ticket gate verdict <ticket_id>` | `--command-id`, `--expected-version`, `--verdict-id`, `--decision {pass,fail}`; optional criterion/candidate digest |
| `ticket resolve <ticket_id>` | `--command-id`, `--expected-version`; optional workflow ref |

With exactly one installed executable workflow, start and proof commands can resolve the sole authored
revision and criterion. Explicit refs and digests remain authoritative and are refused on mismatch.

The shipped workflow is:

```text
capture --entry.ready@1--> frame --criteria.frozen@1--> verify --proof.current@1--> close
```

| Command | Positional | Flags |
|---|---|---|
| `ticket criteria freeze` | `<ticket_id>` | required: `--expected-version` (≥ 0), exactly one of `--candidate-content` or `--candidate-digest`; optional: `--command-id`, `--criteria-file` |
| `ticket evidence add` | `<ticket_id>` | required: `--expected-version` (≥ 1), `--evidence-id`, exactly one of `--content` or `--content-file`; optional: `--command-id`, `--criterion-key`, `--candidate-digest`, `--artifact-digest` |
| `ticket gate verdict` | `<ticket_id>` | required: `--expected-version` (≥ 1), `--verdict-id`, `--decision {pass,fail}`; optional: `--command-id`, `--criterion-key`, `--candidate-digest` |

Digests are `sha256:` followed by exactly 64 lowercase hex characters. Candidate and evidence literal
content is hashed as exact UTF-8 bytes. With one installed Workflow revision and one criterion,
`--criteria-file` and `--criterion-key` default to that exact gate policy. Evidence omitting
`--candidate-digest` binds server-side to the frozen current candidate; omitting `--artifact-digest`
computes it from the supplied content. Proof receipts state the resolved candidate digest and, for evidence,
the artifact digest. Explicit values remain authoritative and a stale candidate or wrong artifact digest is
refused. Evidence content is capped at 100 000 characters by the contract.

The principal recording a verdict must differ from the principal who ran `ticket criteria freeze` — the
candidate's author — or the request is refused as `proof-self-review-refused`. It must also hold protected
operator authority, or the request is refused as `proof-protected-authority-required`. The reviewer is
**not** compared with the principal who supplied the evidence; see
[verdicts and independence](../concepts/proof.md#verdicts-and-independence).

## Ticket: workflow {#workflow}

| Command | Positional | Flags |
|---|---|---|
| `ticket workflow list` | — | — |
| `ticket workflow start` | `<ticket_id>` | `--command-id`; optionally all four ref/digest pairs (`--workflow-ref`, `--workflow-digest`, …) |
| `ticket transition` | `<ticket_id>` | `--command-id`, `--expected-version`, `--workflow-ref`, `--source-stage`, `--destination-stage` |
| `ticket resolve` | `<ticket_id>` | `--command-id`, `--expected-version`; optional `--workflow-ref` |

Refs match `<key>@<revision>`, for example `ctower.trust-spine-four-stage@1`. Digests must match the pinned
revision's canonical graph digest, not the digest of the pack file on disk. See
[workflow pinning](../concepts/workflows.md#pinning-what-start-actually-does).

`ticket workflow list` enumerates coherent `staged` or `published` revisions from the installed pack tree
and prints the exact eight values accepted by `start`. When exactly one revision is installed, omitting all
eight start flags selects it and writes those exact pins into the spooled request. Supplying only some pins
is a usage error. An omitted resolve ref is resolved by the server from the run's persisted immutable ref;
the committed result names that exact ref. If discovery lists zero or multiple revisions, start requires an
explicit complete selection.

## Intake

| Command | Positional | Flags |
|---|---|---|
| `intake submit` | — | required: `--project-key`, `--source-kind`, `--source-ref`, `--content-file`; optional: `--command-id`, `--intent {discussion,create_ticket,link_ticket}` (default `discussion`), `--taint {authenticated,external_untrusted,quarantine_required}` (default `authenticated`), `--thread-id`, `--expected-thread-version`, plus the ticket fields below |
| `intake promote` | `<inbound_event_id>` | required: `--expected-thread-version`, `--intent {create_ticket,link_ticket}`; optional: `--command-id`, the ticket fields below |

## Board and project reads

| Command | Flags |
|---|---|
| `board query` | optional lane, priority, stage, custodian, assignee, source kind/ref |
| `project delivery query ctower` | optional `--output {text,json}` |
| `control health` | none |

All are online reads and never spooled. `project delivery query` does not create or configure a project.

## Company bundle

| Command | Input |
|---|---|
| `company bundle validate` | `<bundle_file>` |
| `company bundle plan` | `<bundle_file>` |
| `company bundle apply` | `<bundle_file>`, `--command-id`, `--expected-active-version`, `--plan-digest` |
| `company bundle export` | none |

CompanyBundle moves one future-only Catalog pointer. It does not activate teams, runners, effects, or a
production configuration.

## Synthetic workflow

| Command | Input |
|---|---|
| `synthetic run` | `--workflow ctower.trust-spine-four-stage@1`, `--wait`, `--assert resolved,closed`; optional `--command-id` |
| `synthetic query` | `<run_id>` |

`synthetic run` is the server-side whole-lifecycle operation. The quickstart instead exercises the
individual public CLI steps so each boundary remains visible.

## Operations and migration

`ops outbox poison dispose` requires an outbox ID, command ID, consumer key, topic, action, and reason.

The `migration ctower-project` family contains `inventory`, `export`, `plan`, `import`, `reconcile`,
`run get`, `correction append`, `fence observe`, `prepare`, `commit-development-epoch`, and `verify`. These
commands are online-only. `prepare` and `commit-development-epoch` are intentional refusal-only surfaces;
they do not activate cutover.

Text output prints checkpoint summary and source/reason lines, followed by one line per qualifying slot:
`slot=<key> state=<state> assigned=<seat>|unassigned signed=<seat>|-`. A rendered seat is
`<label>[<seat_key>]@<catalog_key>@<revision>`. Assignment is selected by the explicit `assigned` or
`unassigned` state in the HTTP response, and a missing signing seat renders as `-`.

## Local spool

| Command | Purpose |
|---|---|
| `spool status` | Count pending, archived, and quarantined records |
| `spool list` | List records, optionally by state |
| `spool quarantine list` | List bounded quarantine rows |
| `spool doctor` | Verify local chain and keyring health |
| `spool drain` | Replay in order with current stdin authority |
| `spool retry <sequence>` | Explicitly release one quarantined sequence with a reason |
| `spool discard <sequence>` | Append a discard disposition; optional exact artifact digest |

The spool is encrypted, origin-scoped, owner-only, and durable-before-send for allowed mutations. Never edit,
copy, or delete its files manually.

A listed entry quarantined by the server also carries `server_refusal` (`status` and a `name` that is either
an authored refusal code or the content-free sentinel `unrecognized_refusal`, never response body text); an
entry quarantined locally — `credential_identity_mismatch`, `expired`, `corrupt_record` — carries its
`reason_code` and no `server_refusal`.

## Contract sources

- Parser and flag truth: `apps/ctowerctl/src/ctowerctl/_parser.py`
- HTTP operation truth: `contracts/http/openapi.yaml`
- Generated replay policy: `generated/python/ctower_client/operations.py`
- Agent retry/refusal rules: [Agent operating contract](../agents/operating-contract.md)
