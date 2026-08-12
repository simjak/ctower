# HTTP API reference

The authored HTTP contract is `contracts/http/openapi.yaml` — an OpenAPI 3.1.0 document titled *ctower first
durable-ticket slice*, version `0.0.0`. It declares **86 operations**. The API schema version is separate
from the repository release version.

!!! warning "Development contract, not a supported API"
    This surface exists so the CLI, the generated clients, and the tests share one definition. It is not a
    stable external API and there is no compatibility promise between revisions. The private-VPS E2 shadow
    runtime serves it only on loopback for low-value reconstructible dogfood; that is not external or
    production API support. See the [Quickstart](../quickstart.md).

!!! info "Where this page comes from"
    The tables below are derived from the generated operation registry
    `generated/python/ctower_client/operations.py` and the response codes in the authored OpenAPI document.
    The registry is machine-owned: `just check` runs `tools.codegen --check`, which fails if it drifts from
    the authored contract. Read the OpenAPI document for request and response schemas; this page is the
    index, not a second copy of them.

## Conventions

### Authentication

Most operations use bearer authentication with an opaque token (`securitySchemes.bearerAuth`). The
first-tenant bootstrap additionally requires the `X-Ctower-Bootstrap-Capability` header, a string of 32–256
characters. The Console browser operations instead use the secure `__Host-ctower_session` cookie, require an
exact configured HTTPS `Origin`, and require `X-Ctower-CSRF` to equal both its secure cookie and persisted
digest. Bearer credentials do not authorize those browser routes.

### Idempotency

Every mutation requires an `Idempotency-Key` header containing a UUID. Replaying the same key with the same
semantics returns the original result; the same key with different semantics is refused as
`idempotency-conflict`. This is the header the CLI's `--command-id` becomes.

### Durability responses

A mutation returns `200`/`201` when the write is accepted off host, and `202` when the semantic result is
committed but the off-host acknowledgement is pending. A `202` carries `Retry-After`, an integer of 1–60
seconds. See [Durability and acceptance](../concepts/durability.md).

### Refusals

Refusals are typed problem documents carrying `type`, `title`, `status`, `detail`, and a `code` from a
closed enumeration of 199 values, plus the optional diagnostic fields `command_id`, `current_version`,
`unmet_facts`, and `prohibited_classes`. See [Refusals](../agents/refusals.md).

### Path and query parameters

| Parameter | In | Constraint |
|---|---|---|
| `ticket_id`, `request_id`, `ruling_id`, `console_session_id`, `outbox_id`, `run_id`, `effect_id` | path | UUID |
| `project_key` | path | `^[a-z][a-z0-9-]{2,63}$` |
| `cursor` | query | integer ≥ 0, default 0 |
| `limit` | query | integer 1–100, default 50 |
| `lane` | query | `backlog`, `ready`, `in_progress`, `in_review`, `blocked`, `complete` |
| `priority` | query | `P0`, `P1`, `P2` |
| `stage_key` | query | `^[a-z][a-z0-9._-]*$` |
| `custodian_id`, `assignee_id` | query | UUID |
| `source_kind` | query | 1–64 characters |
| `source_ref` | query | 1–256 characters |

## Operations

The **Spool** column records whether the protected CLI may durably queue the operation for replay. `forbidden`
means it is sent online or not at all.

### Bootstrap

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/bootstrap/first-tenant` | `bootstrapFirstTenant` | `bootstrap first-tenant` | mutation | forbidden | `201`, `202`, `401`, `403`, `409`, `410`, `422` |

### Project-seat credentials

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/admin/seat-credentials` | `issueSeatCredential` | `credential seat issue` | mutation | forbidden | `201`, `202`, `401`, `403`, `409`, `422`, `503` |
| `POST` | `/v1/admin/seat-credentials/{credential_id}/revocation` | `revokeSeatCredential` | `credential seat revoke` | mutation | forbidden | `200`, `202`, `401`, `403`, `404`, `409`, `422`, `503` |

