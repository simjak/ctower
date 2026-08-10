# Ctower orientation

Refreshed for the durable-record cutoff `2026-08-10T03:33:57Z` by nightly dream
`019fe43f-9500-7d4a-a387-5b35db8dceff`. Read this first, then follow the authority order in
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
   current repository contains Phase 0 governance, not Request product behavior. The build must provide
   server-owned permanent references, independent durable acknowledgement, honest accepted/pending
   rendering, existing-seat CLI and UI channels, a read-only epistemically honest list, and a fail-closed
   dry-run plus fidelity proof for the one-way import. The actual cutover remains dormant until CP3-D and
   the separately accepted portfolio authority epoch permit it.
2. **Keep the Request sequence explicit.** [#401](https://github.com/simjak/ctower/issues/401) adds the
   append-only Agreement/Ruling fact after #400; [#402](https://github.com/simjak/ctower/issues/402) and
   [#403](https://github.com/simjak/ctower/issues/403) then build the morning read model and brief-shaped
   asks. None of those later tickets authorizes the Slack/Hermes capture adapter.
3. **Finish the recurring-output prevention outside this worktree.** The nightly emitter ran without
   assistance, but the consumer stopped loudly on a stale output branch. At the cutoff the dedicated repair
   had only a lifecycle spawn record: collision-safe naming, landed-content cleanup proof, and successful
   replay remained unencoded. This writer leaves consumption to the parent consumer.
4. **Do not activate gated boundaries by implication.** Connector Phase 1 is merged, but the GitHub
   connector remains behind the operator's boundary acknowledgement, append-only D39/D43 supersession,
   canonical incorporation, and a stable build ticket carrying GH-C01 through GH-C08. Crew-console typed
   input remains behind the rendered full-frame mockup acknowledgement and its own security/build gates.
5. **Close the overdue remedy gap.** [#357](https://github.com/simjak/ctower/issues/357) and
   [#358](https://github.com/simjak/ctower/issues/358) are still open. Deliver the executable, invocation,
   regression, and blast-radius proof or re-scope the tickets explicitly; prose is not closure.

Sources: Mission Control `board/ctower-migration-status.md:2333,2379-2433,2447-2527`;
`state/crew-log.jsonl:6707-6833`; the linked GitHub issues; and the landed coordination statuses cited in
[LESSONS.md](LESSONS.md).

## Live lanes at the cutoff

- `engineer-r400-requests` was the active product lane for #400 after #406 merged. No #400 completion
  status or product commit existed in the cutoff record.
- `engineer-dream-collision` was the Mission Control repair lane for the stale-output collision. It had a
  spawn event and no landed status at the cutoff, so this file does not claim the replay fix complete.
- #401–#403 were open queued tickets, not active product behavior. GitHub connector Phase 2 and console
  typed input were operator-gated, not live build lanes.

Sources: Mission Control `board/ctower-migration-status.md:2525-2527` and
`state/crew-log.jsonl:6826,6833`; fresh GitHub read-back for #400–#403.

## Durable state

- Repository head at refresh is `07f7c526b4fdf0a27d9a87fab545fe9789386b9b`, the merge of
  [PR #406](https://github.com/simjak/ctower/pull/406). The latest published release is `v0.21.0`.
  Merged documentation/governance after that release is still `MERGED`, not a new release.
- The GitLab standing integration, notification mirror, promotion control, three-project portfolio,
  per-seat bridge identity, and honest Inbox send control closed their day tickets (#346, #355, #370,
  #354, #389, and #372) with review cures and exact-head evidence. Phase 1 of
  [#381](https://github.com/simjak/ctower/issues/381) is merged; later phases remain open.
- [PR #394](https://github.com/simjak/ctower/pull/394) provides the operator-only dream-lane binding
  surface and a tested versioned forward correction. The live binding ceremony was still outstanding at
  the cutoff even though GitHub auto-closed #392; do not infer the ceremony from the merge.
- [PR #398](https://github.com/simjak/ctower/pull/398) and
  [PR #406](https://github.com/simjak/ctower/pull/406) establish Request specification and governance
  only. SPEC still labels the runtime `SHADOW_ONLY_CP3_D_NOT_PROVEN`; ctower is sole authority for nothing.
- Project files remain the authoritative memory. Search/index output is a derived aid and never overrides
  the cited repository, board, ticket, or coordination evidence.

## Open operator items

- **Crew-console taste:** the rendered full-frame mockup awaits the operator's acknowledgement before typed
  terminal input can advance. [#371](https://github.com/simjak/ctower/issues/371) is open; its old draft
  [PR #373](https://github.com/simjak/ctower/pull/373) is over 48 hours old and currently conflicts with
  main, so the owning lane must refresh or replace it before any code handoff.
- **Dream binding:** the surface and recovery proof are merged in #394, but the documented binding command
  is an operator-only one-way ceremony. The crew may explain and verify the surface; it may not perform the
  ceremony by implication.
- **GitHub connector boundary:** [PR #396](https://github.com/simjak/ctower/pull/396) records a
  cleared-with-controls CSO shape. The operator still owns the yes/no; no Decision, build, credential, or
  egress activation follows until that acknowledgement is recorded.
- **Aging drafts:** [PR #208](https://github.com/simjak/ctower/pull/208) and
  [PR #329](https://github.com/simjak/ctower/pull/329) remain draft, conflicting, and older than 48 hours.
  Both overlap a substantially newer documentation and governance baseline. Their owners must close them
  as obsolete or rejustify and refresh them before asking the operator to review an intended outcome.

## Cold-start next act

Read #400 and `docs/specs/operator-requests.md`, compare the assigned candidate with head `07f7c526`, and
state whether you are building, reviewing, testing, documenting, or releasing. Preserve the shadow-only and
cutover gates, reuse the proven pending/unknown distinctions, run the seat's independent gate, and report
the exact residual rather than advancing to a later Request or gated-boundary lane.
