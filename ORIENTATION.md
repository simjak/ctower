# Ctower orientation

Refreshed for durable-record cutoff `2026-08-10T05:20:01Z` by scheduled dream
`019fe965-f100-76be-b6cc-388404e2df47`. Read this first, then follow the authority order in
[README.md](README.md): [SPEC.md](SPEC.md) is normative, [DECISIONS.md](DECISIONS.md) is append-only
history, and the architecture atlas and roadmap are derived aids.

## The ten files that matter first

| Order | File | Why it matters |
|---:|---|---|
| 1 | [SPEC.md](SPEC.md) | Current product, architecture, workflow, acceptance, and build contract; version 1.20. |
| 2 | [DECISIONS.md](DECISIONS.md) | Accepted decision lineage through D47; supersede rather than rewrite. |
| 3 | [ARCHITECTURE.md](ARCHITECTURE.md) | Terminal-safe map of the current system; it must not outrun the spec. |
| 4 | [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md) | Sequencing proposal only; it activates no work. |
| 5 | [README.md](README.md) | Honest front door for the pre-alpha `0.21.0` repository and shadow-only boundary. |
| 6 | [Operator Request specification](docs/specs/operator-requests.md) | Accepted phase contract now owned by #400, including custody, numbering, channels, and cutover gates. |
| 7 | [Connector specification](docs/specs/connectors.md) | Provider-neutral seam, GitLab-only active scope, and the separate GitHub boundary sequence. |
| 8 | [Authored HTTP contract](contracts/http/openapi.yaml) | Source for public operations and generated clients; generated output is not edited by hand. |
| 9 | [`_dream_dispatch_sql.py`](packages/ctower-kernel/src/ctower_kernel/runtime/_dream_dispatch_sql.py) | Record-owned dream effects, binding authority, immutable rows, and consumption custody. |
| 10 | [`inboxSend.ts`](apps/ctower-ui/src/mutate/inboxSend.ts) | Proven accepted-versus-pending UI idiom that the Request build must reuse. |

## Current priorities

