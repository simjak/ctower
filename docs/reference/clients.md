# Generated clients and contracts

If you are writing code against ctower rather than driving the CLI, use the generated packages. They are
produced from the authored contracts and are checked for drift on every gate run, so they cannot quietly
disagree with the server.

## The three layers

```text
contracts/          authored, hand-written, reviewed   <- the source of truth
    │  python3 -m tools.codegen --root . --write
    ▼
generated/          machine-owned, never hand-edited
    ├── python/ctower_client      strict client, models, operation registry
    ├── python/ctower_contracts   vendored JSON schemas as a runtime resource
    └── .generated-manifest.json  input and output digests
```

`contracts/` is authored. `generated/` is machine-owned and must match its manifest. Editing a generated
file is a gate failure, not a style preference.

## `ctower_client`

A strict, typed HTTP client package.

| Export | Purpose |
|---|---|
| `CtowerClient` | Context-managed HTTP client; one method per operation, e.g. `create_ticket`, `get_board`, `record_proof_verdict` |
| `CtowerProblemError` | Raised on a typed refusal; carries the parsed `Problem` |
| `ctower_client.models` | Pydantic v2 models for every request, response, and enum in the contract |
| `ctower_client.operations` | `OPERATIONS`, `CLI_OPERATIONS`, `OperationSpec`, `SpoolPolicy`, `operation_for_cli` |

The models are strict: `extra="forbid"`, frozen where appropriate. An unexpected field is an error rather
than a silently ignored key.

### The operation registry

`OPERATIONS` maps each operation ID to an `OperationSpec`:

```python
OperationSpec(
    operation_id="createTicket",
    client_method="create_ticket",
    method="POST",
    path="/v1/tickets",
    request_model=TicketCreateRequest,
    response_model=TicketCommandResult,
    cli_names=("ticket capture", "ticket create"),
    mutation=True,
    spool_policy=SpoolPolicy.ALLOWED,
    principal=None,
    refusal_only=False,
)
```

This registry is the **closed replay inventory** for the protected CLI, not a general dispatcher. It is what
lets the spool replay a queued mutation without a second hand-maintained table, and what the CLI parity test
asserts the parser against.

`CLI_OPERATIONS` maps CLI names to the same specs; `operation_for_cli(name)` is the lookup.

## `ctower_contracts`

Vendors the authored JSON schemas into a local-only runtime resource, so schema validation needs no
filesystem layout and no network.

| Export | Purpose |
|---|---|
| `CATALOG` | The loaded contract catalog |
| `schema_for`, `validator_for` | Resolve one schema or a validator for it |
| `verify_all` | Verify the whole catalog |
| `ContractCatalog` | The catalog type |

Resolution rejects network references and any path that escapes the authored contract tree.

## Regenerating and checking

```bash
python3 -m tools.codegen --root . --write     # regenerate
python3 -m tools.codegen --root . --check     # verify no drift (runs inside `just check`)
```

`generated/.generated-manifest.json` owns the exact input and output digests. `just check` runs the
`--check` form and also byte-compiles `generated/python`, so a hand-edited generated file fails the gate.

Both packages and `ctower_contracts/schemas.json` ship inside the verified development wheel.

## What generated presence does not mean

A generated client existing does not establish a stable external API, a supported package release, a
deployment, or any runtime activation. The packages are build outputs of a pre-alpha contract.

## Also authored, also worth reading

| Directory | Contents |
|---|---|
| `contracts/http/` | The OpenAPI document |
| `contracts/domain/` | Ticket, event, task-management, project-delivery, migration, and outbox schemas |
| `contracts/workflow/` | Workflow and review-plan schemas |
| `contracts/execution/` | Execution, gate, and evidence policy schemas |
| `contracts/evidence/` | Evidence and object manifest schemas |
| `contracts/operations/` | Durability policy and acknowledgement, health, anchors, backup, restore |
| `contracts/components/` | The universal `VersionedComponent` envelope and its component kinds |
| `packs/` | Staged workflow, policy, routine, and component payloads |

`packs/` are **staged fixtures**: draft or staged desired-state payloads for review and code generation,
not published, active, or authoritative until schema, compatibility, conformance, digest, authorization, and
activation checks pass.

## Related

- [HTTP API reference](http-api.md) — every operation.
- [CLI reference](cli.md) — the same surface from a shell.
- [The generated-artifacts README](https://github.com/simjak/ctower/blob/main/generated/README.md).
