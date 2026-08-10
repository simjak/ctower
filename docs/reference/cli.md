# CLI reference

`ctowerctl` — also installed as `ctl` — is the complete command surface. There are **82 authored server
commands**, **7 local spool commands**, and one local installed-Workflow discovery command. There is no
operation-ID escape hatch: an unrecognized command is a usage error, not a passthrough.

!!! info "Where this page comes from"
    Every command name, flag, and choice list on this page is derived from
    `apps/ctowerctl/src/ctowerctl/_parser.py`. Server commands are contract-bound: the test
    `test_parser_exposes_every_authored_name_without_operation_dispatch` in
    `tests/modules/ctowerctl/test_cli_boundaries.py` asserts the parser's authored server names equal the
    generated registry `CLI_OPERATIONS`, which is generated from `contracts/http/openapi.yaml`. The local
    Workflow discovery command reads the installed pack tree and performs no network request.

## Invocation shape

```text
ctl [--base-url <url>] [--as operator] <area> <action> [<positional>] [--flags]
```

`--base-url` scopes every invocation, including local spool commands, because the spool is scoped per
origin. It may be omitted; see [Instance discovery](#instance-discovery).

`--as operator` is required only for `dream-lane bind` and is refused on every other command. It declares
the ceremony's required role; the server still authenticates and authorizes the stdin authority, so the
flag cannot elevate a non-operator credential.

### `--base-url` rules

- Must be absolute `http` or `https`.
- Cleartext `http` is permitted **only** for loopback (`localhost`, or any loopback IP).
- Must not carry userinfo, a query string, or a fragment.

Violations are usage errors (exit `64`).

### Instance discovery

Omit `--base-url` and the CLI resolves the one instance declared in the owner-only
`~/.config/ctower/cli-instances.json` catalog — never an environment variable. `ctower-private-vps
expose-cli` writes that catalog from the installed runtime's own configuration. A catalog with zero
declared instances, or with more than one, both refuse by name (usage exit `64`) instead of guessing; pass
`--base-url` explicitly to reach a different instance or to disambiguate. An explicit `--base-url` always
takes priority and skips discovery entirely.

### Authority

Every server command reads one authority line from **stdin**. It is never a flag and never an environment
variable. Maximum 8192 characters; the trailing newline is stripped.

```bash
printf '%s\n' "${authority}" | ctl --base-url http://127.0.0.1:8080 control health
```

Missing or oversized authority is a usage error.

### Exit codes

| Exit | Meaning |
|---:|---|
| `0` | Query succeeded, or mutation accepted |
| `64` | Invalid command, invalid input, or missing stdin authority |
| `69` | Permanent server refusal, quarantine barrier, or failed assertion |
| `74` | Local spool, keyring, filesystem, or integrity failure |
| `75` | Durably queued, server unreachable, or `durability_pending` |

Full semantics, including what to retry: [the agent operating contract](../agents/operating-contract.md).

### Common flags

| Flag | Applies to | Notes |
|---|---|---|
| `--command-id` | Every mutation | Caller-supplied UUID becomes the idempotency key. Optional on every mutation; the CLI generates and prints one client-side when omitted |
| `--expected-version` | Version-guarded mutations | Optimistic concurrency; a mismatch is `version-conflict` |
| `--reason` | Authority and work mutations | Bounded metadata, never secret material |

`<ticket_id>`, `<run_id>`, `<outbox_id>`, and `<sequence>` are positional.

## Bootstrap

One-time first-tenant ceremony. Not spooled.

| Command | Flags |
|---|---|
| `bootstrap first-tenant` | `--command-id`, `--tenant-name`, `--tenant-slug`, `--operator-name`, `--operator-credential-ref`, `--operator-vault-ref`, `--commander-name`, `--commander-vault-ref` |

All `*-ref` values are references. Never pass a credential value.

## Project-seat credentials

| Command | Positional | Flags |
|---|---|---|
| `credential seat issue` | — | required: `--credential-digest`, `--credential-ref`, `--display-name`, `--project-key`, one or more `--scope {capture,transition,evidence}`, `--seat-key`; optional: `--command-id` |
| `credential seat revoke` | `<credential_id>` | required: `--reason`; optional: `--command-id` |

Both commands are online-only and operator-authorized. They are never spooled. Credential values are not
accepted; the issue command takes a reference and a lowercase SHA-256 digest.

## Requests

| Command | Positional | Flags |
|---|---|---|
| `request capture` | `<text>` | required: `--project-key`; optional: `--command-id` |
| `request list` | — | optional: `--project-key` |
| `request prioritize` | `<request_id>` | required: `--expected-version`, `--priority {P0,P1,P2}`, `--reason`; optional: `--command-id` |
| `request triage` | `<request_id>` | required: `--expected-version`, `--disposition {ACCEPTED,DUPLICATE,REJECTED}`; optional: `--command-id`, `--reason`, `--canonical-request-id` |
| `request owner assign` | `<request_id>` | required: `--expected-version`, `--owner-id`, `--reason`; optional: `--command-id` |
| `request ticket relate` | `<request_id>` | required: `--expected-version`, `--ticket-id`, `--purpose {required,optional}`, `--reason`; optional: `--command-id`, `--inactive` |
| `request blocker set` | `<request_id>` | required: `--expected-version`, `--blocker-key`, `--reason`; optional: `--command-id`, `--inactive` |
| `request closure evaluate` | `<request_id>` | required: `--expected-version`, `--reason`; optional: `--command-id` |

Capture and every Request mutation use the protected encrypted spool. Exit `75` and a
`durability_pending` result mean the server has not yet supplied the required acceptance proof; drain or
replay the same command ID. Do not invent a fresh command ID for the same intent. `request list` is an
online-only read and never enters the spool.

The server derives Actor, project authority, submitter, initial owner, source, number, and state. A Request
may remain without a Ticket; relations are explicit and never change Ticket custody or lifecycle. See
[Requests](../concepts/requests.md).

## Ticket: capture and reads

| Command | Positional | Flags |
|---|---|---|
| `ticket capture` | — | required: `--priority {P0,P1,P2}`, `--project-key`, `--source-kind`, `--source-ref`, `--title`; optional: `--command-id`, `--initial-custodian-id` |
| `ticket create` | — | identical to `ticket capture` |
| `ticket query` | `<ticket_id>` | required: `--project-key` |
| `ticket show` | `<ticket_id>` | identical to `ticket query` |
| `ticket timeline` | `<ticket_id>` | required: `--project-key` |
| `ticket assignments` | `<ticket_id>` | required: `--project-key` |
| `ticket audit` | `<ticket_id>` | required: `--project-key`; optional: `--cursor` (≥ 0), `--limit` (≥ 1, server max 100) |

`capture`/`create` and `query`/`show` are aliases of the same operations, `createTicket` and `getTicket`.
When `--command-id` is omitted, the CLI generates it before encrypted spool enqueue and prints it. Use
`spool drain` for a queued retry; entering the create command again without the printed key starts a new
intent. When `--initial-custodian-id` is omitted, the authenticated principal becomes the requested initial
custodian. A Commander may establish only self-custody; an operator omission is refused and an operator
must explicitly name an eligible Commander. Explicit values are authorization requests, not authority.

## Ticket: authority

| Command | Positional | Flags |
|---|---|---|
| `ticket comment add` | `<ticket_id>` | `--command-id`, `--body` |
| `ticket assign` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--kind {current_assignee,stage_owner,reviewer}`, `--to-principal-id`, `--scope-ref` (optional) |
| `ticket custody transfer` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--from-custodian-id`, `--to-custodian-id`, `--protected-transfer` (required flag) |

`--protected-transfer` is mandatory and has no negative form. Custody transfer is a protected operation,
distinct from assignment. See [tickets](../concepts/tickets.md#the-parts-you-will-see).

## Ticket: context and review dispatch

| Command | Positional | Flags |
|---|---|---|
| `ticket change-reference add` | `<ticket_id>` | required: `--repository`, `--change-identity`, `--reference`; optional: `--command-id` |
| `ticket label apply` | `<ticket_id>` | required: `--label-key`; optional: `--command-id` |
| `ticket review-dispatch list` | `<ticket_id>` | — |
| `ticket review-dispatch consume` | `<ticket_id> <effect_id>` | required: `--expected-version`, `--reason`, `--crew-name`; optional: `--command-id` |

Change references and labels add declared context. A review-dispatch effect is a recorded request for an
independent review. Consuming it records the authenticated reviewer assignment; it does not launch a
reviewer process.

## Ticket: work and intents

| Command | Positional | Flags |
|---|---|---|
| `ticket prioritize` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--priority {P0,P1,P2}`, `--urgent-evidence-ref` (optional) |
| `ticket admit` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason` |
| `ticket reopen` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason` |
| `ticket defer` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--review-after` |
| `ticket block` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--blocker-id`, `--blocker-kind {dependency,operator_action,policy,resource,technical}`, `--reason-class`, `--owner-principal-id`, `--source-ref`, `--resolution-condition`, `--board-impact` / `--no-board-impact`, plus optional `--affected-stage`, `--next-check-at`, `--dependency-ref` |
| `ticket unblock` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--blocker-id`, `--resolution-evidence-ref` |
| `ticket relation add` | `<ticket_id>` | `--command-id`, `--expected-version`, `--reason`, `--kind {parent_of,depends_on,blocks,duplicates,relates_to,caused_by}`, `--target-ticket-id` |

`--review-after` and `--next-check-at` are ISO-8601 timestamps that **must** carry a UTC offset. A naive
timestamp is rejected.

`--board-impact` uses argparse's boolean-optional form: pass either `--board-impact` or
`--no-board-impact`. Omitting both is an error.

## Ticket: proof

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

Both accept the same optional ticket fields: `--initial-custodian-id`, `--priority {P0,P1,P2}`, `--title`,
`--target-ticket-id`, `--expected-ticket-version`. Both are mutations and are spoolable.

Submitting without `--thread-id` starts a new thread; supplying one appends to that thread and then
`--expected-thread-version` is required. Supplying exactly one of the pair is a usage refusal, not a guess.
Content submitted as `--taint quarantine_required` is stored and held: it is recorded as quarantined and
never becomes a ticket on submission. Promotion is idempotent — promoting an event that already produced a
ticket returns the same ticket instead of creating another, and an ineligible event is refused without
changing anything.

## Inbox

| Command | Positional | Flags |
|---|---|---|
| `inbox send` | `<text>` | required: `--to <seat_key>`; optional: `--command-id`, `--thread <thread_id>` |
| `inbox notify` | `<text>` | required: `--to <seat_key>`; optional: `--command-id` |
| `inbox ack` | `<message_id>` | required: `--state {delivered,read}`; optional: `--command-id` |
| `inbox promote` | `<thread_id>` | optional: `--command-id`, `--ticket <ticket_id>` |
| `inbox list` | — | `--unread` |
| `inbox read` | `<thread_id>` | — |
| `inbox read-state` | `<thread_id>` | — |

`send` starts a two-party thread when `--thread` is omitted. On an existing thread, `--to` must name the
other participant. `send`, `ack`, and `promote` are protected, spoolable mutations; an exact command replay
returns its original result, while reusing the command ID with different input is refused as
`idempotency-conflict`.

`notify` is the narrow Mission Control transport. The existing durable delivery completes first; its stable
delivery UUID must be reused as `--command-id` for this additive attempt. The request carries only `--to`
and text: sender identity comes from the authenticated Actor and the recipient must already exist in the
persisted seat registry. Both directions of one seat pair share a derived thread, while a different pair
uses a different thread. Exact retry appends no message; an unknown seat is
`inbox-recipient-not-found`. That refusal or an unavailable ctower service never reverses the existing
delivery, and there is no configuration switch or identity auto-creation.

`promote` has two modes. Without `--ticket`, it atomically creates a P2 ticket whose title is the thread's
immutable first message, establishes ordinary initial custody for the authenticated eligible principal,
and links the thread and ticket. With `--ticket`, it leaves the existing in-scope ticket unchanged and adds
the same bidirectional link. The result reports the explicit outcome `ticket_created` or `ticket_linked`
and the resulting ticket ID. A thread may be promoted only once: exact replay of the original command
returns its original result, but a new promotion command is refused as `inbox-already-promoted`. A missing
or out-of-scope thread or ticket is `tenant-scope-denied`; creation is refused as
`inbox-thread-head-invalid` when the first message cannot be used as a ticket title. Every refusal leaves
the thread and ticket unchanged.

Only the recorded recipient may acknowledge a message. Acknowledgements advance monotonically from `sent`
to `delivered` to `read`; acknowledging `read` before `delivered` records both facts in that order. Repeating
the current state, or requesting `delivered` after `read`, is refused as
`inbox-acknowledgement-not-advancing`. A participant who is not the message recipient is refused as
`inbox-message-recipient-mismatch`; a missing message or one outside the authenticated participant scope is
reported as `tenant-scope-denied`.

The three reads are online-only queries and never record delivery or read facts. `list` is scoped to the
authenticated participant and reports per-thread and total unread counts; `--unread` filters out threads
with no unread incoming message. `read` returns the ordered messages and the fact-derived
`read_through_position`, but opening the thread does not change it. `read-state` returns each message's
fact-derived `sent|delivered|read` state and its recorded delivery/read event IDs and timestamps.

Send-specific refusals are `inbox-sender-unaddressable`, `inbox-recipient-not-found`,
`inbox-recipient-ambiguous`, `inbox-recipient-self`, and `inbox-thread-participant-mismatch`. Invalid text or
identifiers are `invalid-request`; an unavailable or out-of-scope thread is `tenant-scope-denied`. Refusals
change no Inbox state.

## Knowledge

| Command | Positional | Flags |
|---|---|---|
| `knowledge add` | — | required: `--scope {org,project}`, exactly one of `--body-file` or `--source-ref`; optional: `--project-key`, `--title`, `--command-id` |
| `knowledge list` | — | required: `--scope {org,project}`; optional: `--project-key` |
| `knowledge get` | `<document_id>` | required: `--scope {org,project}`; optional: `--project-key` |

Project scope requires `--project-key`; organization scope forbids it. `add` is a protected spoolable
mutation. The two reads are online-only.

## Recorded work sessions

| Command | Positional | Flags |
|---|---|---|
| `session start` | `<ticket_id>` | required: `--branch-ref`, `--crew-name`, `--harness-ref`, `--model-ref`, `--seat-key`, `--worktree-ref`; optional: `--command-id` |
| `session transition` | `<ticket_id> <session_id>` | required: `--reason`, `--to-state {dispatched,briefed,working,gated}`; optional: `--command-id` |
| `session close` | `<ticket_id> <session_id>` | required: `--outcome {delivered,blocked,abandoned,failed}`, `--input-tokens`, `--output-tokens`; optional: `--evidence-ref`, `--command-id` |
| `session ticket` | `<ticket_id>` | required: `--project-key` |
| `session project` | `<project_key>` | optional: `--cursor`, `--limit` |

Session start, transition, and close are protected spoolable mutations. Reads are online-only. Session
facts record work; they do not establish ticket, workflow, or proof state.

## Board and health {#board-and-health}

| Command | Flags |
|---|---|
| `board query` | positional: `<project_key>`; all flags optional: `--lane {backlog,ready,in_progress,in_review,blocked,complete}`, `--priority {P0,P1,P2}`, `--stage-key`, `--custodian-id`, `--assignee-id`, `--source-kind`, `--source-ref` |
| `control health` | — |

Both are queries and are never spooled.

For mirroring, query the exact source pair first and create only on an empty `cards` result. This is a
check-then-create workflow with a race window: source lookup does not assert uniqueness or ownership, and
independent creators can produce duplicates. See
[Source lookup and the mirroring race](../agents/operating-contract.md#source-lookup-and-the-mirroring-race).

## Operations

| Command | Positional | Flags |
|---|---|---|
| `ops outbox poison dispose` | `<outbox_id>` | `--command-id`, `--consumer-key`, `--topic`, `--action {retry,tombstone}`, `--reason` |

## Company bundle

| Command | Positional | Flags |
|---|---|---|
| `company bundle validate` | `<bundle_file>` | — |
| `company bundle plan` | `<bundle_file>` | — |
| `company bundle apply` | `<bundle_file>` | `--command-id`, `--expected-active-version` (≥ 0), `--plan-digest` |
| `company bundle export` | — | — |

`validate` and `plan` are read-only. `apply` moves one future-only Catalog pointer and requires the exact
digest from the plan you are applying. See the [CompanyBundle guide](../guides/company-bundle.md).

## Synthetic

| Command | Positional | Flags |
|---|---|---|
| `synthetic run` | — | `--workflow {ctower.trust-spine-four-stage@1}`, `--wait` (required), `--assert` (required, must be exactly `resolved,closed`), `--command-id` (optional, generated if omitted) |
| `synthetic query` | `<run_id>` | — |

`synthetic run` is the one public command that drives the whole four-stage lifecycle server-side. `--wait`
and `--assert` are both mandatory, and `--assert` accepts only the literal `resolved,closed` — the contract
does not let you assert a weaker outcome.

Waiting polls for up to 60 seconds. A run that ends `failed`, or that succeeds with lifecycle facts other
than those asserted, exits `69`. A timeout exits `75`.

## Dream dispatch

| Command | Positional | Flags |
|---|---|---|
| `dream-dispatch list` | — | — |
| `dream-dispatch consume` | `<effect_id>` | required: `--output-digest <sha256>`; optional: `--command-id` |
| `dream-lane bind` | — | required: `--lane`, `--crew`, `--harness`, `--model`, `--effort`, `--fallback`, `--tier`; optional: `--command-id` |

`list` is an online-only query and is never spooled. A project-seat principal receives only the effect for
its persisted Project grant; foreign Project effects and the fleet effect are absent. An operator receives
all Project effects plus the fleet effect.

`consume` is a protected, spoolable mutation. The output digest must be `sha256:` followed by exactly 64
lowercase hexadecimal characters. The server derives the effect's Project scope before checking
consumption or lane/model policy: a foreign Project or fleet request by a project seat refuses as
`project-scope-denied` with no consumption. Fleet consumption is operator-only. The command accepts no
lane, crew, harness, model, family, effort, or tier flags; those facts come from the persisted substrate
binding and are joined to the Routine occurrence and output digest.

`dream-lane bind` is the online-only operator ceremony that creates one immutable binding per lane reference
for the authenticated operator principal. The closed ceremony selection is `codex` with `gpt-5.6-sol` at
`max`, `qwen3.8-max` as fallback, and the `hard` tier. A non-operator is refused as
`dream-lane-binding-operator-required`; rebinding the same lane is refused as
`dream-lane-already-bound`.

A persisted mistake is irreversible for that lane: its crew and route selection can never be updated or
deleted. Recovery is to bind the corrected selection under a new versioned lane reference. The newest
binding event becomes the authenticated substrate binding used by later `dream-dispatch consume` commands;
the consume request still supplies no lane or model claims. For example, if
`dream-lane:writer-r2881-dream` was bound incorrectly, the same-lane correction refuses and the exact
recovery walk is:

```console
ctl --as operator dream-lane bind --lane dream-lane:writer-r2881-dream --crew writer-r2881-dream --harness codex --model gpt-5.6-sol --effort max --fallback qwen3.8-max --tier hard
# refuses: dream-lane-already-bound
ctl --as operator dream-lane bind --lane dream-lane:writer-r2881-dream.v2 --crew writer-r2881-dream --harness codex --model gpt-5.6-sol --effort max --fallback qwen3.8-max --tier hard
ctl --as operator dream-dispatch consume <effect_id> --output-digest <sha256>
```

Replace `<effect_id>` and `<sha256>` with the effect identifier and lowercase SHA-256 output digest from
the recovered run; do not reuse the mistaken lane reference for another binding attempt.

Run the live ceremony only as the operator, using the exact command shape below:

```console
ctl --as operator dream-lane bind --lane <ref> --crew writer-r2881-dream --harness codex --model gpt-5.6-sol --effort max --fallback qwen3.8-max --tier hard
```

## Migration (ctower-project)

All eleven commands are authenticated and online-only. They are **not** spoolable.

| Command | Positional | Flags |
|---|---|---|
| `migration ctower-project inventory` | — | `--command-id`, `--request-file` |
| `migration ctower-project export` | — | `--command-id`, `--request-file` |
| `migration ctower-project plan` | — | `--command-id`, `--request-file` |
| `migration ctower-project import` | — | `--command-id`, `--request-file` |
| `migration ctower-project reconcile` | — | `--command-id`, `--request-file` |
| `migration ctower-project prepare` | — | `--command-id`, `--request-file` |
| `migration ctower-project commit-development-epoch` | — | `--command-id`, `--request-file` |
| `migration ctower-project correction append` | — | `--command-id`, `--request-file` |
| `migration ctower-project fence observe` | — | `--command-id`, `--request-file` |
| `migration ctower-project run get` | `<run_id>` | — |
| `migration ctower-project verify` | — | — |

`prepare` and `commit-development-epoch` are **refusal-only** in the generated registry: they exist so the
spelling is stable and authenticated, and they always refuse. They do not import, fence, or rewire anything.

## Project delivery

| Command | Positional | Flags |
|---|---|---|
| `project delivery query` | `<project_key>` | `--output {text,json}` (default `text`) |
| `project events` | `<project_key>` | optional: `--cursor`, `--limit` |

A read-only projection. See [Project Delivery](../concepts/project-delivery.md).

Text output prints checkpoint summary and source/reason lines, followed by one line per qualifying slot:
`slot=<key> state=<state> assigned=<seat>|unassigned signed=<seat>|-`. A rendered seat is
`<label>[<seat_key>]@<catalog_key>@<revision>`. Assignment is selected by the explicit `assigned` or
`unassigned` state in the HTTP response, and a missing signing seat renders as `-`.

`project events` returns a cursor page of typed events visible to the authenticated project principal. It
is also read-only and online-only.

## Attention findings

| Command | Positional | Flags |
|---|---|---|
| `attention finding append` | — | required: `--subject-ticket-id`, `--kind-key`, `--reason-code`, `--effective-owner {operator,commander}`, `--recommendation`, one or more `--alternative`, `--consequence`, `--dedupe-key`, one or more `--source-fact`; optional: `--deadline`, `--command-id` |
| `attention finding disposition` | `<finding_id>` | required: `--outcome {resolved,snoozed,expired,superseded,cancelled}`, `--reason`; optional: `--command-id` |

Both commands append facts and are spoolable. A disposition does not delete the finding.

## Local spool

Seven commands that never leave the machine except where noted. See the
[protected CLI guide](../guides/protected-cli.md) for the recovery procedures.

| Command | Positional | Flags |
|---|---|---|
| `spool status` | — | — |
| `spool list` | — | `--state {pending,accepted_archive,quarantine}`, `--limit` (default 1000) |
| `spool quarantine list` | — | `--limit` (default 1000) |
| `spool doctor` | — | — |
| `spool drain` | — | — (reads stdin authority and sends) |
| `spool retry` | `<sequence>` | `--reason` |
| `spool discard` | `<sequence>` | `--reason`, `--artifact-digest` (optional) |

`spool status` and `spool doctor` exit `74` when the spool is unhealthy or its state cannot be established.
`spool drain` exits `69` at a quarantine barrier, `75` while entries remain pending, `0` when the spool is
empty.

A listed entry quarantined by the server also carries `server_refusal` (`status` and a `name` that is either
an authored refusal code or the content-free sentinel `unrecognized_refusal`, never response body text); an
entry quarantined locally — `credential_identity_mismatch`, `expired`, `corrupt_record` — carries its
`reason_code` and no `server_refusal`.

## Output

Machine output is one JSON object per invocation: deterministic key order, no ASCII escaping, compact
separators, and a single trailing newline. Two exceptions render text instead: `company bundle export`
emits YAML, and `project delivery query --output text` emits the compact delivery projection.

A mutation prints `command_id`, `state` (`accepted`, `queued`, `quarantined`, or `local_failure`),
`reason_code`, and `sequence`, plus `result` when a current server result is available. A refusal prints the
[problem document](../agents/refusals.md) on stderr.

Authority values never appear in output.

## Related

- [HTTP API reference](http-api.md) — the operation each command calls.
- [Generated clients and contracts](clients.md) — using the same surface from code.
- [For agents](../agents/operating-contract.md) — replay, idempotency, and refusal handling.