1. **Build [#400](https://github.com/simjak/ctower/issues/400) to the accepted Request contract.** The
   repository contains Phase 0 governance, not Request product behavior. At the cutoff the build lane was
   active and about seven hours deep, but no completion candidate or product PR existed. The build must
   provide server-owned permanent references, independent durable acknowledgement, honest accepted/pending
   rendering, existing-seat CLI and UI channels, a read-only epistemically honest list, and a fail-closed
   dry-run plus fidelity proof for the one-way import. Cutover remains dormant until CP3-D and a separately
   accepted portfolio authority epoch permit it.
2. **Keep the Request sequence explicit.** [#401](https://github.com/simjak/ctower/issues/401) adds the
   append-only Agreement/Ruling fact after #400; [#402](https://github.com/simjak/ctower/issues/402) and
   [#403](https://github.com/simjak/ctower/issues/403) then build the morning read model and brief-shaped
   asks. None authorizes the Slack/Hermes capture adapter.
3. **Preserve the recurrence boundary that is now proven.** Mission Control commit
   `bb45f23d2f47a62c5cbb2529188496a6d894ab4e` landed collision-safe output custody, and the pending effects
   replayed through a digest whose content matched the durable record. Full unattended custody is still not
   claimed: the documented operator binding ceremony remains outstanding, and unbound effects must keep
   refusing without execution or loss.
4. **Do not activate gated boundaries by implication.** Connector Phase 1 is merged, but the GitHub
   connector remains behind operator acknowledgement, append-only D39/D43 supersession, canonical
   incorporation, and a stable build ticket carrying GH-C01 through GH-C08. Crew-console typed input remains
   behind the rendered full-frame mockup acknowledgement and its own security/build gates.
5. **Close the two current engineering-memory gaps.** [#357](https://github.com/simjak/ctower/issues/357)
   and [#358](https://github.com/simjak/ctower/issues/358) still lack the durable executable-remedy gate.
   Separately, the dream tooling must derive notification sender identity from the actual emitter and prove
   that another accountable seat cannot be named by caller text.

Sources: Mission Control `board/ctower-migration-status.md:2529-2533`,
`coordination/2026-08-10_0457--writer-r2881-dream--dream-fleet-019fe965f100.status.md`, Mission Control
commit `bb45f23d`, the linked GitHub issues, and the current gap register in [LESSONS.md](LESSONS.md).

## Live lanes at the cutoff

- `engineer-r400-requests` remained the only live ctower product lane. The latest bounded board read said
  it was working with no PR; current GitHub read-back still found #400 open.
- PR [#409](https://github.com/simjak/ctower/pull/409) merged the locked `packaging` dependency update at
  `2026-08-10T04:15:57Z`. It advanced main but added no Request behavior and closed no product ticket.
- The recurring-output repair is landed prevention rather than an active product lane. The replayed dream
  artifact is complete, while consumption and binding custody stay with the parent consumer and operator.
- #401–#403 are open queued tickets. GitHub connector Phase 2 and console typed input remain operator-gated,
  not live build lanes.

Sources: Mission Control `board/ctower-migration-status.md:2529-2533`, the fleet dream status cited above,
and fresh GitHub read-back for #400–#403 and #409.

## Durable state

- Repository head at refresh is `a17116225d7a8a75455074f94dde5aca165eb5bf`, the merge of
  [PR #409](https://github.com/simjak/ctower/pull/409). The latest published release is `v0.21.0`.
  The Request governance merge and later dependency merge are `MERGED`, not a Request release.
- The GitLab standing integration, notification mirror, promotion control, three-project portfolio,
  per-seat bridge identity, and honest Inbox send control closed their day tickets (#346, #355, #370,
  #354, #389, and #372) with review cures and exact-head evidence. Phase 1 of
  [#381](https://github.com/simjak/ctower/issues/381) is merged; later phases remain open.
- [PR #394](https://github.com/simjak/ctower/pull/394) provides the operator-only dream-lane binding
  surface and a tested versioned forward correction. The unbound-lane probe refused without execution or
  loss, but the live ceremony is still outstanding; neither the merge nor the refusal performs it.
- [PR #398](https://github.com/simjak/ctower/pull/398) and
  [PR #406](https://github.com/simjak/ctower/pull/406) establish Request specification and governance
  only. SPEC still labels the runtime `SHADOW_ONLY_CP3_D_NOT_PROVEN`; ctower is sole authority for nothing.
- The consumer collision repair is on Mission Control main and its pending work replayed. This closes the
  prevention gap, not the separate binding, effect-consumption, or record-authority gates.
- Project files remain authoritative memory. Search/index output is derived assistance and never overrides
  the cited repository, board, ticket, or coordination evidence.

## Open operator items

- **Crew-console taste:** the rendered full-frame mockup awaits the operator's acknowledgement before typed
  terminal input can advance. [#371](https://github.com/simjak/ctower/issues/371) is open; its old draft
  [PR #373](https://github.com/simjak/ctower/pull/373) is over 48 hours old, draft, dirty, and conflicting.
- **Dream binding:** the surface and recovery proof are merged in #394, but the documented binding command
  is an operator-only one-way ceremony. The crew may explain and verify the refusal/recovery surface; it may
  not perform the ceremony by implication.
- **GitHub connector boundary:** [PR #396](https://github.com/simjak/ctower/pull/396) records a
  cleared-with-controls CSO shape. The operator still owns the yes/no; no Decision, build, credential, or
  egress activation follows until that acknowledgement is recorded.
- **Aging drafts:** [PR #208](https://github.com/simjak/ctower/pull/208) and
  [PR #329](https://github.com/simjak/ctower/pull/329) remain open drafts, dirty, conflicting, and older
  than 48 hours. With #373, their owners must close obsolete work or rejustify and refresh it before
  presenting an intended outcome to the operator.

## Cold-start next act

Read #400 and `docs/specs/operator-requests.md`, compare the assigned candidate with head `a17116225d7a`,
and state whether you are building, reviewing, testing, documenting, or releasing. Preserve the shadow-only
and cutover gates, reuse the proven pending/unknown distinctions, run the seat's independent gate, and report
the exact residual rather than advancing to a later Request or gated-boundary lane.
