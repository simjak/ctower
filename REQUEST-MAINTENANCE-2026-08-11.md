# Ctower Request maintenance proposals — 2026-08-11

**PROPOSALS ONLY.** This snapshot does not mutate, close, merge, retire, rank, or otherwise change an
operator Request. The Mission Control ledger remains authoritative at this cutoff, and only its ordinary
recorded command may apply an operator-confirmed disposition.

## Snapshot and scope

- Source: Mission Control `state/requests.jsonl` at commit
  `eef777742f60354c9071ef00b388004822a4fa92`, the last commit before the scheduled
  `2026-08-11T02:00:00Z` cutoff: 5,402 lines, SHA-256
  `6a014ca33334c19b6ab21616015f53815e626d146553d47064a2da2d15f6e567`.
- Scope: 13 active Ctower rows — explicit `project=ctower` rows, active Ctower feature rows owned by
  `ctower-commander`, and R2858 because R2859 explicitly relays that all-project directive into Ctower.
  Mislabelled `project=manibo` values remain visible rather than being silently corrected.
- Status fold: 1 `BLOCKED`, 7 `NEW`, and 5 `WIP`. Twelve source rows are older than 48 hours by
  the ledger's recorded timestamps; those timestamps carry no timezone, so this artifact does not invent one.
- Source identities: R2816, R2824, R2825, R2846, R2847, R2857, R2858, R2859, R2881, R2882, R2883,
  R2886, and R2896.
- R2903 is not an active source row in this snapshot: its final ledger row is `DONE`/`active=false` at
  `2026-08-10 22:05`. It is excluded rather than proposed for closure a second time.

## Duplicate proposals

The proposed survivor retains every folded identity, original timestamp, note, relationship, and source
reference as append-only metadata. Similarity alone changes nothing.

| Proposed survivor | Folded rows | Why these appear to be the same ask | Operator action |
|---|---|---|---|
| R2847 (`2026-08-07 12:57`) | R2846 (`2026-08-07 12:57`) | Both request GitLab feedback ingestion into Ctower and automatic REVIEW dispatch; R2847 is the project-scoped relay. | Confirm R2847 as survivor carrying both records, or keep them separate. |
| R2859 (`2026-08-07 15:23`) | R2858 (`2026-08-07 15:22`) | Both order all three projects and their communication onto Ctower; R2859 identifies itself as the Ctower-owned relay. | Confirm R2859 as survivor carrying both records, or keep them separate. |
| R2883 (`2026-08-08 02:42`) | R2882 (`2026-08-08 02:41`); R2896 (`2026-08-09 06:45`) | All three request mutating Ctower UI plus real-time crew terminal/chat control; R2883 carries the security boundary and R2896 is the execution relay. | Confirm R2883 as survivor carrying all three records, or keep them separate. |

Count: **3 duplicate groups / 4 proposed redundant rows**. No source record changed.

## Done-but-open proposals

| Request | Proposed disposition | Concrete landed evidence | Residual checked |
|---|---|---|---|
| R2847 | Close after confirming the R2846/R2847 duplicate proposal. | Ctower issues [#346](https://github.com/simjak/ctower/issues/346) and [#347](https://github.com/simjak/ctower/issues/347) were closed before this snapshot; repository commits `3964aecfedd5` (PR #377) and `02ce22835a51` (PR #362) contain the named increments. | Both named custody increments landed; later connector, portfolio, and running-instance coverage work have separate Requests or tickets. |

Count: **1 proposed closure**. R2857 remains open because its compound quickstart/onboarding outcome lacks
one exact-revision proof in this record. R2881 remains open because output creation, effect consumption,
read-back, binding authority, and terminal reap are separate custody facts. R2886 remains open because
the GitHub candidate was security-cleared but still unmerged at the cutoff.

## Supersession review — both sides quoted

**No supersession proposal has sufficient evidence.** The closest candidate is kept explicit:

| Earlier row | Later row | Exact source excerpts | Disposition |
|---|---|---|---|
| R2816 | R2824 | R2816: “the ctower STRUCTURAL/constitution document — what it is, what problem it solves, how, the reasoning (clean+structural) + incremental roadmap phased by priority & system structure.” R2824: “agree structural discussion verdicts → update README with all concepts, update implementation plan+roadmap, break into task tickets, START implementation (inbox-as-product first).” | R2824 broadens into implementation but never says that R2816's operator-taste handoff is retired. Keep both open unless the operator records replacement or closure. |

R2896 is treated as a duplicate execution relay under R2883, not silently as a superseding Request.

## Top 20

The Request-memory week goal completed in the ledger before this cutoff, so no active source row receives
an invented goal boost. Ranking keeps the prior stable order, then applies recurrence custody, portfolio
reach, age, and operator-gated versus fleet-owned next acts. Only eight rows remain, so the bounded top 20
contains eight rows and the retained tail is empty. This is a kill-or-keep proposal, not priority authority.

| Rank | Request | Recommendation | Why it ranks here / next confirmable act |
|---:|---|---|---|
| 1 | R2881 | **KEEP / custody** | This recurring artifact exists, but effect consumption, read-back, binding authority, and terminal reap remain separately provable facts. |
| 2 | R2859 | **KEEP / re-scope** | Three-project custody and communication remain the fleet-wide program; name the still-unserved rails precisely before more work. |
| 3 | R2857 | **RECONCILE** | Quickstart and onboarding evidence are split; prove both clauses at exact revisions or split the surviving outcome. |
| 4 | R2886 | **KEEP / landing gate** | The GitHub connector candidate had exact-head security clearance at the cutoff but was not merged; retain until normal review and landing evidence exist. |
| 5 | R2883 | **KEEP / security and taste gates** | Read-only Console work does not fulfill grouped real-time terminal/chat mutation; typing remains a separate guarded boundary. |
| 6 | R2824 | **RE-SCOPE** | Canonical structure and many slices landed, but the broad implementation order still needs one bounded surviving outcome. |
| 7 | R2816 | **DECIDE** | Oldest Ctower row; refresh the structural candidate for operator taste or close it with exact accepted evidence. |
| 8 | R2825 | **DECIDE / retire if obsolete** | The hourly-report process order is aging; retain it only with an explicit current need, otherwise record retirement. |

Retained unranked tail: **0 rows**.

## Ambiguities held open

- No Request is silently closed from a branch, candidate, security clearance, process exit, or projection.
- R2816/R2824 has no explicit replacement words, so overlap does not become supersession.
- R2857's two-clause outcome, R2881's custody chain, and R2886's unmerged candidate each lack one terminal
  fact at the snapshot.
- R2825 may be obsolete, but only an ordinary recorded operator disposition can retire it.

## Accounting and verification

- Active Ctower-scoped source rows: **13**; source rows older than 48 hours: **12**.
- Duplicate proposals: **3 groups / 4 redundant rows**.
- Done-but-open proposals: **1 row**; supersession proposals: **0 rows**.
- Remaining if every proposal is confirmed: **8 = 8 ranked + 0 tail**.
- Count equation: **13 - 4 deduped-away - 1 closed = 8**.
- Proposal sets do not overlap; every proposed identity was active at the snapshot.
- Request mutation commands invoked: **0**. Request rows mutated: **0**.
