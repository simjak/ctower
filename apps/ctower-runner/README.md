# ctower-runner boundary

Python worker-plane composition root. It composes separately versioned Harness, Supervisor,
Target, Workspace, and Telemetry Adapters through `ctower-runner-sdk`; it receives fenced jobs and
returns observations, and it never owns ticket, workflow, gate, or effect truth.

The runner has three real adapters: `hermes/`, `claude_code/`, and the direct `codex/` CLI
adapter. A deterministic fault-injection fake exercises the same shared seam without counting as
a real provider binding. Each adapter is revision-pinned at registration and crosses the seam
through the same five verbs.

Codex has two valid routes, but only one direct Codex binding. The direct `codex` adapter owns a
single CLI account per configuration home, so it provides the pool and fallback layers through
the runner's credential boundary. When Codex is reached through Hermes, it is a runtime under the
`hermes` harness: Hermes owns its provider pool and fallback, and the runner configures and
observes those layers rather than creating a second Codex pool. A model or runtime name never
creates another harness category.

Hermes already ships per-provider credential pools, rotation strategies, and an ordered fallback
ladder, so its adapter **configures and observes both layers and implements neither** — no second
rotation policy competes with a working one, and ctower never writes the engine's credential
files. One writer per file.

| Module | What it owns |
|---|---|
| `spec` | The authored `HarnessSpec` document and the answered survey that derives its roles |
| `substrate` | The four ports it reads through — D10's Supervisor, the gateway log, the engine's credential store, the workspace — plus the generated-client writeback port |
| `liveness` | Hermes-private pane reading: the cap phrasings, the bar-anchored percentage, the timer glyphs |
| `corpus` | Captured hermes footers and the state each must classify to |
| `pool` | The engine's pool, observed through a named-field allowlist and metered, never re-implemented |
| `binding` | The five verbs |

It holds no operator or commander credential, adds no cron, cadence, or backlog authority, advances
no stage, opens no remote or image Seam, and makes no record-tier connection: writeback reaches
ctower through the generated client as the seat, inside `capture`, `transition`, and `evidence`,
with a stage change emitted only as a request.
