# Ctower Request maintenance proposals — 2026-08-10

**PROPOSALS ONLY.** This snapshot does not mutate, close, merge, retire, rank, or otherwise change an
operator Request. The Mission Control ledger remains authoritative at this cutoff, and only its ordinary
recorded command may apply an operator-confirmed disposition.

## Snapshot and scope

- Source: Mission Control `state/requests.jsonl` at commit
  `9b1a7185197dfdaab57068e7a8dce8ff1553936e`, the last commit before the scheduled
  `2026-08-10T02:00:00Z` cutoff: 5,396 lines, SHA-256
  `9c207324c3c8170369a632da8d2795a427080b10953ae6d21a72a4f08c2ed73a`.
- Scope: 14 active Ctower rows — explicit `project=ctower` rows, active Ctower feature rows owned by
  `ctower-commander`, and R2858 because R2859 explicitly relays that all-project directive into Ctower.
  Mislabelled `project=manibo` values remain visible rather than being silently corrected.
- Status fold: 1 `BLOCKED`, 8 `NEW`, and 5 `WIP`. Eight source rows are older than 48 hours by the
  ledger's recorded timestamps; those timestamps carry no timezone, so this artifact does not invent one.
- Source identities: R2816, R2824, R2825, R2846, R2847, R2857, R2858, R2859, R2881, R2882, R2883,
  R2886, R2896, and R2903.

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
| R2847 | Close after confirming the R2846/R2847 duplicate proposal. | Ctower issues [#346](https://github.com/simjak/ctower/issues/346) and [#347](https://github.com/simjak/ctower/issues/347) are recorded closed in Mission Control `coordination/2026-08-10_0333--writer-r2881-dream--dream-ctower-019fe43f9500.status.md`; repository commits `3964aecfedd5` (PR #377) and `02ce22835a51` (PR #362) predate this snapshot. | Both named custody increments landed; later connector and portfolio work has separate Requests. |

Count: **1 proposed closure**. R2857 remains open because its compound quickstart/onboarding outcome lacks
one exact-revision proof in this record. R2881 remains open because output creation, Ctower consumption,
read-back, and terminal reap are separate custody facts. R2886 remains open because its GitHub boundary was
not an active product connector at the cutoff.

## Supersession proposals

**None with sufficient evidence.** R2816 and R2824 overlap, but the former is a structural-document/taste
handoff and the latter is a broader implementation order; no exact later text retires either one. R2896 is
handled as a duplicate execution relay under R2883, not silently treated as a replacement.

## Top 20

The durable board at the cutoff names Request v1 as the live product lane. Ranking therefore starts with
that week goal, then the recurrence whose output owns this artifact, then portfolio outcomes, age, and
operator-gated versus fleet-owned work. Only nine rows remain, so the bounded top 20 contains nine rows and
the retained tail is empty. This is a kill-or-keep proposal, not priority authority.

| Rank | Request | Recommendation | Why it ranks here / next confirmable act |
|---:|---|---|---|
| 1 | R2903 | **KEEP** | Current Request-memory goal. Drive #400 through server-owned identity, honest acknowledgement, and read-back; keep cutover gated. |
| 2 | R2881 | **KEEP / custody** | The dream output exists, but consumption, read-back, binding authority, and terminal reap remain separate evidence. |
| 3 | R2859 | **KEEP / re-scope** | Three-project custody and communication remain the active control-plane program; name the still-unserved rails precisely. |
| 4 | R2857 | **RECONCILE** | Quickstart and onboarding evidence are split; prove both clauses at exact revisions or split the surviving outcome. |
| 5 | R2886 | **KEEP / operator gate** | The GitHub connector boundary has controls, but no operator acknowledgement or product activation at this cutoff. |
| 6 | R2883 | **KEEP / security and taste gates** | Dogfood send/promotion controls do not fulfill grouped real-time terminal/chat mutation. Preserve the separate boundary. |
| 7 | R2824 | **RE-SCOPE** | Canonical structure and several slices landed, but the broad implementation order needs one bounded surviving outcome. |
| 8 | R2816 | **DECIDE** | Oldest Ctower row; refresh or replace the structural candidate for operator taste, or close it with exact accepted evidence. |
| 9 | R2825 | **DECIDE / retire if obsolete** | The hourly-report process order is aging; retain it only with an explicit current need, otherwise record retirement. |

Retained unranked tail: **0 rows**.

## Accounting and verification

- Active Ctower-scoped source rows: **14**; source rows older than 48 hours: **8**.
- Duplicate proposals: **3 groups / 4 redundant rows**.
- Done-but-open proposals: **1 row**; supersession proposals: **0 rows**.
- Remaining if every proposal is confirmed: **9 = 9 ranked + 0 tail**.
- Count equation: **14 - 4 deduped-away - 1 closed = 9**.
- Proposal sets do not overlap; every proposed identity was active at the snapshot.
- Request mutation commands invoked: **0**. Request rows mutated: **0**.
