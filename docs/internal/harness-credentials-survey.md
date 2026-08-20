# CT-I1-044 — later-wave credentials survey

Status: authored revision `ctower.later-wave-harness-survey/v1`, revision 1.
Observed: 2026-08-20T14:24:08Z.

Dependency truth: CT-I1-043 is landed on `origin/main` through merged PR #539. The Codex
source below is pinned to merge commit `9bc6c352ff2491e9bcec0cd8cfb50a19a4655b99`
(the PR head was `1058d09a9796bba1292b021ee81f57d56e2fccba`). This survey uses the
current-main binding provenance and remains blocked only by its own unanswered later-wave facts.

This is an internal, fail-closed survey. It does not implement or register a later-wave
Adapter. A state is `UNVERIFIED` whenever the reachable evidence does not answer the
question; absence of a binary is evidence that the probe could not run, not proof that a
vendor capability does not exist.

## Row-scope map

| Candidate | Classification required by CT-I1-044 | Effective route on this box | Disposition | HarnessSpec / liveness |
|---|---|---|---|---|
| `openclaw` | Gateway-routed harness | No reachable binary; design-only gateway route | **REFUSED — undecidable** | No registration; liveness `unknown` |
| `qwen-code` | Legal baseline harness value | Installed Qwen Code CLI, invoked as `qwen` | **REFUSED — undecidable** | No registration; liveness `unknown` |
| `zcode` | Stub until a real binding exists | No `zcode` command found; documentation reachability is **UNVERIFIED** | **REFUSED — undecidable** | No registration; liveness `unknown` |
| `deepseek` | **Model, not a harness** | Model through a Hermes profile | **ZERO adapter work** | No deepseek HarnessSpec; inherits `hermes.gateway_log` |

The names and classification are not sufficient to choose `configure` versus `provide`.
For the three harness candidates, at least one layer question is unknown, so the survey
refuses registration rather than guessing a second rotation policy. `deepseek` is not
eligible for that choice: the model is reached through the already-existing Hermes route,
so the correct adapter count is zero.

## Pinned sources

| ID | Revision | Evidence |
|---|---|---|
| `spec-ct-i1-044` | `origin/main` `d72408e7` | `docs/internal/SPEC.md:5342`, full CT-I1-044 row |
| `design-seam-c07` | `c07c049c` | `docs/internal/design/harness-adapter-seam.md:303-322` ten-question template; `:387-411` later-wave classification; `:423-453` never-both rule |
| `auth-runbook-2026-08-17` | runbook update 2026-08-17 | `/srv/projects/mission-control/playbooks/codex-hermes-auth-runbook.md:77-159`; Hermes pool, provider routes, reset/error distinctions, and the no-copy law |
| `hermes-binding-d724` | `d72408e7` | `apps/ctower-runner/src/ctower_runner/hermes/binding.py`; gateway log is serving truth and the binding observes the Hermes pool |
| `claude-binding-d724` | `d72408e7` | `apps/ctower-runner/src/ctower_runner/claude_code/binding.py`; per-home, provided-pool pattern and checkpoint/respawn failover |
| `codex-binding-main-539` | `9bc6c352ff2491e9bcec0cd8cfb50a19a4655b99` | `apps/ctower-runner/src/ctower_runner/codex/binding.py`; PR #539 is merged into `origin/main` at this merge commit (PR head `1058d09a9796bba1292b021ee81f57d56e2fccba`); direct-CLI versus runtime-under-Hermes distinction and pool/substrate reconciliation |
| `qwen-cli-0215` | installed `0.21.5` | `/home/agent/.local/bin/qwen`; `qwen --version` and `qwen --help` |
| `qwen-docs-0215` | installed `0.21.5` | `/home/agent/.local/lib/qwen-code/lib/bundled/qc-helper/docs/configuration/{auth,model-providers,settings}.md` |
| `local-command-absence` | `2026-08-20T14:24:08Z` | `command -v openclaw qwen-code zcode deepseek` — all four names absent; the separate `qwen` binary is present |
| `ctower-weight-registry-d724` | `d72408e7` | `packages/ctower-kernel/src/ctower_kernel/pools/topology.py:89-95`; only codex weights are authored there |