### Tickets

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/tickets` | `createTicket` | `ticket capture`<br>`ticket create` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `422` |
| `GET` | `/v1/tickets/{ticket_id}` | `getTicket` | `ticket query`<br>`ticket show` | query | forbidden | `200`, `401`, `404`, `422` |
| `GET` | `/v1/tickets/{ticket_id}/assignments` | `listTicketAssignments` | `ticket assignments` | query | forbidden | `200`, `401`, `404`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/assignments` | `changeTicketAssignment` | `ticket assign` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |
| `GET` | `/v1/tickets/{ticket_id}/audit` | `listTicketAuditEvents` | `ticket audit` | query | forbidden | `200`, `401`, `404`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/comments` | `addTicketComment` | `ticket comment add` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/custody` | `transferTicketCustody` | `ticket custody transfer` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/intents` | `applyTicketIntent` | `ticket admit`<br>`ticket defer`<br>`ticket block`<br>`ticket unblock`<br>`ticket reopen` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/priority` | `changeTicketPriority` | `ticket prioritize` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/proof/criteria` | `freezeProofCriteria` | `ticket criteria freeze` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/proof/evidence` | `recordProofEvidence` | `ticket evidence add` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/proof/verdict` | `recordProofVerdict` | `ticket gate verdict` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/relations` | `addTicketRelation` | `ticket relation add` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |
| `GET` | `/v1/tickets/{ticket_id}/timeline` | `getTicketTimeline` | `ticket timeline` | query | forbidden | `200`, `401`, `404`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/workflow/resolve-close` | `resolveCloseWorkflow` | `ticket resolve` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/workflow/start` | `startTicketWorkflow` | `ticket workflow start` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/workflow/transition` | `transitionWorkflow` | `ticket transition` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |
| `GET` | `/v1/tickets/{ticket_id}/workflow/review-dispatches` | `listReviewDispatchEffects` | `ticket review-dispatch list` | query | forbidden | `200`, `401`, `403`, `404`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/workflow/review-dispatches/{effect_id}/consume` | `consumeReviewDispatchEffect` | `ticket review-dispatch consume` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/change-references` | `recordTicketChangeReference` | `ticket change-reference add` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/labels` | `applyTicketLabel` | `ticket label apply` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |

`TicketCreateRequest.initial_custodian_id` is optional at this HTTP boundary. Omission selects the
authenticated principal. A Commander may establish its own custody; an operator omission is refused and
an operator must explicitly name an eligible Commander. Supplying a UUID requests that placement, but the
server authorizes the actor before accepting it.

### Requests

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/requests` | `captureRequest` | `request capture` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `422` |
| `GET` | `/v1/requests` | `listRequests` | `request list` | query | forbidden | `200`, `401`, `403`, `404`, `422` |
| `POST` | `/v1/requests/{request_id}/priority` | `prioritizeRequest` | `request prioritize` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/requests/{request_id}/triage` | `triageRequest` | `request triage` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/requests/{request_id}/owner` | `assignRequestOwner` | `request owner assign` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/requests/{request_id}/ticket-relations` | `relateRequestTicket` | `request ticket relate` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/requests/{request_id}/blockers` | `setRequestBlocker` | `request blocker set` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/requests/{request_id}/closure-evaluations` | `evaluateRequestClosure` | `request closure evaluate` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |

Capture accepts only `project_key` and `text`; the authenticated Actor, submitter, initial owner, native
source alias, UUIDv7 identity, and tenant-wide permanent `R<number>` are server facts. Capture creates no
Ticket. Every semantic change appends an independent fact under `expected_version`; there is no writable
Request status.

The list is an accepted-only read at a named Record watermark. It reports requested, answered, and
unanswered projects separately, so an unanswered source never contributes a fabricated empty result.
Mutation `202` responses remain `durability_pending`; accepted list rows and totals exclude them. The
operator migration helper is deliberately absent from this ordinary HTTP surface. A row whose exact
accepted decision blocker is active includes the complete record-derived `decision_brief`; other rows carry
`null`. An accepted Ruling answers only the exact active blocker occurrence it was bound to; a later marker
reopens and an inactive latest marker returns `null`. The list declares no caller input for brief text,
choices, recommendation, or safe default.

