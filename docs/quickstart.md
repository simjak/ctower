# Quickstart

By the end of this page you will have a verified checkout and you will have watched one ticket travel the
complete four-stage lifecycle — capture, frame, verify, close — against a real PostgreSQL 17 database,
ending in the immutable facts `resolved` and `closed`.

!!! note "What this quickstart is not"
    This page verifies a checkout; it does not install the separately documented
    [private-VPS E2 shadow runtime](https://github.com/simjak/ctower/tree/main/deploy/private-vps/development).
    The lifecycle below runs
    inside the repository's acceptance gate, which owns its own disposable database. The shadow runtime is
    loopback-only, `SHADOW_ONLY_CP3_D_NOT_PROVEN`, and restricted to low-value reconstructible dogfood.

## 1. Prerequisites

| Need | Why |
|---|---|
| Git | Clone the repository |
| Python `>=3.12,<3.15` (CI uses 3.13.14) | Run the gates; the product runtime pin is still unresolved |
| `just` | The canonical gate entry points |
| Docker with Compose | The acceptance tests start and stop a disposable PostgreSQL 17 fixture |
| Node 24 and pnpm 10.20.0 | The frozen browser-workspace checks inside `just check` |
| Actionlint and Gitleaks on `PATH` | Workflow linting and secret scanning inside `just check` |

## 2. Clone and install the verification dependencies

```bash
git clone https://github.com/simjak/ctower.git
cd ctower
python3 -m pip install --require-hashes -r requirements/verify.txt
pnpm install --frozen-lockfile --ignore-scripts
```

The requirement set is fully hash-locked. It pins the *verification host*; it does not select ctower's
product runtime and does not install ctower as a service.

## 3. Prove the checkout

```bash
just check
```

This is the warm gate: formatting, lint, strict typing, the strict documentation build, Actionlint,
version mirroring, repository and contract tests, generated-artifact drift, traceability, and an
intended-tree secret scan. It mutates nothing and needs no database.

If it passes, your checkout matches the candidate the maintainers verify.

## 4. Run your first ticket end to end

```bash
python3 -m pytest tests/acceptance/increment-1/test_four_stage_workflow.py -q
```

Expect `2 passed` in a few seconds. The test session starts `deploy/development/compose.yaml`, migrates a
fresh database, bootstraps a tenant, drives one ticket through the whole four-stage workflow, and tears the
fixture down again.

Docker is required. Without it the session fails immediately with
`docker is required for Postgres acceptance tests`.

### What just happened

The ticket moved through the `ctower.trust-spine-four-stage@1` workflow, whose graph lives in
`packs/workflows/ctower.trust-spine-four-stage/v1.yaml`. Each arrow is a declared transition guarded by a
predicate — the engine refuses any move that is not declared:

```text
capture ──entry.ready@1──> frame ──criteria.frozen@1──> verify ──proof.current@1──> close
```

The three predicates are not equally strong, and the difference matters: `entry.ready@1` asks whether the
ticket is admitted and unblocked, `criteria.frozen@1` asks whether the acceptance criteria are frozen, and
only `proof.current@1` requires evidence that is current for this candidate, plus a passing verdict wherever
a criterion demands one. Resolving and closing the ticket check `proof.current@1` again.

In order, the ticket:

1. **was created** with a custodian, a priority, a typed source reference, and a title;
2. **started the workflow**, which pins the exact workflow, execution-policy, gate-policy, and
   evidence-policy references *and their digests* to the run;
3. **moved to `frame`**;
4. **froze its acceptance criteria** against a candidate digest — after this the criteria cannot be edited,
   only superseded;
5. **moved to `verify`**;
6. **recorded evidence** binding an artifact digest to a named criterion and to that exact candidate;
7. **received a verdict from a different principal** — the principal who froze the criteria cannot record
   the verdict, and trying is refused as `proof-self-review-refused`. That is the independence the kernel
   enforces; it does not compare the reviewer with whoever produced the evidence, which is
   [specified and not enforced](concepts/proof.md#verdicts-and-independence);
8. **moved to `close`** only because current proof existed for the current candidate;
9. **resolved and closed**, appending the two lifecycle facts atomically.

The same test also proves the negative path: evidence whose digest does not match the candidate is rejected
with `proof-evidence-digest-mismatch`, and no partial state is written.

### Two more slices worth running

```bash
python3 -m pytest tests/acceptance/increment-1/test_synthetic_operations.py tests/acceptance/increment-1/test_ctl.py -q
```

`test_synthetic_operations.py` exercises the public `synthetic run` operation, which drives that entire
four-stage lifecycle server-side and asserts the run finished with lifecycle facts `resolved,closed`.
`test_ctl.py` exercises `ctowerctl` itself: stdin-only authority, writing a command to the encrypted local
queue before sending it, and the "committed here, off-host acknowledgement still pending" result
(`durability_pending`) you should expect from a normal write.

## 5. Run the full gate

```bash
just verify
```

`just verify` is the release gate. It refuses a dirty tree, re-runs the warm gate, executes the required
suites with branch coverage, scans the complete reachable history for secrets, and proves a clean tree
afterwards. Run it only from a clean committed candidate you intend to validate.

It validates the repository. It does not install ctower, make a database durable, or create a supported
tenant.

## 6. What the commands look like

The private-VPS E2 shadow runtime drives work through the same `ctowerctl` interface (installed as both
`ctowerctl` and `ctl`, with a local `ctower-shadow-ctl` secret-reference wrapper). The shapes below are
exact — every flag is checked against `apps/ctowerctl/src/ctowerctl/_parser.py` — but they remain
development-only examples, not a stable external API.

Authority is always one line on stdin, never an argument or an environment variable:

```bash
read -r -s -p "Authority: " authority
printf '\n'
printf '%s\n' "${authority}" |
  ctl --base-url http://127.0.0.1:8080 control health
unset authority
```

Creating a ticket:

```bash
printf '%s\n' "${authority}" |
  ctl --base-url http://127.0.0.1:8080 ticket create \
    --priority P1 \
    --source-kind operator-cli \
    --source-ref operator-cli:first-ticket \
    --title "First durable ticket"
```

The CLI generates and prints the command ID. The authenticated principal becomes the initial custodian;
both values can still be supplied explicitly when a caller needs coordinated replay or deliberate custody.

A normal, healthy result here is **exit `75`** with `"state":"queued"` and
`"reason_code":"durability_pending"` — the machine-readable way of saying "committed here, waiting for
another host to acknowledge it". That is not a failure: the result is committed and the off-host
acknowledgement has not landed yet. Read
[Durability and acceptance](concepts/durability.md) before treating `75` as an error, and
[the agent operating contract](agents/operating-contract.md) before retrying anything.

## Where to go next

- [Concepts](concepts/index.md) — the vocabulary these commands use.
- [CLI reference](reference/cli.md) — every command and flag.
- [For agents](agents/operating-contract.md) — exit codes, idempotency, and refusal handling.
- [Repository setup](start-here/repository-setup.md) and
  [the development walking slice](getting-started.md) — the maintainer-facing view of the same gates.