The machine-readable source is `contracts/runner/later-wave-harness-survey.json`; its
strict authored shape is `contracts/runner/later-wave-harness-survey.schema.json`.

## Local binary and document evidence

The exact read-only probes returned:

```text
openclaw: command not found
qwen-code: command not found
qwen: /home/agent/.local/bin/qwen
zcode: command not found
deepseek: command not found
qwen --version: 0.21.5
qwen auth --help: Configure authentication (removed)
```

The installed Qwen package identifies itself as `@qwen-code/qwen-code` version `0.21.5`.
Its reachable docs state:

- `/auth` offers Alibaba ModelStudio (Coding Plan, Token Plan, Standard API Key), third-party
  providers, and custom providers; API-key references are selected through `envKey`, settings,
  `.env`, or environment variables. This proves an env-overridable config surface, not an
  authored-config-only one.
- `--fallback-model` / `modelFallbacks` are ordered **model** fallbacks on capacity errors.
  They do not prove a native credential pool or a credential/provider fallback ladder.
- Coding Plan documentation names an included weekly quota. The exact reset timestamp for
  this installation is not available without an authenticated provider observation.
- Subagents, model providers, cache sharing, and restart-required settings are documented, but
  credential inheritance and credential-rotation invalidation are not documented.
- `modelPricing` is an optional local cost-estimation setting, not an authoritative provider
  credit-weight table. No exact per-model, per-direction Qwen or DeepSeek weights are present
  in the installed docs or ctower's current authored weight registry.

No credential files, environment values, account stores, or live provider requests were read
or performed.

## Per-question evidence table

State vocabulary: `VERIFIED` means the cited source states the narrow fact shown; `N/A` means
the question belongs to a harness and the candidate is a model; `UNVERIFIED` means the role
cannot be chosen from reachable evidence. `UNVERIFIED` is deliberately not coerced to `false`.

### `openclaw` — gateway-routed harness; refused

| Question | Answer | Evidence / falsifiable boundary |
|---|---|---|
| Native pool | **UNVERIFIED** | The design names a gateway auth token plus persisted device key, but no native pool; no binary is reachable. |
| Native fallback | **UNVERIFIED** | No source proves an in-session credential/provider ladder. |
| Config surface / authored-only | **UNVERIFIED** | Two approval planes are named; no authored config or override law is reachable. |
| Identity proof | **VERIFIED, narrow** — persisted device key | This proves device pairing only; an account claim remains unverified. |
| Reset/window semantics | **UNVERIFIED** | No quota, rolling block, reset, or balance semantics are reachable. |
| Rotation cache semantics | **UNVERIFIED** | No rotation or gateway cache invalidation hook is reachable. |
| Subagent inheritance | **UNVERIFIED** | No source proves inheritance across a gateway run. |
| Egress topology | **UNVERIFIED** | ws/wss is named, but shared versus per-entry egress is not. |
| Probe target | **UNVERIFIED** | Gateway run events are named as truth; product/endpoint/model for a representative probe is absent. |
| Credit weights | **UNVERIFIED** | No per-model, per-direction table is reachable. |

Capability declaration: liveness is `unknown` by name. A successful invite is not readiness;
the design's adapter type, non-placeholder gateway token, persisted device key, and
`device_auth`-enabled preflight assertions remain future evidence requirements.

### `qwen-code` — baseline harness; refused

| Question | Answer | Evidence / falsifiable boundary |
|---|---|---|
| Native pool | **UNVERIFIED** | Multiple model providers are documented, but no native credential pool or account rotation is proven. |
| Native fallback | **VERIFIED, model-only** — `--fallback-model` / `modelFallbacks` | Capacity-error fallback is between model IDs; it is not credential/provider fallback. |
| Config surface / authored-only | **VERIFIED** — env-overridable | `settings.json`, `.env`, environment variables, and CLI overrides are documented. |
| Identity proof | **UNVERIFIED** | API-key `envKey` references are documented; no decodable account identity claim is established. |
| Reset/window semantics | **VERIFIED, coarse** — weekly plan | The Coding Plan has an included weekly quota; the exact reset clock is unavailable here. |
| Rotation cache semantics | **UNVERIFIED** | Settings changes require restart, but credential rotation invalidation is not specified. |
| Subagent inheritance | **UNVERIFIED** | Subagents are documented; credential inheritance is not. |
| Egress topology | **UNVERIFIED** | Per-model `baseUrl` exists; actual shared/per-entry egress is not proven. |
| Probe target | **UNVERIFIED** | `qwen` is installed, but no authenticated representative product/endpoint/model call was made. |
| Credit weights | **UNVERIFIED** | Optional `modelPricing` is local estimation; no authoritative directional table is present. |