### Rulings

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/rulings` | `appendRuling` | `ruling append` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `422`, `503` |
| `GET` | `/v1/rulings` | `listRulings` | `ruling list` | query | forbidden | `200`, `401`, `403`, `404`, `422` |
| `GET` | `/v1/rulings/{ruling_id}` | `getRuling` | `ruling get` | query | forbidden | `200`, `401`, `403`, `404`, `422` |

Append accepts exact `verbatim` words and either an optional `request_id` or an optional
`supersedes_ruling_id`; the two cannot be combined. The server derives Project, principal, and seat from the
existing authenticated project seat. A Request-linked append must name a current decision Request in that
same Project. Reads expose only accepted facts and keep the stable Ruling ID, server date, byte digest,
attribution, both supersession directions, and the linked Request UUID and `R<number>` reference. A
successor inherits its predecessor's Request link. Listing names requested, answered, and unanswered
Projects plus the Record watermark; pending facts are absent.

### Morning digest

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `GET` | `/v1/digests/morning` | `getMorningDigest` | `digest morning` | query | forbidden | `200`, `401`, `403`, `422` |

The optional `date` query is an ISO calendar date. Omission selects the current Europe/Vilnius date. The
operator-only result has one artifact key and content digest, Request and Ruling watermarks, and the ordered
open-decision, prior-day-Ruling, and Ticket-proof sections. Each section distinguishes a measured zero from
an unknown total and names every unreached scope. The read stores nothing and does not deliver or schedule a
notification. See the [morning digest concept](../concepts/morning-digest.md).

### Console viewer

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/admin/console/sessions` | `allowConsoleSession` | — | mutation | forbidden | `201`, `202`, `401`, `403`, `409`, `422` |
| `POST` | `/v1/admin/console/sessions/{console_session_id}/revocation` | `revokeConsoleSession` | — | mutation | forbidden | `202`, `204`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/admin/console/kill-switch` | `setConsoleKillSwitch` | — | mutation | forbidden | `202`, `204`, `401`, `403`, `422` |
| `GET` | `/v1/console/sessions` | `listVisibleConsoleSessions` | — | query | forbidden | `200`, `401`, `403` |
| `POST` | `/v1/console/sessions/{console_session_id}/grants` | `mintConsoleViewGrant` | — | mutation | forbidden | `201`, `202`, `401`, `403`, `404`, `409` |
| `POST` | `/v1/console/sessions/{console_session_id}/renewals` | `renewConsoleViewGrant` | — | mutation | forbidden | `201`, `202`, `401`, `403`, `404` |
| `GET` | `/v1/console/sessions/{console_session_id}/events` | `streamConsoleEvents` | — | stream claim | forbidden | `200`, `202`, `401`, `403`, `404`, `409`, `422` |

The Console event route refuses every query string before it evaluates stream authority or reads output.
Reconnect supplies the durable cursor only through `Last-Event-ID`, bounded from zero through the maximum
signed 64-bit value; malformed, negative, and larger values refuse before a stream claim.

The three `/v1/admin/console` routes use operator bearer authentication. An allowance request carries the
complete `ConsoleSessionRef` fields plus the fixed `tmux-v1`, `standard`, and `restricted` Phase-1 values.
Revocation carries a 1–500-character reason. The global switch carries `enabled` and a 1–500-character
reason. Allow is the only Console operation emitted into the ordinary protected generated client; the
browser/SSE and empty-204 admin operations remain server-only boundaries and do not create handwritten
browser bearer clients.

The four `/v1/console` routes use `browserSession`, require `X-Ctower-CSRF` (32–256 characters), and require
the presented `Origin` to equal the configured private HTTPS origin. The same CSRF value must appear in the
secure CSRF cookie and match the persisted session digest. Discovery returns only exact current allowed
sessions. Mint and renewal return a grant receipt without its nonce; `maximum_uses` is always `1`, expiry is
at most five minutes, and renewal retains the original continuous-view start for the thirty-minute ceiling.

The event URL carries no credential. `Last-Event-ID` is an optional signed-64-bit durable cursor header.
Success is `text/event-stream` with `Cache-Control: no-store` and `X-Accel-Buffering: no`; compression and
CORS authority are absent. Event shapes are:

- `chunk`: integer `cursor`, base64 `data` representing no more than 16 KiB decoded, and
  `object_digest` as `sha256:<hex>`; the SSE `id` equals the durable cursor.
- `gap`: `reason` is `cursor_unavailable`, `source_truncated`, `unprovable_range`, `slow_consumer`, or
  `rate_limited`; `next_cursor` is an integer or `null`.
- `closed`: `code` is `expired`, `revoked`, `fenced`, `rate_limited`, `slow_consumer`,
  `reauthentication_required`, `globally_disabled`, or `output_unavailable`.

`client_disconnected` is durable internal stream-close evidence after the HTTP transport is gone; it is not
an SSE event because no connected client remains to receive it.

Delivery and replay are each capped at 1 MiB per minute, queued pending bytes at 256 KiB, and grant/revocation
state is polled at least every four seconds. See [Console view grants](../concepts/console-viewer.md) and the
[operator procedure](../operations/console-viewer.md).

### Intake

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/intake` | `submitIntake` | `intake submit` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `413`, `422` |
| `POST` | `/v1/intake/events/{inbound_event_id}/promotion` | `promoteIntakeEvent` | `intake promote` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `413`, `422` |

