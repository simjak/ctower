# ctower-runner-sdk boundary

The harness-adapter seam (CT-I1-041, D72): one revision-pinned `HarnessSpec` parsed as data,
five verbs composed over D10's existing Supervisor Interface, and the sibling `CredentialPool`
Interface resolved at `spawn`. The current public set has three real bindings — Hermes, Claude
Code, and the direct Codex CLI — plus one deterministic fault-injection fake for conformance. It
owns framing, manifests, registry compatibility, seam policy, and the shared conformance
contract; it has no database, ticket, workflow, gate, or effect authority, and it imports no
kernel module.

D10 already owns process control — `probe`, `launch`, `observe`, `deliver_input`, `interrupt`,
`terminate`, `snapshot`, `adopt` — and that vocabulary is not reopened here. This layer adds only
what a *seat* needs: `launch` cannot report that the pane it started is serving a different model
than the one requested, and `probe` cannot report that a lane is alive but past its context window
and therefore no longer trustworthy.

| Module | What it owns |
|---|---|
| `spec` · `survey` | `HarnessSpec` parsed against its authored contract; the answered survey and the per-layer role it decides |
| `seam` · `attempt` · `facts` | The five verbs, an attempt's immutable pin, and the typed facts that cross the seam |
| `policy` | The meaning every binding shares: cap-before-working precedence, writeback authority, collect and teardown rules |
| `guard` | The final pre-dispatch boundary — obtain, verify, and burn one CommandGuard decision per dispatch |
| `credentials` · `rotation` | The pool Interface with no copy verb, three orthogonal entry axes, rotation completion, and probe validity |
| `credits` · `ledger` | Provider-native credit metering and the cost of resilience, layer identity preserved |
| `registry` | What may register (`never both`, answered survey) and what may publish (two real bindings plus one fake) |
| `fake` · `conformance` | The deterministic fault-injection fake, and the subject shape the one shared suite drives |

Three rules explain most of the module boundaries. **Harness-private observation exists only
inside a binding** and crosses the seam as typed facts, so nothing here parses a footer, a
transcript, or a gateway log. **Secrets are references, never values** — the pool's entry
projection reads a named allowlist because credential fields sit adjacent to the metadata being
read. And **never both**: where the harness ships a resilience layer the adapter configures and
observes it, where it lacks one the adapter provides it, and two policies over one credential set
are a race over single-use refresh chains rather than redundancy.

Codex reached through Hermes is a runtime under the Hermes harness, not a fourth binding and not a
second pool. The direct Codex CLI is the `codex` binding; its own configuration home and the
attempt's model are separate pinned references. Registration rejects a model or runtime name when
it is presented as a harness.

Publication is earned, not implied by a single implementation: `registry.publication()` returns
no refusal only when at least two real bindings and one deterministic fault-injection fake have
passed the unchanged shared conformance suite. The current three-real-binding set is therefore
published; a registry with only one real binding remains unpublished.