Capability declaration: liveness is `unknown` by name. The binary exists, but the survey did
not spend credentials or perform a live request. The candidate therefore does not enter the
conformance suite.

### `zcode` — stub; refused

| Question | Answer | Evidence / falsifiable boundary |
|---|---|---|
| Native pool | **UNVERIFIED** | The design keeps zcode as a stub; the command probe found no executable, so a native pool is not established. |
| Native fallback | **UNVERIFIED** | The design keeps zcode as a stub; the command probe found no executable, so a native fallback is not established. |
| Config surface / authored-only | **UNVERIFIED** | The cited design and command probe do not establish a config surface. |
| Identity proof | **UNVERIFIED** | The cited design and command probe do not establish an identity artifact or claim. |
| Reset/window semantics | **UNVERIFIED** | The cited sources do not establish quota, reset, or window semantics. |
| Rotation cache semantics | **UNVERIFIED** | The cited sources do not establish rotation or cache semantics. |
| Subagent inheritance | **UNVERIFIED** | The cited sources do not establish subagent or credential inheritance behavior. |
| Egress topology | **UNVERIFIED** | The cited sources do not establish an egress path or isolation boundary. |
| Probe target | **UNVERIFIED** | The command probe found no executable, so no product, endpoint, or model probe was run; the target remains UNVERIFIED. |
| Credit weights | **UNVERIFIED** | The cited sources do not establish a per-model, per-direction credit table. |

Capability declaration: liveness is `unknown` by name. This remains a stub; a table row is
not an Adapter and no capability declaration is minted.

### `deepseek` — model; zero adapter work

| Question | Answer | Effective route |
|---|---|---|
| Native pool | **N/A — model** | Hermes profile owns the pool; the model name owns none. |
| Native fallback | **N/A — model** | Hermes profile owns the declared fallback ladder. |
| Config surface / authored-only | **N/A — model** | Profile/provider configuration is the authored route. |
| Identity proof | **N/A — model** | Credential entry identity belongs to the effective provider. |
| Reset/window semantics | **N/A — model** | Effective provider quota/credit semantics apply. |
| Rotation cache semantics | **N/A — model** | Hermes profile/gateway restart semantics apply. |
| Subagent inheritance | **N/A — model** | Hermes owns per-task credential leasing. |
| Egress topology | **N/A — model** | Effective Hermes/provider path applies. |
| Probe target | **N/A — model** | Probe the actual Hermes gateway/provider route and the model when exercised. |
| Credit weights | **UNVERIFIED** | Runbook names provider credits, 402 exhaustion, and discount windows, but no exact DeepSeek directional table is authored. |

There is no `deepseek` HarnessSpec, no deepseek adapter, and no new model-specific rotation
policy. The serving truth remains the Hermes gateway/provider log, as the landed binding does.

## Disposition and no-new-policy proof

| Candidate | Pool role | Fallback role | Why |
|---|---|---|---|
| `openclaw` | **UNDECIDABLE** | **UNDECIDABLE** | Unknown native facts refuse the never-both choice. |
| `qwen-code` | **UNDECIDABLE** | **UNDECIDABLE** | A model fallback is not a credential fallback; native pool and credential ladder remain unknown. |
| `zcode` | **UNDECIDABLE** | **UNDECIDABLE** | Stub has no survey evidence. |
| `deepseek` | **N/A** | **N/A** | Model inherits Hermes; adapter work is zero. |

No later-wave candidate is registered as an active `HarnessSpec`. No runtime code, harness
value, rotation policy, credential value, public ingress, or conformance subject is added by
this survey. The only authored decision is the refusal/zero-work disposition above.

