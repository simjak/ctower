# Ctower orientation

Refreshed `2026-08-14T13:28:28+02:00` by scheduled dream
`019fee8c-4d00-77d8-b729-e6f7821eecba`. Read this file first. The authority order is
[the specification](docs/internal/SPEC.md), append-only [decisions](docs/internal/DECISIONS.md), the
derived [architecture atlas](ARCHITECTURE.md), then the non-normative
[roadmap](docs/internal/IMPLEMENTATION-ROADMAP.md).

## The ten files that matter first

| Order | File | Why it matters |
|---:|---|---|
| 1 | [docs/internal/SPEC.md](docs/internal/SPEC.md) | Normative product, architecture, workflow, acceptance, and build contract; current version 1.24. |
| 2 | [docs/internal/DECISIONS.md](docs/internal/DECISIONS.md) | Append-only rationale through D65; supersede an accepted decision rather than rewriting it. |
| 3 | [ARCHITECTURE.md](ARCHITECTURE.md) | Sole terminal-safe atlas derived from the specification; repair it if the two diverge. |
| 4 | [docs/internal/IMPLEMENTATION-ROADMAP.md](docs/internal/IMPLEMENTATION-ROADMAP.md) | Sequencing proposal only; it activates no backlog item. |
| 5 | [README.md](README.md) | Honest pre-alpha front door and the shortest statement of what works today. |
| 6 | [docs/start-here/availability.md](docs/start-here/availability.md) | Public shipped/development-only/planned/unsupported boundary. |
| 7 | [contracts/http/openapi.yaml](contracts/http/openapi.yaml) | Authored HTTP authority from which generated clients and references derive. |
| 8 | [requests.py](packages/ctower-kernel/src/ctower_kernel/work/requests.py) | Small public Work interface for the shipped Request authority. |
| 9 | [runtime/interface.py](packages/ctower-kernel/src/ctower_kernel/runtime/interface.py) | Small public Runtime interface for Routines, occurrences, effects, and custody. |
| 10 | [test_routine_occurrence_e2e.py](tests/acceptance/increment-1/test_routine_occurrence_e2e.py) | Newest running-instance proof: one Routine occurrence through the supervised development stack. |

## Current truth

- Ctower remains pre-alpha. There is no published package, hosted service, or production deployment. The
  private loopback development shadow is reconstructible and unsupported; it is not a durability claim.
- The development slice includes Request/Ruling/digest reads, proof-gated Tickets and Workflow, fixed
  Routines, bounded GitLab and GitHub issue integrations, generated clients, and the private read-only Console
  server foundation. The Console has no product panel or typing authority.
- CP3-D is still red. Mission Control and the applicable GitHub/GitLab records remain writable co-sources;
  Ctower is sole authority for nothing, and bulk legacy import remains dormant.
- Current repository head is `047309f2a816345870a471ce2393ab0e5eeef2b5`, merged by
  [PR #480](https://github.com/simjak/ctower/pull/480). The latest published release is
  [v0.29.0](https://github.com/simjak/ctower/releases/tag/v0.29.0) at
  `5eb92710dc673186450e0e3b3e4cb0a6bd265483`; main is ahead of that release.
- The former documentation drafts [#208](https://github.com/simjak/ctower/pull/208),
  [#329](https://github.com/simjak/ctower/pull/329), and
  [#373](https://github.com/simjak/ctower/pull/373) are now merged. D65 makes the three
  `docs/internal/` paths above canonical without compatibility aliases.

## Priorities and live candidate lanes

1. **Reconcile the Request-maintenance candidate with current main.**
   [PR #494](https://github.com/simjak/ctower/pull/494) proposes CT-I1-024 at head
   `ee9689b1cfbbf52b974d7ba2684e45cc6aa8963b`. Its old head passed the named gates, but current GitHub
   reports it conflicting: three commits ahead, seven behind, no review decision. Resolve against current
   canon, regenerate machine-owned output, rerun both gates on the new exact head, then obtain independent
   QA/Review. No proposal may mutate a Request except through a separately authorized ordinary command.
2. **Continue the running-instance coverage program honestly.**
   [#443](https://github.com/simjak/ctower/issues/443) is the first of the 17 audited gaps to close and is
   carried by current head. Issues #440–#442 and #444–#456 remain open. Work one exact layer at a time; an
   in-process client, fixture echo, page load, or process exit is not running-instance E2E.
3. **Keep Console typing inactive.** The read-only Phase-1 server foundation is part of the development
   slice. [#463](https://github.com/simjak/ctower/issues/463) still requires the repaired Q3 controls and a
   fresh maximum-effort exact-candidate CSO clearance. [PR #436](https://github.com/simjak/ctower/pull/436)
   is 28 main commits behind and may not merge on its stale green checks.
4. **Treat new canonical designs as plans, not shipped behavior.** CT-I1-025 through CT-I1-031 describe
   project management, knowledge mining, ticket movement/worklists, catalogs, and workspaces. Their spec
   merges do not create routes, records, workers, schedules, or product support; implementation still needs
   ordinary activation, dependencies, evidence, and same-candidate documentation.
5. **Keep the two overdue memory gaps visible.** Operational sender attribution in Mission Control tooling
   still lacks a substrate-owned identity regression, and [#357](https://github.com/simjak/ctower/issues/357)
   plus [#358](https://github.com/simjak/ctower/issues/358) still lack the executable-remedy gate. Owners and
   historical deadlines are in [LESSONS.md](LESSONS.md).

GitHub proves repository and ticket state, not staffing. The latest Ctower crew lifecycle rows are stale, so
this orientation does not invent an active crew from them; the open candidates above must be claimed through
the ordinary Commander route.

## Open operator items

- No production, destructive, or shared-boundary action is implied by this refresh.
- Console typing returns to the operator only after #463 has a fresh exact-candidate CSO clearance and the
  rendered variant is current; stale #436 evidence is not a taste gate.
- CT-I1-024's eventual operator confirmation surface is a separate product gate. The current need is
  engineering reconciliation and independent evidence, not an operator disposition on this dream's
  proposal list.

## Cold-start next act

Name your seat and assigned ticket, verify the actual model, then read the ten files above and the nearest
boundary README. If assigned #494, start from the current main/candidate conflict and preserve proposal versus
Request authority. If assigned an E2E gap, drive a supported running instance and record the exact revision.
If assigned Console typing, stop at #463's missing fresh clearance. Run `just check` while developing and
`just verify` only on the clean candidate you intend to hand to independent review.
