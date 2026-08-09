# Ctower orientation

Refreshed `2026-08-08T07:09:19+02:00` by nightly dream
`019fdf19-3900-7a98-8a3f-cd0c7378a6e9`. Read this first, then follow the authority order in
[README.md](README.md): [SPEC.md](SPEC.md) is normative; decisions are append-only history; the
architecture atlas and roadmap are derived aids.

## The ten files that matter first

| Order | File | Why it matters |
|---:|---|---|
| 1 | [SPEC.md](SPEC.md) | Current product, architecture, workflow, acceptance, and build contract. |
| 2 | [DECISIONS.md](DECISIONS.md) | Accepted append-only decisions; supersede rather than rewrite. |
| 3 | [ARCHITECTURE.md](ARCHITECTURE.md) | Terminal-safe map of the current system; it must not outrun the spec. |
| 4 | [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md) | Sequencing proposal only; it activates no work. |
| 5 | [README.md](README.md) | Honest front door, supported paths, and current product boundary. |
| 6 | [contracts/http/openapi.yaml](contracts/http/openapi.yaml) | Authored HTTP source; generated clients derive from it. |
| 7 | [`_dream_dispatch_sql.py`](packages/ctower-kernel/src/ctower_kernel/runtime/_dream_dispatch_sql.py) | Persisted project/fleet authority for the newly shipped dream effects. |
| 8 | [`_review_dispatch_sql.py`](packages/ctower-kernel/src/ctower_kernel/workflow/_review_dispatch_sql.py) | Substrate-bound independent-review dispatch policy. |
| 9 | [`_promotion_sql.py`](packages/ctower-kernel/src/ctower_kernel/inbox/_promotion_sql.py) | Atomic native-thread promotion into Work. |
| 10 | [`test_dream_dispatch_effect.py`](tests/acceptance/increment-1/test_dream_dispatch_effect.py) | End-to-end scope, replay, refusal, and consumption proof for #368. |

## Priorities and live lanes

1. **Finish [#369](https://github.com/simjak/ctower/issues/369).** The consumer/cron lane is working.
   Its latest durable report says the installed shadow still returns `404` for the new route; tool,
   tests, cron installation, and one real served-instance cycle remain. This dream does not consume
   its own effect; custody belongs to the parent consumer.
2. **Activate [#371](https://github.com/simjak/ctower/issues/371) through the canonical process.** The
   security-reviewed Phase 1 viewer proposal in draft [PR #373](https://github.com/simjak/ctower/pull/373)
   is build-activating only for stable ticket creation after canonical incorporation. It is not an
   implementation, deployment, or shipped feature. Identity/browser auth, Runtime cursor and gap
   contracts, the registered adapter, full-frame mockup approval, containment proof, and deployed
   proof remain prerequisites.
3. **Continue the dogfood wave.** [#346](https://github.com/simjak/ctower/issues/346) external issue
   ingestion precedes the ordinary import, then [#355](https://github.com/simjak/ctower/issues/355)
   carries the dual-rail bridge, then [#354](https://github.com/simjak/ctower/issues/354) builds the
   portfolio view. Do not jump the order.
4. **Keep UI dependencies explicit.** [#370](https://github.com/simjak/ctower/issues/370) may build on
   the landed public promotion operation. [#372](https://github.com/simjak/ctower/issues/372) waits
   for #355. The later editor remains later scope.

Sources: Mission Control `board/ctower-migration-status.md:1692-1694,1984-1985,2035-2040,2073-2101`;
`coordination/2026-08-08_0627--devops-r369-consumer--dream-spawner.status.md:3-20`;
`coordination/2026-08-08_0618--cso-r371-delta2--phase1-activation.status.md:3-30`.

## Durable state

- Native Inbox core/UI, knowledge, review dispatch, delivery/read facts, public promotion, and the
  four nightly dream routines have landed with their day tickets evidence-closed: #330, #331,
  #332, #347, #353, #345, and #368. The three served visual defects #337–#339 also closed; #338's
  final proof is against merged revision `f5e9b9b`.
- The repository head read for this refresh is `135b3e1fce2d0fa1afdf06dbf687141e387800bd`, the merge of
  [PR #374](https://github.com/simjak/ctower/pull/374). The installed shadow lag reported by #369
  does not change repository truth and must not be called a served-cycle pass.
- The local gbrain probe is unavailable because its PGLite database cannot initialize. Treat search
  absence as tooling failure, use the cited durable record directly, and do not attempt re-indexing
  until the three probes pass.

Sources: the linked GitHub tickets and PRs; Mission Control
`board/ctower-migration-status.md:1766-1786,1823-1824,1894,1984-1985,2073-2101`;
`state/crew-log.jsonl:6640-6895`.

## Open operator items

- [PR #208](https://github.com/simjak/ctower/pull/208), front-door documentation, has been open
  since `2026-08-02T11:21:17Z`; it remains draft and currently reports a dirty merge state.
- [PR #329](https://github.com/simjak/ctower/pull/329), the structural constitution, has been open
  since `2026-08-05T10:40:49Z`; it remains draft and currently reports a dirty merge state.

Both are older than 48 hours and were parked for operator ceremony/taste. Their owning documentation
lanes must first refresh the heads to current main; then the operator can review the intended product
and structure choices rather than resolve Git conflicts. Source: current GitHub PR metadata and
Mission Control `board/ctower-migration-status.md:931-940,983-990,1138-1155`.