`413` is the request-body bound (`request-body-too-large`). Both operations accept explicit
`create_request`, `create_ticket`, and `link_ticket` intents (`submitIntake` also defaults to `discussion`).
`create_request` carries no Ticket mutation fields and accepts only authenticated native provenance;
caller-declared external provenance refuses as `request-source-forbidden`. Promotion is idempotent:
promoting an event that already produced a Request or Ticket returns that authority instead of creating a
second one, and an event that is not eligible is refused as `intake-promotion-ineligible` without changing
anything.

### Inbox

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/inbox/messages` | `sendInboxMessage` | `inbox send` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/inbox/notifications` | `ingestInboxNotification` | `inbox notify` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/inbox/messages/{message_id}/ack` | `acknowledgeInboxMessage` | `inbox ack` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/inbox/threads/{thread_id}/promotion` | `promoteInboxThread` | `inbox promote` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `GET` | `/v1/inbox/threads` | `listInboxThreads` | `inbox list` | query | forbidden | `200`, `401`, `404`, `422` |
| `GET` | `/v1/inbox/correspondents` | `listInboxCorrespondents` | `inbox correspondents` | query | forbidden | `200`, `401`, `404`, `422` |
| `GET` | `/v1/inbox/threads/{thread_id}` | `readInboxThread` | `inbox read` | query | forbidden | `200`, `401`, `404`, `422` |
| `GET` | `/v1/inbox/threads/{thread_id}/read-state` | `readInboxMessageState` | `inbox read-state` | query | forbidden | `200`, `401`, `404`, `422` |

`InboxSendRequest` addresses a project seat with `to`, carries 1–65536 characters of `text`, and optionally
names an existing `thread_id`. Omission starts a two-party thread; an existing thread accepts only the other
participant as recipient. `InboxAcknowledgeRequest.state` is `delivered` or `read`, and only the recorded
message recipient may write it. State advances monotonically: a direct `read` acknowledgement appends the
missing `delivered` fact before the `read` fact. A request that repeats the current state, or requests
`delivered` after `read`, changes nothing and is refused as `inbox-acknowledgement-not-advancing`.

`InboxNotificationRequest` contains only `to` and `text`. The authenticated Actor supplies sender identity;
the persisted seat registry resolves the recipient, and an unknown seat is
`inbox-recipient-not-found` without creating one. The server derives one direction-independent thread for
the principal pair. The caller sends the original notification delivery UUID as `Idempotency-Key`, so an
exact retry returns the first result and appends no duplicate message event. This endpoint is additive to
the caller's existing durable delivery and does not provide a switch or cutover mechanism.

Exact mutation replay returns the original result; the same `Idempotency-Key` with different semantics is
`idempotency-conflict`. Other Inbox mutation refusals are `inbox-message-recipient-mismatch`,
`inbox-sender-unaddressable`, `inbox-recipient-not-found`, `inbox-recipient-ambiguous`,
`inbox-recipient-self`, and `inbox-thread-participant-mismatch`. Invalid payloads are `invalid-request`;
missing or participant-inaccessible messages and threads are `tenant-scope-denied`. Every refusal leaves
Inbox state unchanged.

All three reads consume accepted projection state and append no acknowledgement or cursor fact.
`listInboxThreads` is participant-scoped; its optional `unread` query defaults to `false`, and `true` keeps
only threads with unread incoming messages. `readInboxThread` returns messages in position order plus the
fact-derived `read_through_position`; reading does not advance it or reduce unread counts.
`readInboxMessageState` is likewise pure and returns every message's fact-derived `sent`, `delivered`, or
`read` state with nullable delivery/read event IDs and timestamps.

