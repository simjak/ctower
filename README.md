# ctower

**Durable work control for people and replaceable AI agents.**

ctower keeps the identity, ownership, workflow, proof, and history of work outside the process doing it.
When a terminal closes, a model is replaced, or a provider times out, the worker can be replaced without
inventing what happened. A claim that work is complete counts only when current evidence supports it.

> [!IMPORTANT]
> ctower is pre-alpha. There is no published package, hosted service, or production deployment.
> The only installed runtime is a private, loopback-only development shadow for low-value work that can be
> reconstructed. Browser surfaces are development-only and unsupported. Do not put production credentials,
> irreplaceable data, or authoritative work into this revision.

Start with the [concepts](https://simjak.github.io/ctower/concepts/), run the
[quickstart](https://simjak.github.io/ctower/quickstart/), then use the
[CLI reference](https://simjak.github.io/ctower/reference/cli/).

## Why it exists

Long-running work fails in predictable ways:

- **Custody disappears.** A task belongs to a chat or process that no longer exists.
- **Claims outrun proof.** “Done” survives after the artifact changes or the check becomes stale.
- **Retries duplicate effects.** A timeout hides whether a command was rejected, committed, or still
  waiting for acknowledgement.
- **Readers invent calm.** An unavailable source is rendered as an empty board or a healthy service.

ctower records these states explicitly. Tickets retain one permanent identity and one accountable
custodian. Workflow revisions and policy inputs are pinned. Evidence is bound to an exact candidate.
Commands are idempotent. Reads carry freshness and completeness. Missing or conflicting truth becomes a
typed refusal or an unknown state, never a guessed success.

## The product model

The product is larger than a task list, but each part has one responsibility:

| Concept | Responsibility |
|---|---|
| Requests and conversations | Preserve intent before it becomes executable work. |
| Tickets | Hold the permanent outcome, project, custody, relationships, and lifecycle. |
| Workflows | Pin the legal stage graph and the policies used for one run. |
| Proof | Freeze criteria, bind evidence to a candidate, and gate completion. |
| Boards and delivery views | Rebuild project and portfolio reads from accepted facts. |
| Routines | Schedule repeatable work without turning a schedule into outcome truth. |
| Integrations | Translate strict provider payloads while the control plane keeps custody. |
| Knowledge | Retain bounded, attributable results without storing raw private sessions. |
| Access | Resolve people, machine credentials, project grants, and revocation into typed authority. |
| Runtime and agents | Lease work to replaceable processes while the record remains authoritative. |
| Workspaces | Link durable work to runner-side materialization without treating a host path as truth. |
| Metrics and health | Derive status at named watermarks and show missing evidence as unknown. |

The [architecture atlas](ARCHITECTURE.md) is the compact repository map. The public
[concept guide](https://simjak.github.io/ctower/concepts/) explains the same model from a user's point of
view.

## What works today

The repository contains a tested development slice, not a finished service.

| Available in the development slice | Boundary |
|---|---|
| Capture Requests, preserve Rulings, and read a deterministic morning digest | Authenticated API and protected CLI only. |
| Create, assign, prioritize, block, defer, relate, resolve, and close Tickets | Completion is proof-gated; unavailable sources do not become empty results. |
| Run a pinned four-stage Workflow with frozen criteria, evidence, and verdicts | Richer per-stage proof and independent producer checks remain planned. |
| Read Ticket history, Board views, project delivery, Inbox, Knowledge, and recorded work sessions | These are development contracts with no compatibility promise. |
| Validate, plan, apply, and export one versioned company configuration | Applying configuration does not activate workers, integrations, or external effects. |
| Use generated HTTP clients and a closed protected CLI command set | Unknown commands and untyped payloads are refused. |
| Exercise bounded GitLab and GitHub issue integrations | They are fixed development integrations, not a public connector platform. |
| Run fixed routines and observe health, durability, and acknowledgement state | A schedule or process exit never asserts a successful outcome. |
| Install one supervised loopback shadow runtime on a private Linux host | Its primary and standby share a host; it is not production durability. |
| Verify a private read-only Console server foundation | There is no product panel, safe terminal renderer, typing, or public route. |

The current [availability page](https://simjak.github.io/ctower/start-here/availability/) names the shipped,
development-only, planned, and unsupported boundaries in more detail.

## What is planned

The accepted design continues in layers:

- durable agent registration, liveness, capacity reporting, bounded recovery, and recovery drills;
- recorded project planning before dispatch, deterministic daily work stacks, and typed confirmations;
- bounded and redacted session mining into revision-pinned knowledge;
- one canonical Ticket movement stream, typed stall clocks, and complete worklist reads;
- one public catalog engine over private versioned company content; and
- first-class workspace records whose directories and mounted bytes remain runner-side.

These are design commitments, not claims that commands or product pages already exist. Their public
concept, quickstart, and reference pages ship with their implementations.

## Run the executable tour

You need Git, Python 3.12–3.14, Docker with Compose, `just`, and `uv`:

```bash
git clone https://github.com/simjak/ctower.git
cd ctower
just quickstart
```

The recipe creates an isolated environment, installs the hash-locked verification dependencies, launches a
disposable PostgreSQL-backed API, checks health through the installed CLI, drives one Ticket through the
complete proof-gated Workflow, and removes the temporary environment.

For repository work, install the complete verification toolchain and run `just check` while developing.
Run `just verify` only from the clean candidate you intend to review. See
[Repository setup](https://simjak.github.io/ctower/start-here/repository-setup/) and
[Local development](https://simjak.github.io/ctower/local-development/).

## Documentation

- [Concepts](https://simjak.github.io/ctower/concepts/) — the model and its boundaries.
- [Quickstart](https://simjak.github.io/ctower/quickstart/) — one first working result.
- [CLI reference](https://simjak.github.io/ctower/reference/cli/) — the current closed command surface.
- [HTTP API](https://simjak.github.io/ctower/reference/http-api/) — operation families and generated clients.
- [Self-hosting boundary](https://simjak.github.io/ctower/self-hosting/) — the exact private shadow topology
  and why it is not production.
- [Contributing](CONTRIBUTING.md) — repository workflow and review expectations.

## License

Apache License 2.0. See [LICENSE](LICENSE).
