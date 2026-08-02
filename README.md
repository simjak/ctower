# ctower

**Keep work alive when the agent doing it disappears.**

ctower is an open-source control plane for long-running work shared by people and replaceable AI agents.
It keeps the ticket, current owner, workflow stage, and proof of completion outside any one model session,
terminal, or laptop. When a worker stops, the record does not.

See the working slice in one command:

```bash
just quickstart
```

That command starts a disposable PostgreSQL database and loopback API, installs the real CLI, drives a
ticket through `capture → frame → verify → close`, checks API health, and tears everything down. On the
maintainer toolchain it completes in about a minute.

> **Pre-alpha.** The repository has a tested development slice, not a production service. There is no
> supported public deployment, browser UI, runner, or hosted offering yet. Use synthetic data only.

## Why ctower exists

Agentic work tends to disappear into the process doing it. A session ends and nobody can answer who owns
the task, what changed, or whether “done” referred to the current artifact. ctower makes those answers
durable.

Use it to build systems where:

- a replacement agent can resume the same work without inventing a new history;
- exactly one accountable principal holds custody at a time;
- a workflow can refuse an undeclared or unproven transition;
- evidence is tied to the exact candidate it checked;
- the board and audit trail are derived from accepted facts, not status prose.

The implemented slice is deliberately narrow. It proves the trust spine before adding breadth such as
remote runners, integrations, or a browser.

## The four ideas

| Idea | What it means |
|---|---|
| **Ticket** | The permanent case file for one outcome. Its identity survives handoffs, retries, and reopened work. |
| **Custody** | The one principal accountable now. A transfer is atomic and audited; assignment is a separate fact. |
| **Stage** | The current step in an immutable workflow revision. The shipped fixture uses `capture`, `frame`, `verify`, and `close`. |
| **Evidence** | A typed claim bound to a criterion and the exact candidate digest it checked. Stale proof cannot approve a changed candidate. |

That separation matters. A ticket may be blocked on the Board, remain in the `verify` stage, and still have
one custodian. Those are three facts, not three spellings of “status.”

## How it fits together

```text
human or agent
      │
      ▼
CLI / typed HTTP client ──► loopback API
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
        Work + custody     Workflow + proof    Read models
             └──────────────────┬──────────────────┘
                                ▼
                    append-only Record module
                                │
                                ▼
                           PostgreSQL
```

Python owns the trusted control plane and CLI. TypeScript is reserved for the browser. Authored contracts
under `contracts/` generate strict clients under `generated/`; browser, CLI, and provider code never bypass
the kernel to write record-tier persistence.

## What works today

- first-tenant bootstrap with an Operator and Commander;
- ticket creation, reads, comments, custody, assignments, priority, blockers, relations, and audit history;
- one four-stage workflow with frozen criteria, candidate-bound evidence, an independent protected verdict,
  and proof-gated closure;
- a read-only six-lane Board and project-delivery projection;
- a strict generated HTTP client and protected `ctowerctl`/`ctl` command surface;
- operator-only issuance and revocation for credentials bound to configured project-seat identities;
- an encrypted local mutation spool and typed refusal/exit semantics;
- a loopback-only, shadow development runtime for low-value reconstructible dogfood.

Not available today: creating arbitrary projects or teams through the CLI, a composed API + PostgreSQL + UI
developer stack, remote agents, effects, production backup/recovery, or an internet-facing deployment.
Self-hosting today means one loopback-only instance on a host you control. The docs name those gaps
directly so a visible schema or directory is never mistaken for a product promise.

## Requirements

The one-command tour needs:

- Git and a checkout of this repository;
- Python `>=3.12,<3.15`;
- Docker with Compose;
- `just` and `uv` on `PATH`.

The full contributor gate additionally needs Node 24, pnpm 10.20.0, Actionlint, and Gitleaks. ctower does
not yet pin a product Python runtime; the verification locks do not make that unresolved choice for it.

## Start here

- [Agent-first getting started](docs/getting-started.md) — prerequisites, the one command, and what it proves.
- [CLI reference](docs/reference/cli.md) — the supported journey and the missing project/team commands.
- [Core concepts](docs/concepts/index.md) — tickets, custody, workflows, proof, and durability.
- [Local development](docs/local-development.md) — the gate loop, the disposable database, and what Compose does not give you.
- [Self-hosting](docs/self-hosting.md) — running your own single-host instance, and what still blocks production.
- [Contributing](CONTRIBUTING.md) — repository workflow and gates.

The [architecture atlas](ARCHITECTURE.md) is the compact engineering map. Dense specifications, decision
history, implementation sequencing, operator runbooks, and ticket plans are preserved under
`docs/internal/` and intentionally excluded from the public documentation site.

## Project status

ctower is public pre-alpha software. The verified slice is suitable for learning, development, and
low-value reconstructible dogfood only. It is not suitable for authoritative work, irreplaceable data, or
an internet-facing deployment.

Contributions are welcome, especially narrow tests, documentation corrections, and complete vertical
slices. Run `just check` while developing. A review candidate must also pass `just verify` from a clean
commit.

Apache-2.0 licensed. Security issues belong in the private reporting path described in
[SECURITY.md](SECURITY.md), never in a public issue.
