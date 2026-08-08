# Issue connector framework proposal

Status: subordinate proposal for [GitHub issue #381](https://github.com/simjak/ctower/issues/381), not an
implemented or accepted product contract.

This document proposes how ctower can turn the shipped GitLab issue integration into one narrow issue-
connector framework, add GitHub Issues as the second implementation, and put every connector-created ticket
through explicit project-commander triage. It is deliberately limited to issue trackers with the proven
poll, normalize, update, and proof-gated close-back shape.

`SPEC.md` remains authoritative. Today it accepts only the GitLab-specific D39 seam and defers a generic
connector framework and GitHub integration. Implementation cannot begin merely because this proposal is
merged. Activation requires stable CT tickets and dependencies in `SPEC.md`, an append-only decision that
supersedes the D39 deferral, and corresponding repairs to `ARCHITECTURE.md` and
`IMPLEMENTATION-ROADMAP.md`.

## Outcome

After all four proposed phases are accepted:

- GitLab and GitHub Issues implement the same small, provider-neutral contract;
- the kernel and control worker own custody, progress, leases, fencing, proof-close eligibility, and durable
  idempotency, while each connector owns only its provider transport, strict mapping, external identity, and
  cursor semantics;
- a connector-created ticket is visibly `UNTRIAGED` until its project Commander records accept, duplicate,
  or reject, and a Commander or operator records its priority;
- a connector author can add a Jira-shaped third implementation by adding provider code, registration, and
  tests without editing connector core; and
- credentials remain deployment-resolved references. No provider token enters Catalog, Work, Record,
  Proof, logs, browser state, or connector cursors.

This proposal does not claim that any of that behavior exists yet.

## Evidence and current boundary

The floor is the implementation merged by [pull request #377](https://github.com/simjak/ctower/pull/377),
including its follow-up cure commit `f68110e`. That code already proves:

- strict GitLab payload mapping and bounded pagination;
- a revision-pinned active Catalog registration composed with a deployment-resolved secret;
- one bounded poll tick under a leased, fenced PostgreSQL claim;
- exact external-reference custody, immutable observations, delivery receipts, and proof-gated close-back;
- classified retry with bounded jitter and reconciliation after an ambiguous provider write; and
- shared fake/HTTP conformance plus a real-PostgreSQL `MockTransport` round trip.

The current implementation is intentionally GitLab-shaped in names, cursor fields, normalized values,
configuration schema, and worker composition. Phase 1 extracts those proven rules in place. It does not put
a generic wrapper around the existing GitLab loop and does not keep old and new execution paths alive.

## Scope and non-goals

In scope:

- polling one configured issue container at a pinned connector-registration revision;
- strict conversion from GitLab issues, GitHub issues, and a stated Jira-shaped next connector into one
  normalized external-issue value;
- immutable external-issue-to-ticket custody and replay-safe source observations;
- ticket updates from changed issue content;
- exactly-once outcomes for proof-gated comment-and-close commands;
- explicit triage and priority facts for connector-created tickets; and
- a first-party, statically registered connector-author path with shared conformance tests.

Out of scope:

- pull requests, merge requests, epics, discussions, chat, email, or arbitrary event sources;
- webhook ingress, provider-to-ctower callbacks, or a public connector endpoint;
- dynamic packages, runtime code loading, entry-point discovery, or a connector marketplace;
- connector-defined SQL, tables, migrations, Work transitions, Proof verdicts, or arbitrary outbound effects;
- bi-directional field synchronization beyond source title/description updates and proof-gated comment-and-
  close;
- provider-side triage, automatic prioritization, fuzzy duplicate detection, or cross-project custody; and
- a compatibility layer for the GitLab-specific contract.

## Custody and component boundary

```text
Catalog registration (config + credential reference)
                 | deployment resolves the reference
                 v
control worker -> connector core -> provider adapter -> provider API
                      |                    |
                      | normalized issue   | provider cursor/reconciliation
                      v                    |
               Work + connector store <---+
                      |
                      | accepted Project success proof only
                      v
               durable close command -> provider marker/comment + close
```

The kernel remains provider-blind and never resolves credentials or performs network I/O. The API process
composition root resolves a credential reference and constructs the selected first-party adapter. The
adapter may call only its configured provider origin. The connector service coordinates the generic state
machine and writes through the connector store. No runner, web, CLI, extension, YAML pack, or provider code
connects directly to record-tier persistence.

### Core ownership

Connector core owns:

- the strict `ExternalIssue`, opaque bounded `ConnectorCursorToken`, revision binding, claim, link,
  observation, close-command, and close-receipt value types;
- one `IssueConnector` protocol and one bounded tick service;
- progress keyed by `(tenant_id, connector_registration_key, registration_revision_id)`;
- leased claims, fencing tokens, next-poll scheduling, durable failure counts, and bounded retry timing;
- exact external-reference uniqueness and immutable ticket linkage;
- source-observation and outbound-event deduplication;
- deterministic application of the registration's provider-neutral source-label map;
- selection of eligible Project success evidence and creation of deterministic close command IDs;
- the shared retry executor and its hard attempt, deadline, delay, and jitter bounds;
- PostgreSQL persistence and migrations for provider-neutral connector state; and
- control-worker iteration over already composed connector services.

The connector core interface is a small structural protocol, not an inheritance hierarchy. A connector
implements fetch and comment-and-close behavior; it does not subclass a service or receive stores, database
handles, Work services, or Proof authority.

The complete adapter surface is:

```python
class IssueConnector(Protocol):
    def fetch_page(self, request: FetchIssuePage) -> ExternalIssuePage: ...
    def comment_and_close(self, command: CloseExternalIssue) -> ConnectorReceipt: ...
```

`FetchIssuePage` contains only the opaque cursor token and core-enforced page bound.
`ExternalIssuePage` contains a bounded tuple of strict `ExternalIssue` values, the next opaque token, and an
exhausted flag. `CloseExternalIssue` contains the exact external reference, deterministic command ID,
deterministic marker, and proof-derived comment. `ConnectorReceipt` echoes the command ID and proves marker
and closed state. The composed adapter already owns its pinned, validated provider config and process-local
credential, so neither call carries config or a secret.

### Per-connector ownership

Each provider implementation owns:

- a strict, provider-specific configuration model and authored schema;
- its allowed HTTPS origin and HTTP authentication injection;
- raw response validation and mapping to `ExternalIssue`;
- extraction of provider source labels and reporter presentation fields;
- construction of an exact, immutable external reference;
- interpretation and strict bounded encoding of its opaque cursor token;
- mapping provider errors into the core outcomes `retryable`, `terminal`, or `ambiguous_write`;
- lookup of the deterministic marker after an ambiguous comment or close response; and
- provider-specific close mechanics.

A connector cannot choose retry limits, write directly to progress, relax proof eligibility, invent Work
events, or reinterpret another connector's cursor. The registration revision pins both config and cursor
semantics, so connector core can persist a bounded opaque token without an open-ended JSON contract.

## Numbered invariants

Every invariant below is either traced to the #377 implementation or explicitly labeled new in #381. The
line references are collected in the trace table at the end.

### CX-01 — Revision-pinned composition

**Proven by #377.** Each active Catalog registration resolves to one immutable revision ID and digest. The
control-plane composition root validates that revision's strict provider config, resolves its credential
reference from the deployment secret source, and constructs one adapter. Progress is keyed by that revision;
changing a registration never silently reuses another revision's cursor.

Multiple independently keyed registrations may run together; “one” binds a registration to one revision and
adapter, not the deployment to one provider or repository.

Historical Catalog revisions remain audit facts but are not executable compatibility paths. Framework
activation replaces the active GitLab registration atomically and removes the superseded GitLab-only config
parser.

### CX-02 — Secrets are resolved references, never values

**Proven by #377.** Authored config contains a credential binding reference only. The referenced value is
resolved at deployment composition, injected into the transport, and never returned to kernel values,
Catalog payloads, persistence, cursor tokens, logs, errors, browser code, or test snapshots. Secret-like
literal values fail strict config validation.

### CX-03 — One bounded tick under a leased, fenced claim

**Proven by #377.** A tick claims one due registration revision with an owner, expiry, and monotonically
fresh fence. It performs at most one bounded source page and one bounded outbound event page, then completes
or fails through the same owner-and-fence check. Expired or stale workers cannot commit progress.

### CX-04 — Connector cursor semantics are isolated

**New in #381, extracted from #377's cursor and tick.** Core persists only a non-secret, size-bounded opaque
cursor token under the pinned registration revision. The selected adapter alone validates, decodes, compares,
and advances that token. Fetch results must either advance the token or declare exhaustion; a repeated token
with a non-empty page is a terminal contract failure. Adding a provider must not add columns or branches to
the core cursor type.

### CX-05 — Mapping is strict and provider-owned

**Proven by #377; provider-neutral ownership is new in #381.** A connector rejects malformed external
payloads before they reach Work. It maps only the fields in `ExternalIssue`: connector kind, exact external
reference, title, description, source labels, reporter reference/display name, external state, external update
time, and display URL. Core derives the source version digest over that normalized value.
Unknown enum values, invalid timestamps, missing immutable IDs, over-limit strings, and unsupported item
kinds fail closed.

GitHub's issues endpoint can surface pull requests; the GitHub connector must exclude any item carrying pull-
request identity rather than ingesting it as an issue.

### CX-06 — External-reference custody is closed-world

**Proven closed-world rule in #377; provider-neutral keys are new in #381.** The key
`(tenant_id, connector_registration_key, external_ref)` identifies at most one immutable ctower ticket, and
one ticket has at most one connector source under this proposal. An exact replay returns that link. A link to
a different ticket, or reuse of a ticket by a different external key, fails. No title, repository name, issue
key, author, URL, similarity score, alias, or redirect is allowed to merge custody.

Provider identities are:

- GitLab: `gitlab:<immutable-project-id>:<issue-iid>`;
- GitHub: `github:<immutable-repository-id>:<issue-number>`; and
- Jira-shaped next connector: `jira:<immutable-site-id>:<immutable-issue-id>`.

Mutable paths, owners, repository names, and Jira display keys are presentation fields, never identity.

### CX-07 — Source observations are replay-safe

**Proven by #377.** The source version digest is deterministic over the strictly normalized provider value.
The first observation creates exactly one ticket, exact link, initial priority fact, and observation. An
unchanged replay writes nothing. A changed digest appends one observation and one deterministic ticket update.
Cursor replay, worker restart, or an overlapping poll cannot duplicate the ticket or update.

### CX-08 — Retry is classified, capped, and jittered

**Proven policy in #377; core ownership is new in #381.** Core provides one retry executor with the shipped
limits: at most four attempts, a ten-second total deadline, exponential backoff capped at two seconds, and
bounded jitter. A connector classifies only timeouts, transport
failures known to be transient, provider throttling, and provider 5xx responses as retryable. Authentication,
authorization, validation, unsupported payload, and ordinary 4xx responses are terminal.

The jitter source is injectable for deterministic conformance tests. Durable tick failure scheduling remains
separate from in-request retry and advances only through a valid fence.

### CX-09 — Ambiguous writes reconcile before retry

**Proven by #377.** Every outbound comment contains a deterministic command marker. If the transport cannot
prove whether a write succeeded, the connector first reads the provider thread and searches for that exact
marker. A match becomes the durable receipt; only a confirmed absence permits another write within CX-08's
bounds. Marker matching is exact and scoped to the configured external item. A timeout never licenses a blind
duplicate write.

### CX-10 — Close-back is proof-gated and receipt-backed

**Proven by #377.** Only an accepted Project success proof for the linked ticket creates a provider close
command. Source state, triage, ordinary ticket lifecycle, Board movement, text, comments, or provider labels
cannot do so. The deterministic event/command ID has one durable delivery row and at most one receipt.
Replays return that receipt or reconcile by marker. The connector posts the proof-derived close comment before
closing the issue.

“Exactly once” here means one durable ticket/link/observation per exact source fact and one externally visible
marked close outcome per eligible proof command, including replay and ambiguous-response recovery. It does not
claim that an unreliable network can make a physical request occur only once.

### CX-11 — Provider input has no Work or Proof authority

**Proven by #377; explicit triage gate is new in #381.** Provider content remains `external_untrusted`.
Polling may create a ticket, append a changed title/description observation, and maintain custody. It cannot
accept triage, set an actor-attributed priority, claim or run work, change a lifecycle episode, assert Proof,
or choose close eligibility.

### CX-12 — GitHub proves the plug point while core stays frozen

**New in #381.** GitHub Issues is not accepted until it passes the unchanged shared conformance suite and a
real fixture repository round trip without changes to the core freeze set below. A connector-specific test
fixture or static registry row is not a core change.

### CX-13 — Triage is an independent, append-only state axis

**New in #381.** Connector intake atomically appends an initial `P2` safety default required by the current
Work contract, triage state `UNTRIAGED`, immutable connector custody, and an unresolved Commander-owned
`connector_triage_required` Attention finding. Triage is exactly one of `UNTRIAGED`, `ACCEPTED`, `DUPLICATE`,
or `REJECTED`; it is not encoded in lifecycle status, priority, Board lane, label, or connector config.

Only the project Commander may move an item out of `UNTRIAGED`:

- `ACCEPTED` requires a priority assignment fact recorded after intake by that Commander or an operator. The
  initial automatic `P2` alone is not an actor decision. Acceptance resolves the Attention finding and admits
  the ticket to ordinary execution.
- `DUPLICATE` requires a same-project canonical ticket and appends the existing `duplicates` relation before
  recording the duplicate disposition and cancelling the duplicate ticket.
- `REJECTED` records a reason and cancels the ticket without inventing a duplicate relation.

Duplicate and rejected dispositions do not fabricate Project success and therefore do not close the provider
issue through CX-10.

### CX-14 — Priority has server-side actor authority

**New in #381.** A project Commander or authenticated operator may append a priority assignment for a
connector-created ticket, including while it is `UNTRIAGED`. The command is project-scoped, idempotent,
expected-version checked, and records actor, prior value, new value, reason, and timestamp. No connector,
provider identity, browser state, hidden form field, or UI role label grants this authority.

### CX-15 — Untriaged work cannot silently disappear

**New in #381.** `UNTRIAGED` remains visible in the existing Board and Ticket Detail surfaces with its triage
state, current priority/default, source identity, age, and unresolved Attention finding. The Board provides a
filter and count; Ticket Detail provides contextual triage and priority controls. No new top-level surface is
created. The server derives every control's authorization and rejects stale or unauthorized commands even if
a client renders them. There is no automatic acceptance, expiry, dismissal, or hidden queue.

### CX-16 — Connector N requires zero core changes

**New in #381.** After Phase 2, adding a Jira-shaped connector consists only of its provider package, strict
config/schema, one explicit static registration entry, credential declaration, provider fixtures, and tests.
It must not change a frozen core file, shared conformance assertion, database schema, Work event, Proof rule,
or control-worker branch. If Jira cannot fit the issue-only contract, the author stops and proposes a new
decision instead of widening the interface in the connector pull request.

### CX-17 — Registration is explicit and first-party

**New in #381.** The composition root uses an allow-listed static registry from connector kind to strict
config parser and adapter factory. Registration rejects duplicate kinds and schema identifiers at startup.
There is no import string, executable Catalog payload, package discovery, dynamic entry point, or connector-
supplied persistence. The registry may be extended by one reviewed row without changing connector core.

### CX-18 — Shared conformance is the admission contract

**Proven by #377; multi-provider admission is new in #381.** Every connector runs the same fetch, mapping,
cursor, exact-link, replay, source-update, proof-close, receipt, retry-classification, deadline, jitter, and
ambiguous-write cases. Each real adapter also runs an acceptance test against real PostgreSQL and an in-
process provider `MockTransport`. A provider fixture cannot replace shared conformance or PostgreSQL.

## GitHub Issues connector

GitHub is the second implementation and the proof that the extracted seam is real. Its first accepted scope
is one configured repository, polled over the GitHub API. It maps issues only, uses the repository's immutable
numeric ID plus issue number for identity, and strictly excludes pull requests. Its cursor is provider-owned
and must produce stable ordering with an immutable tie-breaker when update timestamps match.

Outbound behavior is the same as GitLab: append one deterministic marker-bearing comment derived from an
accepted Project success proof, then close the issue, then return or reconcile a receipt. The adapter cannot
close from a GitHub label, milestone, state change, comment, or actor.

The real-fixture acceptance repository must be private to the test installation, contain no production or
personal content, and be reset by creating a fresh uniquely identified issue rather than deleting audit
history. Evidence records the fixture repository ID, issue number, ctower ticket ID, command marker digest,
receipt, and resulting closed state, but never credentials or response authorization headers.

### Core freeze set

Implementing GitHub, and later connector N, must not modify:

- `packages/ctower-kernel/src/ctower_kernel/integrations/interface.py`;
- `packages/ctower-kernel/src/ctower_kernel/integrations/service.py`;
- `packages/ctower-kernel/src/ctower_kernel/integrations/postgres.py`;
- `packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py`;
- provider-neutral connector persistence migrations;
- the provider-neutral connector loop and tick composition in
  `apps/ctower-api/src/ctower_api/control_worker.py`;
- Work, Record, Proof, Board, or Attention kernel authorities; or
- the shared connector conformance harness and its assertions.

If the GitHub implementation requires any freeze-set edit, Phase 1 has not extracted a sufficient seam. The
change returns to Phase 1 review; it is not smuggled into the provider implementation.

## Triage commands and projections

The server exposes two project-scoped commands and projects their facts behind existing authentication and
authorization:

1. `triage_connector_ticket(client_command_id, ticket_id, expected_version, disposition,
   canonical_ticket_id?, reason)` — Commander only, valid only from `UNTRIAGED`.
2. `set_connector_ticket_priority(client_command_id, ticket_id, expected_version, priority, reason)` —
   project Commander or operator, valid for any non-terminal connector-created ticket.
3. Existing read models project triage facts into Board, Ticket Detail, and Attention; no client writes a
   projection directly.

Concurrent commands use expected-version conflict rather than last-write-wins. An idempotency key may replay
the exact same command and result, but reuse with different arguments fails. The audit trail identifies the
authenticated actor and project role supplied by server-side policy, not caller-provided role text.

Program structural decision 10 governs this UI: the browser may submit an allowed mutation, but the server
authenticates the actor and authorizes the project-scoped command. Overview stays on Board, details and
actions stay on Ticket Detail, and human waiting stays in Attention. A UI button is only a request to server
authority.

## Connector-author contract

The author starts from the first-party issue connector scaffold:

```text
apps/ctower-api/src/ctower_api/connectors/<provider>/
  __init__.py             # narrow public export
  adapter.py              # transport, strict raw payloads, mapping, reconciliation
  config.py               # strict config and authored schema binding
  registration.py         # kind, factory, schema ID, credential requirements
tests/connectors/<provider>/
  test_conformance.py     # provider fixture bound to unchanged shared suite
  test_acceptance.py      # real PostgreSQL + MockTransport round trip
  fixtures/               # redacted provider payloads, no credentials
```

Exact target paths are settled in Phase 1 and then frozen. The important contract is ownership, not a package
per noun.

For a Jira-shaped connector, a cold reader must be able to complete these steps:

1. Define a strict config for one site and project, with an immutable site ID and a credential reference.
2. Implement the two-method `IssueConnector` protocol using the existing HTTP client and core retry executor.
3. Map the immutable Jira issue ID into `jira:<site-id>:<issue-id>`; retain the mutable display key only for
   presentation.
4. Implement a bounded provider cursor token with stable update ordering and an immutable tie-breaker.
5. Put the deterministic marker into the provider comment and reconcile an ambiguous write by exact marker
   lookup before retry.
6. Add one allow-listed registration row and a reference-only credential declaration.
7. Bind provider fixtures to the unchanged shared suite.
8. Run the provider acceptance test with real PostgreSQL and `httpx.MockTransport`, including restart,
   overlapping poll, stale fence, source update, proof close, ambiguous response, and replay.
9. Show a freeze-set diff of zero.

The guide must state why a failure is terminal or retryable, how cursor order is proven, what immutable IDs
form custody, how fixture data was redacted, and which provider permissions are required. Copying the GitLab
adapter and changing URLs is not conformance.

## Security and credential custody

This proposal stays inside the accepted D10 integration seam: a trusted API composition root already turns a
Catalog credential reference into a process-local provider transport; a narrow adapter already exchanges
strict typed values with a kernel service; and record-tier persistence remains behind the kernel store. The
second provider changes transport and mapping, not the trust boundary.

Each registration declares and validation evidence proves the least provider scope that supports its exact
operations:

| Connector | Credential and minimum intended scope | Prohibited custody |
|---|---|---|
| GitLab | Expiring project access token for the exact project, Planner role, and project-scoped `api` scope. Planner is the documented minimum role to edit, comment on, and close issues; `api` is currently the project-token scope that permits API writes. | Personal access token when a project token is available; group-wide token; token value in Catalog. |
| GitHub | GitHub App installation token restricted to the fixture/target repository, with repository `Issues: read and write` and `Metadata: read`; no webhook subscription is needed. | User access token, organization-wide installation where repository selection is possible, App private key or installation token in Catalog. |
| Jira-shaped next | Expiring project/site-constrained technical principal with only browse/read issue, add comment, edit issue, and transition issue permissions proven for the chosen Jira deployment. | Human password, site-admin grant, cross-project scope, or an unreviewed generic API token. |

[GitLab documents](https://docs.gitlab.com/user/project/settings/project_access_tokens/) that project access
tokens are scoped to their associated project; its
[scope reference](https://docs.gitlab.com/security/tokens/access_token_scopes/) says `api` grants API
read/write within that scope, and its
[role matrix](https://docs.gitlab.com/user/permissions/#project-planning) makes Planner the minimum project
role for the required issue changes. [GitHub documents](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)
that Apps start with no permissions and should request the minimum required permissions. Implementers must
re-check vendor documentation at build time because provider permission models can change.

The following would cross a new boundary and therefore stops implementation for an explicit CSO gate and an
accepted superseding decision:

- webhook or other provider-initiated ingress;
- OAuth consent, refresh-token custody, or a user-delegated token broker;
- dynamic third-party code loading, package discovery, or executable connector configuration;
- connector-authored SQL, schema, migration, direct database handle, or record-tier client;
- any credential value in Catalog, Work, Record, Proof, logs, browser storage, fixtures, or cursors;
- browser, runner, CLI, extension, or YAML-pack network calls to a provider;
- provider data that can triage, set priority, mutate lifecycle, claim work, assert proof, or bypass Project
  success close eligibility;
- arbitrary outbound actions beyond the narrow marker-bearing comment-and-close command; or
- new public listeners, firewall paths, egress destinations, or network trust zones.

## Delivery phases and phase gates

Each phase leaves a complete, testable product boundary. A later phase does not excuse a partial earlier one.

### Phase 1 — Extract the framework in place

Replace GitLab-shaped core names, cursor columns, service branches, persistence, and worker composition with
the provider-neutral contract. Move GitLab transport, mapping, external identity, cursor codec, failure
classification, and reconciliation into the GitLab implementation. Delete the superseded GitLab-only loop
and config execution path; do not wrap it or run both paths.

Acceptance:

- every existing #377 unit, conformance, real-PostgreSQL acceptance, retry, ambiguous-write, claim, fence,
  restart, update, close, and replay trace remains green with equivalent observable IDs and outcomes;
- mutation tests still fail when exact dedup, proof eligibility, marker reconciliation, or fencing is removed;
- the active GitLab registration is the framework registration and the superseded parser/path is absent;
- generic core contains no GitLab or GitHub branch, config type, payload field, or cursor interpretation; and
- `just check` and `just verify` pass.

### Phase 2 — Add GitHub Issues

Implement GitHub only through the frozen Phase 1 seam and static registry. Add strict issue mapping, pull-
request exclusion, immutable repository identity, provider cursor semantics, retry classification, and exact
marker reconciliation.

Acceptance:

- unchanged shared conformance passes for GitLab and GitHub;
- GitHub's provider tests cover equal timestamps, rename-safe repository identity, pull-request exclusion,
  throttling, terminal authorization errors, and ambiguous comment/close responses;
- a real GitHub fixture issue completes issue -> ticket -> source update -> accepted Project success proof ->
  one marked comment -> closed issue, and replay creates no duplicate ticket, update, comment, close, or
  receipt;
- the evidence bundle contains the non-secret custody IDs and gate output named above; and
- the core freeze-set diff is zero and both repository gates pass.

### Phase 3 — Add connector triage and priority authority

Add the independent triage facts, commands, authorization, Attention finding, and existing-surface projections.
Connector intake remains end-to-end usable: it produces a durable, visible ticket that cannot execute until
accepted.

Acceptance:

- real ingested GitLab and GitHub items atomically appear `UNTRIAGED` with initial `P2` and one unresolved
  Commander-owned Attention finding;
- a project Commander accepts one after a Commander/operator priority assignment, and the custody trail
  records both authenticated actions;
- duplicate requires and records one same-project canonical relation; reject records a reason; neither
  produces a provider close without accepted Project success proof;
- an operator can set priority but cannot triage, and unauthorized, cross-project, stale-version, and forged-
  role requests fail;
- Board, Ticket Detail, and Attention show the same triage state and untriaged count after restart; and
- concurrency, command replay, projection rebuild, `just check`, and `just verify` pass.

### Phase 4 — Publish and validate connector-author DevEx

Publish the final scaffold, registration procedure, credential ceremony, conformance contract, fixture rules,
and troubleshooting guidance using the frozen paths from Phase 1 and the GitHub implementation as the first
cold-reader example.

Acceptance:

- a contributor unfamiliar with the extraction follows only the guide to build a Jira-shaped test connector
  with provider mapping, cursor, marker reconciliation, and reference-only credential declaration;
- its unchanged shared conformance and real-PostgreSQL + `MockTransport` acceptance pass;
- its freeze-set diff is zero and it adds no dependency when the existing HTTP/Pydantic stack suffices;
- secret scanning proves fixtures, failure output, and docs contain references only;
- a reviewer verifies every requested provider permission against current vendor documentation; and
- `just docs-check`, `just check`, and `just verify` pass.

## Acceptance and proof map

| Requirement | Required proof |
|---|---|
| One extracted base contract | Phase 1 source diff, removed GitLab-only path, unchanged #377 regression traces |
| Two real implementations | Shared conformance matrix naming GitLab and GitHub |
| Exactly-once GitHub round trip | Real fixture custody IDs, one ticket/update/comment/close/receipt before and after replay |
| Triage authority | Real ingested-item audit showing Commander disposition and Commander/operator priority fact |
| Untriaged visibility | Board, Ticket Detail, and Attention read-model assertions across rebuild/restart |
| Connector N without core changes | Jira-shaped cold-reader implementation, green shared/PostgreSQL tests, zero freeze-set diff |
| Credential custody | Registration schema tests, deployment-resolution test, secret-scan output, permission review |
| Repository health | Named `just check`, `just docs-check`, and `just verify` outputs at the exact reviewed head |

Fixture output is development evidence, not production evidence. A shipped connector additionally needs the
accepted CT tickets, canonical specification and decision changes, deployment ceremony, and any production
evidence those authorities require.

## #377 invariant trace table

All paths below refer to the #377 implementation as cured by `f68110e`. A row marked **NEW #381** has no
claim of existing implementation.

| Invariant | Classification | #377 source or new requirement |
|---|---|---|
| CX-01 | Proven | `apps/ctower-api/src/ctower_api/gitlab_loop.py:71-107,122-169`; `packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py:29-83` |
| CX-02 | Proven | `apps/ctower-api/src/ctower_api/gitlab_loop.py:33-68,122-169`; `tests/modules/integrations/test_gitlab_loop.py:99-184` |
| CX-03 | Proven | `packages/ctower-kernel/src/ctower_kernel/integrations/interface.py:210-245`; `packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py:84-119,362-445`; `tests/acceptance/increment-1/test_gitlab_integration.py:162-203` |
| CX-04 | **NEW #381** | Extracted from `packages/ctower-kernel/src/ctower_kernel/integrations/interface.py:210-228` and `packages/ctower-kernel/src/ctower_kernel/integrations/service.py:85-140,304-309` |
| CX-05 | Proven + new ownership | `packages/ctower-kernel/src/ctower_kernel/integrations/interface.py:51-103`; `apps/ctower-api/src/ctower_api/gitlab_adapter.py:249-276` |
| CX-06 | Proven + **NEW #381** provider-neutral keys | `packages/ctower-kernel/src/ctower_kernel/integrations/interface.py:87-90,257-280`; `packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py:154-267`; `packages/ctower-kernel/migrations/0054_gitlab_issue_integration.sql:33-58,120-128` |
| CX-07 | Proven | `packages/ctower-kernel/src/ctower_kernel/integrations/service.py:142-204`; `packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py:210-281,448-483` |
| CX-08 | Proven + **NEW #381** core ownership | `apps/ctower-api/src/ctower_api/gitlab_adapter.py:171-246,341-347`; `tests/modules/integrations/test_adapter_conformance.py:337-419` |
| CX-09 | Proven | `apps/ctower-api/src/ctower_api/gitlab_adapter.py:107-166`; `tests/modules/integrations/test_adapter_conformance.py:422-449` |
| CX-10 | Proven | `packages/ctower-kernel/src/ctower_kernel/integrations/service.py:232-301`; `packages/ctower-kernel/src/ctower_kernel/integrations/_postgres_sql.py:282-359`; `apps/ctower-api/src/ctower_api/gitlab_adapter.py:107-138` |
| CX-11 | Proven + **NEW #381** triage gate | `packages/ctower-kernel/src/ctower_kernel/integrations/service.py:142-204,232-301` |
| CX-12 | **NEW #381** | Second-implementation and freeze-set requirement |
| CX-13 | **NEW #381** | Triage state and Commander-disposition requirement |
| CX-14 | **NEW #381** | Commander/operator priority and server-authority requirement |
| CX-15 | **NEW #381** | Existing-surface visibility and durable Attention requirement |
| CX-16 | **NEW #381** | Jira-shaped connector-N zero-core-change requirement |
| CX-17 | **NEW #381** | First-party static registration and no dynamic loading requirement |
| CX-18 | Proven + **NEW #381** admission | `tests/modules/integrations/test_adapter_conformance.py:98-169`; `tests/acceptance/increment-1/test_gitlab_integration.py:91-229` |

## Proposal checklist

- [x] Current capability and proposal status are distinguished.
- [x] Core and per-connector ownership are explicit.
- [x] GitLab is refactored in place with no compatibility path.
- [x] GitHub proves the seam against a frozen core.
- [x] Triage, priority, UI projection, and server authority are explicit.
- [x] Connector-N scaffold, registration, and PostgreSQL/`MockTransport` proof are explicit.
- [x] Credential scopes and CSO triggers are explicit.
- [x] Four independently testable phases are defined.
- [x] Every invariant traces to #377 source lines or identifies itself as new in #381.

## Sign-off

This proposal is ready for architecture, security, product-authority, and sequencing review. It is not an
implementation authorization and does not supersede `SPEC.md` or D39.
