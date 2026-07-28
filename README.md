# ctower

**A control plane for work done by people and AI agents, where the proof stays attached to the work.**

Most trackers store claims. A ticket says "done" because somebody moved a card. ctower stores proof
instead: a step cannot close until the thing that proves it is attached — a test run, a screenshot, the
digest of what was deployed, a review by someone other than the author. If the proof is missing, the work
is not done, and ctower says so plainly rather than letting it through.

**In one sentence:** agents can plan, build and finish work without asking permission at every step, and
nothing they do reaches the outside world without a narrow, short-lived permission and a receipt that
records what happened.

> [!IMPORTANT]
> **Status: pre-alpha, version `0.0.0`.** There is no release, no package, and no supported way to install
> or deploy ctower. The command line is the only interface; browser work is deliberately deferred. The part
> that reaches the outside world — deploys, messages, payments — is specified but not built. Do not use
> this to manage real work yet. [What works today](#what-works-today) is the honest split.

## Why it exists

Work now runs through a mix of humans and AI agents. Both forget things. Both lose everything they knew
when a session ends, a terminal closes, or a machine dies. Chat history is not a system of record, and a
card on a board proves nothing.

ctower is meant to be the part that does not forget: the ticket is permanent, the process is data you can
version, the proof is attached to the exact work it checked, and the agents doing the work are
replaceable.

**People are asked for four things only:** is this the right thing to build, does it cross a new security
or architecture line, is it destructive or hard to undo, and is this an incident. Everything else is
decided on the evidence.

## How it works, end to end

```
  SOMETHING NEEDS DOING
  today: an authenticated HTTP call, or a command you type
  planned: email, chat, webhooks, a schedule
        |
        v
  IT BECOMES A THREAD
  every message is kept, in order, with a record of where it came
  from. Nothing is summarised away or overwritten.
        |
        v
  A TICKET IS OPENED
  a permanent id, the outcome being promised, and an owner.
  Everything else hangs off this.
        |
        v
  THE TICKET PICKS A PROCESS
  the steps this kind of work has to pass through, and the rules
  for each step. The process is data you version, not code you
  redeploy, so different work can follow different processes.
        |
        v
  +----------------------------------------------------------+
  |  CAN THIS STEP CLOSE?                                    |
  |    Is the proof attached?                                |
  |    Does it match this exact version of the work?         |
  |    Did someone other than the author pass it?            |
  +----------------------------------------------------------+
        |                                |
       yes                              no
        |                                |
        v                                v
  THE WORK IS PICKED UP            NOTHING CHANGES
  one worker at a time, so two     and you are told exactly what
  never collide. If one dies,      is missing. A check that never
  the next resumes where it        ran is never counted as having
  stopped.  [planned]              passed.
        |
        v
  PROOF IS ATTACHED
  a test name, a run id, a digest — something a stranger can
  re-check months later without having been there. Change the
  work, and proof that depended on the old version stops
  counting.
        |
        v
  IT REACHES THE OUTSIDE WORLD  [planned]
  a deploy, a message, a payment. Each one gets a narrow,
  short-lived permission, and the receipt comes back in.
        |
        v
  YOU CAN SEE WHAT HAPPENED
  the board, the whole history of a ticket, what shipped — all
  rebuilt from the recorded facts, never typed in by hand.
```

`[planned]` marks a step that is designed and specified but not built yet.

## A day in the life

These are the three situations ctower is being built for. Parts of each work today and parts do not — the
next section says exactly which.

**A bug arrives at 3am.**
The message becomes a thread, then a ticket. The process for bugs says *find the cause before you fix
it*, so the fix step stays shut until something explaining the cause is attached. A worker picks the
ticket up, writes a failing test, and fixes it. Review needs a second, independent pass. Shipping is
refused while the docs are out of date. The deploy leaves a receipt, and a later check confirms that what
is running is what was built. Nobody was woken up, and every step can be re-checked in the morning.

**Someone asks for single sign-on.**
Planning produces a design and a spec, both attached to the ticket as proof. The plan touches
authentication, which the rules mark as a new security line — so ctower stops and asks one person, once,
with the recommendation and the consequences spelled out. After the yes, the rest runs on its own, and the
security review is required this time because the rules said so, not because somebody remembered.

**A machine dies mid-deploy.**
Its permission to act expires, and anything it says afterwards is ignored. The next run starts from the
last known good point, sees the deploy already left a receipt, and reconciles instead of deploying twice.
The ticket never lied, because its state was never stored inside that machine.

## What works today

Everything in the left column is in the main line of the repository and covered by tests that run in the
project's own checks. Everything in the right column is specified and designed, and not built.

| Works today | Designed, not built yet |
|---|---|
| Open a ticket, set its priority, assign it, block and unblock it, defer it, comment on it, link it to other tickets, resolve and close it | Any supported way to install, deploy, or run a hosted instance |
| A four-step flow — take it in, agree what "done" means, check it, close it — where every step is gated on proof and the verdict cannot come from the author | A web interface. The command line is the only one, on purpose, for now |
| Proof tied to the exact version of the work it checked: change the work and the proof that depended on the old version stops counting | Anything that reaches the outside world: real deploys, messages, payments, receipts, incident recovery |
| A board with six lanes, the full history of every ticket, and a per-project delivery view, all rebuilt from recorded facts | Fleets of agents working in parallel, with permissions that expire and automatic resume after a crash |
| A command line that keeps each command in an encrypted local queue and sends it when it can, so nothing is lost if the server or the network is down | Connectors that read from email, chat, or a source host |
| Inbound messages stored durably with their source, and a step that turns one into a ticket without duplicating it if the request is retried | Memory that lets a worker recall how something was solved months ago |
| A self-test that drives one ticket through the whole four-step flow against a real PostgreSQL database | Richer process authoring and deeper rules than the flow above |

One thing worth naming: a long-running instance that keeps its data across restarts has been proven on a
development branch, but it is **not** in the main line yet, so it is not claimed above.

## Getting started

There is no supported way to install or deploy ctower, and nothing to `pip install`. That is the honest
answer, and it stays in this README until it changes.

What you *can* do right now:

**1. Read what it is meant to do.** The [documentation site](https://simjak.github.io/ctower/) starts with
an overview and the [shared vocabulary](https://simjak.github.io/ctower/concepts/).

**2. Clone it and run the project's own checks.** This proves the repository is sound on your machine. It
does not install or start anything.

```bash
git clone https://github.com/simjak/ctower.git
cd ctower
python -m pip install --require-hashes -r requirements/verify.txt
pnpm install --frozen-lockfile --ignore-scripts
just check
```

You also need a [Gitleaks](https://github.com/gitleaks/gitleaks) binary on your `PATH`; the checks call it
and never download anything themselves. The
[development guide](https://simjak.github.io/ctower/contributing/development/) covers the rest.

**3. Read the test that proves the flow.** `tests/acceptance/increment-1/test_four_stage_workflow.py` is
the shortest honest description of what ctower actually enforces. `just verify` runs the full set against
disposable PostgreSQL containers and needs Docker.

**4. Follow along, or help.** [SPEC.md](SPEC.md) is what is being built and
[IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md) is the order it is being built in. Watch the
repository to hear when the first installable version lands.

## Words you will meet

- **Ticket** — the permanent record of an outcome somebody promised. Everything else attaches to it.
- **Process** — the steps a kind of work must pass through and the rules for each step. It is versioned
  data, not code, so changing it does not mean a deploy.
- **Proof** — something attached to a step that shows the step really happened, tied to the exact version
  of the work it checked.
- **Refusal** — what happens when something required is missing: ctower changes nothing and tells you
  exactly what it wanted. A check that never ran is never treated as a pass.

## Scope, in the project's own words

Two scope statements are repeated verbatim across this repository, and other documents are checked against
them:

> Public API + protected CLI precede I1 source-of-truth cutover.
>
> Browser implementation, browser evidence, and browser E2E first activate at CT-I2-005 / I2.4.

In plain terms: the HTTP API and the command line are built first, and ctower does not become the system of
record for its own work until they hold up. Browser work — the interface, its tests, and its proof — starts
later, at a planned point the roadmap calls I2.4. `I1`, `I2.4` and `CT-I2-005` are stage names from
[IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md), not version numbers.

## Go deeper

- [Overview](https://simjak.github.io/ctower/) and [Quickstart](https://simjak.github.io/ctower/quickstart/)
  — what ctower is, and the shortest path through it.
- [Concepts](https://simjak.github.io/ctower/concepts/) — tickets, processes, proof, board views, and what
  "durable" means here.
- [Reference](https://simjak.github.io/ctower/reference/cli/) — every command and every HTTP operation.
- [For agents](https://simjak.github.io/ctower/agents/operating-contract/) — how an automated caller
  should behave: retries, exit codes, and what each refusal means.
- [Advanced and internals](https://simjak.github.io/ctower/internals/) — delivery state, verification
  evidence, and operational boundaries.
- [SPEC.md](SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md), and
  [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md) — the engineering records. Dense on purpose.

## Contributing

Contributions are welcome, especially anything that proves one complete path end to end. Read
[CONTRIBUTING.md](CONTRIBUTING.md) and the
[documentation policy](https://simjak.github.io/ctower/contributing/documentation/) first.

To report a vulnerability, follow [SECURITY.md](SECURITY.md) — please do not open a public issue.

## License

Apache License 2.0. See [LICENSE](LICENSE).
