# Tracked review records

source_count: 31
record_count: 34
allowed_commit_path: docs/internal/review-records/
record_only_commit_check: `git diff --name-only <sha>^ <sha>`

This directory is the durable, internal review-record surface. It is under `docs/internal/`,
which is excluded from the published MkDocs tree, but it remains in Git's intended-tree secret
scan. Records are deliberately normalized rather than copied from coordination status files:
transcripts, URLs, credentials, bearer material, connection strings, personal contacts, and
private project identities are not part of the tracked corpus.

## Shape

Each `record-*.md` contains one final `verdict`, one exact `head` identity, and one `SIGNED-OFF`
block. A superseded round is not left beside the live decision. The file name carries the judged
PR or subject, the head prefix, and the seat. A source review that covered several subjects is
split into separate records; that is why 31 source records produce 34 normalized records rather
than weakening the one-file/one-verdict/one-head invariant.

The feed-notify source review was performed against an uncommitted artifact and did not provide a
versioned commit. Its record says `UNCOMMITTED-ARTIFACT` explicitly; no SHA is invented.

## Standing rule

Review lanes remain read-only. The Commander lands a normalized review record as the last commit
before merge. A record-only commit that touches only `docs/internal/review-records/` changes no product code,
so it does not invalidate an earlier gate verdict. For every such commit, prove the scope with:

```text
git diff --name-only <sha>^ <sha>
```

The output must contain only `docs/internal/review-records/` paths. This is a mechanical check,
not a claim inferred from the commit message.

## Scope disposition

The 31 selected CSO/security source records are represented here. The remaining coordination
corpus is intentionally not rescued in this candidate: it contains ordinary engineering,
operations, product, and duplicate support status material outside the P1 security-verdict scope.
The three marker-bearing support files that were not verdicts are also excluded. No raw status
file is an authority after normalization; the source remains available only in the ephemeral
coordination estate and the concise evidence recorded here.

## Security-review boundary

This corpus is an AI-assisted review record, not a professional security audit or a production
release authorization. Each record applies only to its named head and stated controls. A changed
head requires a fresh review; a review pass never substitutes for the operator's product or
release gate.
