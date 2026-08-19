# ctower-runner boundary

Python worker-plane composition root. It composes separately versioned Harness, Supervisor,
Target, Workspace, and Telemetry Adapters through `ctower-runner-sdk`; it receives fenced jobs and
returns observations, and it never owns ticket, workflow, gate, or effect truth.

`hermes/` is the first real Adapter (CT-I1-041). Because that harness already ships per-provider
credential pools, rotation strategies, and an ordered fallback ladder, this binding **configures
and observes both layers and implements neither** — no second rotation policy competes with a
working one, and ctower never writes the engine's own `auth.json`. One writer per file.

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