### Knowledge

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/knowledge/documents` | `addKnowledgeDocument` | `knowledge add` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `422`, `503` |
| `GET` | `/v1/knowledge/documents` | `listKnowledgeDocuments` | `knowledge list` | query | forbidden | `200`, `401`, `403`, `422` |
| `GET` | `/v1/knowledge/documents/{document_id}` | `getKnowledgeDocument` | `knowledge get` | query | forbidden | `200`, `401`, `403`, `404`, `422` |

### Attention findings

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/attention/findings` | `appendAttentionFinding` | `attention finding append` | mutation | allowed | `202`, `401`, `403`, `404`, `422` |
| `POST` | `/v1/attention/findings/{finding_id}/disposition` | `recordAttentionFindingDisposition` | `attention finding disposition` | mutation | allowed | `202`, `401`, `403`, `404`, `409`, `422` |

### Recorded work sessions and project events

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `GET` | `/v1/tickets/{ticket_id}/sessions` | `listTicketSessions` | `session ticket` | query | forbidden | `200`, `401`, `404`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/sessions` | `startTicketSession` | `session start` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/tickets/{ticket_id}/sessions/{session_id}/facts` | `recordTicketSessionFact` | `session transition`<br>`session close` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `GET` | `/v1/projects/{project_key}/sessions` | `listProjectSessions` | `session project` | query | forbidden | `200`, `401`, `403`, `404`, `422` |
| `GET` | `/v1/projects/{project_key}/events` | `listProjectEvents` | `project events` | query | forbidden | `200`, `401`, `403`, `404`, `422` |

### Projections and health

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `GET` | `/health` | `getControlHealth` | `control health` | query | forbidden | `200`, `401` |
| `GET` | `/v1/board` | `getBoard` | `board query` | query | forbidden | `200`, `401`, `422` |
| `GET` | `/v1/projects/{project_key}/delivery` | `getProjectDelivery` | `project delivery query` | query | forbidden | `200`, `401`, `404`, `422` |

Project Delivery rows expose `qualifying_stage_slots[]`. Each item has `slot_key`, `state`, a strict
`assigned_seat` union (`{"state":"assigned","seat":ProjectDeliverySeat}` or exactly
`{"state":"unassigned"}`), and nullable `signing_seat`. `ProjectDeliverySeat` contains `seat_key`,
`seat_label`, and its pinned `catalog_revision` (`catalog_key`, `revision`, `content_digest`).

### Operations

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/outbox/{outbox_id}/dispositions` | `recordOutboxPoisonDisposition` | `ops outbox poison dispose` | mutation | allowed | `200`, `202`, `401`, `404`, `409`, `422` |

### Company bundle

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/company/bundle/apply` | `applyCompanyBundle` | `company bundle apply` | mutation | allowed | `200`, `202`, `401`, `403`, `409`, `422`, `503` |
| `GET` | `/v1/company/bundle/export` | `exportCompanyBundle` | `company bundle export` | query | forbidden | `200`, `401`, `403`, `404` |
| `POST` | `/v1/company/bundle/plan` | `planCompanyBundle` | `company bundle plan` | query | forbidden | `200`, `401`, `403`, `409`, `422` |
| `POST` | `/v1/company/bundle/validate` | `validateCompanyBundle` | `company bundle validate` | query | forbidden | `200`, `401`, `403`, `422` |

