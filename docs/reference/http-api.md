# HTTP API reference

The authored HTTP contract is `contracts/http/openapi.yaml` — an OpenAPI 3.1.0 document titled *ctower first
durable-ticket slice*, version `0.0.0`. It declares **41 operations**.

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

Bearer authentication with an opaque token (`securitySchemes.bearerAuth`). The first-tenant bootstrap
additionally requires the `X-Ctower-Bootstrap-Capability` header, a string of 32–256 characters.

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
closed enumeration of 96 values, plus the optional diagnostic fields `command_id`, `current_version`,
`unmet_facts`, and `prohibited_classes`. See [Refusals](../agents/refusals.md).

### Path and query parameters

| Parameter | In | Constraint |
|---|---|---|
| `ticket_id`, `outbox_id`, `run_id` | path | UUID |
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

`TicketCreateRequest.initial_custodian_id` is optional at this HTTP boundary. Omission selects the
authenticated principal. A Commander may establish its own custody; an operator omission is refused and
an operator must explicitly name an eligible Commander. Supplying a UUID requests that placement, but the
server authorizes the actor before accepting it.

### Intake

| Method | Path | Operation | CLI | Kind | Spool | Responses |
|---|---|---|---|---|---|---|
| `POST` | `/v1/intake` | `submitIntake` | `intake submit` | mutation | allowed | `201`, `202`, `401`, `403`, `404`, `409`, `413`, `422` |
| `POST` | `/v1/intake/events/{inbound_event_id}/promotion` | `promoteIntakeEvent` | `intake promote` | mutation | allowed | `200`, `202`, `401`, `403`, `404`, `409`, `413`, `422` |

`413` is the request-body bound (`request-body-too-large`). Promotion is idempotent: promoting an event that
already produced a ticket returns that ticket rather than creating a second one, and an event that is not
eligible is refused as `intake-promotion-ineligible` without changing anything.

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