## Battery command contract

- Declarative contract: `.venv/bin/python -m ctower_contracts verify --all`
- Warm (pinned verify environment): `PYTHON=.venv/bin/python just check`
- Validation-only conformance proof: the contract verifier checks generated schema definitions
  and references; `tests/conformance/harness-adapter/test_survey_registration.py` generates
  dependency-matrix violations with a bounded Hypothesis search and validates them against the
  closed schema. It does not execute a harness, bind a provider, or add runtime behavior.
- No `just verify` is owed by this docs/contracts-only slice unless the repository gate
  reports that the changed generated contract surface requires it.

## SIGNED-OFF

- seat: engineer
- crew: engineer-044-survey
- model: gpt-5.6-luna
- claim: CT-I1-044 is surveyed for `openclaw`, `qwen-code`, `zcode`, and `deepseek` with revision-pinned evidence; unknowns refuse registration, `deepseek` receives zero adapter work, and no credential value or rotation policy was added.
- stood-under: The full CT-I1-044 row at `d72408e7`, sealed design `c07c049c`, auth runbook, landed Hermes/Claude bindings, merged Codex PR #539 at `9bc6c352ff2491e9bcec0cd8cfb50a19a4655b99`, installed Qwen binary/docs, literal absence probes, strict contract data, and the declarative plus warm batteries.
- if-this-breaks: Re-run the exact source revisions and candidate command probes; do not convert any `UNVERIFIED` answer into a role without a newly reachable fact.

## SIGNED-OFF — 2026-08-20T21:33:29Z

- seat: engineer
- crew: engineer-044-r5
- model: gpt-5.6-luna
- claim: The survey paperwork distinguishes the validation-only schema proof from runtime or binding implementation; the complete dependency matrix and bounded violation search do not activate a harness.
- stood-under: `contracts/runner/later-wave-harness-survey.matrix.json`, the strict survey schema/data pair, and the focused conformance test at the pushed repair head.
- if-this-breaks: Re-run the focused schema test and inspect the matrix-derived violation set; do not describe this proof as a harness execution or binding.

## r6 semantic closure — current-main provenance and single-law validation

The compact matrix is revision 1 and is pinned in both the authored survey and schema by
SHA-256 `cc9f4f9fee632816a9d7825f87cbf8346fccdcc8d5e65dfb4d3f1b30a640cfa5`. It owns the
finite domains, six pair refusals, candidate route-context restrictions, and the evidence
claim-support table. The schema projects those named laws through reusable `$defs`; it does
not collect a 45-row example bank or duplicate a minified candidate branch.

Two previously accepted impossible surveys now refuse in the validation-only contract:
`qwen-code` with `effective_route=qwen-cli` cannot claim a `gateway_endpoint` probe, and
`credit_weights=published_directional` cannot be verified using the installed Qwen docs plus
the Codex-only registry. The latter requires the unavailable evidence type
`qwen-directional-weight-table`, so the authored Qwen answer remains `UNVERIFIED`.

The property oracle derives all 45 question pairs, candidate-context cases, and evidence
claim cases from the matrix. `tests/conformance/harness-adapter/test_survey_registration.py`
remains validation-only: it executes no harness, provider, binding, credential, or live
request.

## SIGNED-OFF — engineer-044-r6

- seat: engineer
- crew: engineer-044-r6
- model: gpt-5.6-luna
- claim: CT-I1-044's compact single-law matrix now refuses the Qwen route/probe contradiction and unsupported directional-weight claim while preserving survey-only scope; CT-I1-043/#539 is recorded as landed on origin/main.
- stood-under: current `origin/main` `9bc6c352ff2491e9bcec0cd8cfb50a19a4655b99`, PR #539 head `1058d09a9796bba1292b021ee81f57d56e2fccba`, matrix digest above, validation-only RED `3 failed, 7 passed`, GREEN `12 passed`, and the exact authored schema/data/docs.
- if-this-breaks: Re-run the route/evidence mutations and the derived property search at the live PR head; do not infer a provider fact, cite unavailable evidence, or activate a later-wave binding.
