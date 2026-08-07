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
| Onboard a project | **Available to an Operator, as configuration** | Through the CompanyBundle: `company bundle validate` → `plan` → `apply`. There is no `project create` command and no self-serve path — see [Onboard a project](#onboard-a-project) |
| Create a team or onboard another member | **Partially available** | There is no team or general member-management command. A project's starter checkpoints and their accountable seat keys are bundle resources; an Operator then binds one credential per already-configured project-seat identity with `credential seat issue/revoke` |
| Create a ticket | **Available** | `ticket create` or its alias `ticket capture` |
| Run the full workflow | **Available as a development fixture** | The tested path below reaches durable `resolved` and `closed` facts |

The partially-available row is an API and domain gap, not an undocumented flag; adding examples for it
would be fiction. Onboarding is not a gap — it is a deliberate shape. Self-serve project onboarding, the
thing that does not exist, is tracked as [issue #212](https://github.com/simjak/ctower/issues/212).

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
| `bootstrap first-tenant` | `--tenant-name`, `--tenant-slug`, `--operator-name`, `--operator-credential-ref`, `--operator-vault-ref`, `--commander-name`, `--commander-vault-ref`; optional `--command-id` |

This online-only, one-use ceremony creates the initial tenant and two principals. Every `*-ref` value is a
reference, never a secret value. It is not itself the onboarding flow: projects arrive through the
CompanyBundle below.

## Onboard a project

| Command | Input |
|---|---|
| `company bundle validate` | `<bundle_file>` |
| `company bundle plan` | `<bundle_file>` |
| `company bundle apply` | `<bundle_file>`, `--expected-active-version`, `--plan-digest`; optional `--command-id` |
| `company bundle export` | none |

A project is not created by a command. It is a `kind: project` resource inside the CompanyBundle, published
by an Operator over the same authenticated command API the UI uses. The checked-in
`company/company.bundle.yaml` carries the three configured projects — `ctower.control-plane`,
`manibo.delivery`, `bh-loop.delivery` — beside the `kind: checkpoint` resources that give each project its
starter checkpoints and name the seat accountable for each.

Adding a project therefore means adding its `project` resource, its checkpoints, and their assignments to
the bundle, then running validate → plan → apply. Nothing about the sequence is project-specific.

### The run

Against a disposable loopback instance and the checked-in bundle. Authority is one bounded line on stdin,
never a flag.

```console
$ ctl --base-url http://127.0.0.1:38677 company bundle validate company/company.bundle.yaml
{"bundle_digest":"sha256:3550c774...","checks":[{"code":"schema.closed","status":"passed"},
{"code":"digest.canonical","status":"passed"},{"code":"reference.exact","status":"passed"},
{"code":"compatibility.current","status":"passed"},{"code":"security.secret-free","status":"passed"}],
"valid":true,"warnings":[]}
```

`validate` is a pure read. Its five named checks are the whole verdict; `valid` is never inferred from an
absent error.

```console
$ ctl --base-url http://127.0.0.1:38677 company bundle plan company/company.bundle.yaml
{"actions":[ ... {"component":{"key":"bh-loop.delivery","kind":"project","revision":1},"kind":"create"},
{"component":{"key":"ctower.control-plane","kind":"project","revision":1},"kind":"create"},
{"component":{"key":"manibo.delivery","kind":"project","revision":1},"kind":"create"} ... ],
"base_version":0,"plan_digest":"sha256:b65365a5...","proposed_bundle_digest":"sha256:3550c774...",
"warnings":[]}
```

`plan` is also a read, and it is where a project's arrival is visible: three `create` actions on `kind:
project` components, beside the `create` actions for the checkpoint set. `base_version` is the currently
active bundle version — `0` when no bundle has ever been applied.

```console
$ ctl --base-url http://127.0.0.1:38677 company bundle apply company/company.bundle.yaml \
    --command-id 9bcccc10-1eba-40ec-b10b-103b77bc8316 \
    --expected-active-version 0 \
    --plan-digest sha256:b65365a5...
{"command_id":"9bcccc10-...","reason_code":"durability_pending","state":"queued",
 "result":{"active_version":1,"bundle_digest":"sha256:3550c774...","durability_state":"durability_pending",
 "event_ids":[...],"plan_digest":"sha256:b65365a5..."},"sequence":1}
```

Exit `75`, not `0`. `apply` is a durable mutation: it enters the encrypted spool, reports
`durability_pending`, and is completed by `spool drain` with the same command ID. `--plan-digest` must be
the `plan_digest` printed by the plan you actually read, and `--expected-active-version` must be the
version that plan reported; either one stale is a refusal, not a silent re-plan.

```console
$ ctl --base-url http://127.0.0.1:38677 company bundle export
assignments:
- component:
    content_digest: sha256:17288c4f...
    key: commander.protected-cli
    kind: agent_profile
    revision: 1
  slot: agent_profile
  subject: principal:commander
company:
  display_name: Ctower
  key: ctower
resources:
...
```

`export` emits the active bundle as canonical YAML with no runtime state. Planning that export against the
same instance returns `{"actions":[]}` at `base_version: 1` — the round trip carries zero semantic diff,
which is what makes the exported file a safe starting point for the next revision.

CompanyBundle moves one future-only Catalog pointer. It does not activate teams, runners, effects, or a
production configuration.

### Why there is no `project create`

This is a specified shape, not a missing feature.

- `docs/internal/SPEC.md`, *Portfolio topology, shadow boundary, and project grants*: the configured project
  keys "are ordinary Project component data under one CompanyBundle, not product-code branches, separate
  tenants, or separate databases."
- The same section's authorization table, row *Apply Project/checkpoint/seat configuration*: it is an
  "Operator-only CompanyBundle command." A project Commander "may author/propose a revision but cannot apply
  it," and the `capture` scope is explicitly not granted "Catalog/CompanyBundle apply."
- INV-47 states the general rule: CompanyBundle is transport — validate, plan, apply, and export through
  authenticated commands.

The CLI cannot drift from that on its own.
`tests/modules/ctowerctl/test_cli_boundaries.py::test_parser_exposes_every_authored_name_without_operation_dispatch`
asserts `authored_command_names() == frozenset(CLI_OPERATIONS)`: the parser's closed command set must equal
the generated contract's operation set exactly. A `project create` command cannot be added by editing the
parser; it would need an authored HTTP operation, which the specification does not grant.

[Issue #212](https://github.com/simjak/ctower/issues/212) holds the open question — whether a project
commander should be able to self-serve onboarding — as an operator decision between two options, not as an
implementation task:

- **(a)** the CompanyBundle path above is *the* onboarding route, documented as such. This page is that
  answer written down.
- **(b)** a specification amendment authorizes a self-serve create-project under D30's per-project grants.
  That is a change to the rows quoted above, because it moves project creation out of operator-only
  CompanyBundle apply, and it would then need an authored HTTP operation before any CLI command could exist.

Until (b) is decided and amended, (a) is what the product does, and the sequence on this page is the
onboarding path.

## Project-seat credentials

| Command | Required input |
|---|---|
| `credential seat issue` | `--credential-digest`, `--credential-ref`, `--display-name`, `--project-key`, one or more `--scope {capture,transition,evidence}`, and `--seat-key`; optional `--command-id` |
| `credential seat revoke <credential_id>` | `--reason`; optional `--command-id` |

These are online-only Operator mutations and are never written to the replay spool. They bind or revoke a
credential for one configured `(project_key, seat_key)` identity; the project and the seat must already
exist in the applied bundle, and these commands do not create either, nor a team.
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

The CLI generates a command ID when omitted. A Commander may establish their own initial custody. An
Operator must explicitly name an eligible Commander.

### Ownership and work

| Command | Required flags beyond `<ticket_id>` |
|---|---|
| `ticket comment add` | `--body`; optional `--command-id` |
| `ticket assign` | `--expected-version`, `--reason`, `--kind`, `--to-principal-id`; optional `--command-id`, `--scope-ref` |
| `ticket custody transfer` | `--expected-version`, `--reason`, `--from-custodian-id`, `--to-custodian-id`, `--protected-transfer`; optional `--command-id` |
| `ticket prioritize` | `--expected-version`, `--reason`, `--priority`; optional `--command-id`, `--urgent-evidence-ref` |
| `ticket admit`, `ticket reopen` | `--expected-version`, `--reason`; optional `--command-id` |
| `ticket defer` | the common mutation flags plus `--review-after` with a UTC offset |
| `ticket block` | the common mutation flags plus blocker ID/kind, reason class, owner, source, resolution condition, and an explicit board-impact choice |
| `ticket unblock` | the common mutation flags plus `--blocker-id`, `--resolution-evidence-ref` |
| `ticket relation add` | the common mutation flags plus `--kind`, `--target-ticket-id` |

Assignment and custody are different. Assignment names a worker role; custody names the single accountable
principal and is a protected atomic transfer.

### Board context and Attention

| Command | Required input |
|---|---|
| `ticket change-reference add <ticket_id>` | `--repository`, `--change-identity`, `--reference`; optional `--command-id` |
| `ticket label apply <ticket_id>` | `--label-key`; optional `--command-id` |
| `attention finding append` | `--subject-ticket-id`, `--kind-key`, `--reason-code`, `--effective-owner {operator,commander}`, `--recommendation`, one or more `--alternative`, `--consequence`, `--dedupe-key`, one or more `--source-fact`; optional `--command-id`, `--deadline` |
| `attention finding disposition <finding_id>` | `--outcome {resolved,snoozed,expired,superseded,cancelled}`, `--reason`; optional `--command-id` |

Change references and labels populate recorded Board-card context; they are never inferred from repository
names or arbitrary label text. An Attention finding is an append-only, typed request for an exact human
action. Disposition records its outcome instead of making the finding disappear.

### Workflow and proof

| Command | Required input |
|---|---|
| `ticket workflow list` | none; local installed-pack discovery |
| `ticket workflow start <ticket_id>` | optional `--command-id` and complete set of four ref/digest pairs |
| `ticket transition <ticket_id>` | `--expected-version`, `--workflow-ref`, `--source-stage`, `--destination-stage`; optional `--command-id` |
| `ticket criteria freeze <ticket_id>` | `--expected-version`, exactly one candidate content/digest; optional `--command-id`, criteria file |
| `ticket evidence add <ticket_id>` | `--expected-version`, `--evidence-id`, exactly one content/file; optional `--command-id`, criterion and digests |
| `ticket gate verdict <ticket_id>` | `--expected-version`, `--verdict-id`, `--decision {pass,fail}`; optional `--command-id`, criterion/candidate digest |
| `ticket resolve <ticket_id>` | `--expected-version`; optional `--command-id`, workflow ref |

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
| `ticket workflow start` | `<ticket_id>` | optional `--command-id` and all four ref/digest pairs (`--workflow-ref`, `--workflow-digest`, …) |
| `ticket transition` | `<ticket_id>` | `--expected-version`, `--workflow-ref`, `--source-stage`, `--destination-stage`; optional `--command-id` |
| `ticket resolve` | `<ticket_id>` | `--expected-version`; optional `--command-id`, `--workflow-ref` |

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
| `project delivery query <project_key>` | optional `--output {text,json}` |
| `control health` | none |

All are online reads and never spooled. `project delivery query` does not create or configure a project;
that is [Onboard a project](#onboard-a-project).

`<project_key>` is validated against the generated contract pattern `^[a-z][a-z0-9-]{2,63}$` before the
request leaves your machine; a key outside it exits `64`. A well-formed key with no authorized rows is
refused with `project-delivery-unavailable`, never answered with an empty view.

`--output text` prints one header line carrying company, project, projection/source watermarks,
`reconciled_at`, `freshness_due_at`, `rebuild_generation`, and the projection's semantic digest, then a
`CHECKPOINT STATE CRITERIA SLOTS UNRESOLVED` table. Each row is followed by its
`label`/`owner`/`outcome` line, a `freshness`/`confidence`/`health`/`sources`/`reasons`/`watermark`/
`row_digest` line, and one line per qualifying-stage slot:

```text
  slot=<slot_key> state=<state> assigned=<seat>|unassigned signed=<seat>|-
```

A rendered seat is `<label>[<seat_key>]@<catalog_key>@<revision>`. Assignment follows the explicit
`assigned` or `unassigned` state in the response and is never inferred from the presence of a seat; a
missing signing seat renders as `-`. `--output json` emits the same view as the deterministic structured
document.

## Synthetic workflow

| Command | Input |
|---|---|
| `synthetic run` | `--workflow ctower.trust-spine-four-stage@1`, `--wait`, `--assert resolved,closed`; optional `--command-id` |
| `synthetic query` | `<run_id>` |

`synthetic run` is the server-side whole-lifecycle operation. The quickstart instead exercises the
individual public CLI steps so each boundary remains visible.

## Operations and migration

`ops outbox poison dispose` requires an outbox ID, consumer key, topic, action, and reason; `--command-id`
is optional under the common mutation rule.

The `migration ctower-project` family contains `inventory`, `export`, `plan`, `import`, `reconcile`,
`run get`, `correction append`, `fence observe`, `prepare`, `commit-development-epoch`, and `verify`. These
commands are online-only. `prepare` and `commit-development-epoch` are intentional refusal-only surfaces;
they do not activate cutover.

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