### Synthetic control

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/control/synthetic-runs` | `runSyntheticWorkflow` | `synthetic run` | mutation | allowed | `201`, `202`, `401`, `403`, `409`, `422` |
| `GET` | `/v1/control/synthetic-runs/{run_id}` | `getSyntheticWorkflowRun` | `synthetic query` | query | forbidden | `200`, `401`, `404`, `422` |

### Dream dispatch

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `GET` | `/v1/runtime/dream-dispatches` | `listDreamDispatchEffects` | `dream-dispatch list` | query | forbidden | `200`, `401`, `403` |
| `POST` | `/v1/runtime/dream-dispatches/{effect_id}/consume` | `consumeDreamDispatchEffect` | `dream-dispatch consume` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `422` |
| `POST` | `/v1/runtime/dream-lane-bindings` | `bindDreamLane` | `dream-lane bind` | mutation | forbidden | `200`, `202`, `401`, `403`, `409`, `422` |

The list is filtered by persisted authority before response materialization. Project seats receive only
their own Project effect and never the fleet effect; operators receive all Project effects and the fleet
effect. Consumption derives scope from the stored effect before checking whether it was consumed or whether
the caller has a qualifying lane/model binding. Foreign Project consumption and non-operator fleet
consumption return `project-scope-denied` without recording an event, outbox row, or consumption.

`DreamDispatchConsumeRequest` contains only `output_digest`, a lowercase SHA-256 digest. The server copies
lane, crew, harness, model, family, effort, and tier from the authenticated principal's persisted substrate
binding; none is accepted from the request. The `202` response uses the ordinary durability-pending and
`Retry-After` contract.

`DreamLaneBindRequest` is the operator-only, online ceremony surface. It accepts the lane and crew plus the
closed `codex` / `gpt-5.6-sol` / `max` / `qwen3.8-max` / `hard` selection. The server resolves the
authenticated principal from the credential, records one canonical event, and creates one immutable
`runtime_dream_lane_bindings` row atomically. It never accepts a principal or model-family claim from the
request. Non-operators receive `dream-lane-binding-operator-required`; an already-bound operator receives
`dream-lane-already-bound`.

### Migration (ctower-project)

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/migrations/ctower-project/commit-development-epoch` | `commitCtowerProjectDevelopmentEpoch` | `migration ctower-project commit-development-epoch` | refusal-only | forbidden | `401`, `409`, `422` |
| `POST` | `/v1/migrations/ctower-project/corrections` | `appendCtowerProjectImportCorrection` | `migration ctower-project correction append` | mutation | forbidden | `201`, `202`, `401`, `409`, `422` |
| `GET` | `/v1/migrations/ctower-project/cutover-health` | `getCtowerProjectCutoverHealth` | `migration ctower-project verify` | query | forbidden | `200`, `401` |
| `POST` | `/v1/migrations/ctower-project/export` | `bindCtowerProjectExportEquality` | `migration ctower-project export` | mutation | forbidden | `200`, `202`, `401`, `409`, `422` |
| `POST` | `/v1/migrations/ctower-project/fence-observations` | `reportCtowerProjectFenceObservation` | `migration ctower-project fence observe` | mutation | forbidden | `201`, `202`, `401`, `403`, `409`, `422` |
| `POST` | `/v1/migrations/ctower-project/import` | `applyCtowerProjectImportBatch` | `migration ctower-project import` | mutation | forbidden | `200`, `202`, `401`, `403`, `409`, `422` |
| `GET` | `/v1/migrations/ctower-project/import-runs/{run_id}` | `getCtowerProjectImportRun` | `migration ctower-project run get` | query | forbidden | `200`, `401`, `404` |
| `POST` | `/v1/migrations/ctower-project/inventory` | `createCtowerProjectImportRun` | `migration ctower-project inventory` | mutation | forbidden | `201`, `202`, `401`, `409`, `422` |
| `POST` | `/v1/migrations/ctower-project/plan` | `bindCtowerProjectAliasPlan` | `migration ctower-project plan` | mutation | forbidden | `200`, `202`, `401`, `409`, `422` |
| `POST` | `/v1/migrations/ctower-project/prepare` | `prepareCtowerProjectCutover` | `migration ctower-project prepare` | refusal-only | forbidden | `401`, `409`, `422` |
| `POST` | `/v1/migrations/ctower-project/reconcile` | `finalizeCtowerProjectImportRun` | `migration ctower-project reconcile` | mutation | forbidden | `200`, `202`, `401`, `409`, `422` |

## Principals

Some operations require a specific principal beyond ordinary authentication. From the registry:

| Principal | Operations |
|---|---|
| `operator` | migration `inventory`, `export`, `plan`, `reconcile`, `corrections`, `import-runs/{run_id}`, `prepare`, `commit-development-epoch` |
| `migration_importer` | migration `import` |
| `fence_observer` | migration `fence-observations` |
| `authenticated` | migration `cutover-health`, project delivery |

Everything else resolves the principal from the bearer credential and the tenant scope.

## Related

- [CLI reference](cli.md) — the command that calls each operation.
- [Generated clients and contracts](clients.md) — the typed client packages.
- [The authored OpenAPI document](https://github.com/simjak/ctower/blob/main/contracts/http/openapi.yaml) —
  request and response schemas.
