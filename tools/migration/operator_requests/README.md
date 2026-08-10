# Operator Request cutover helper

This one-time release helper reads the complete Mission Control Request JSONL,
validates append lineage before selecting latest rows, derives the exact frozen
open denominator, validates reviewed owner and priority mappings, and emits
serial batches of at most 25 with a deterministic three-row sample. It writes
neither source nor target and exposes no import transport. Actual fencing,
signed-manifest acceptance, import, reconciliation, removal, and the first
post-cutover capture are a separate operator-visible authority epoch.

The dry run fails closed when the ledger is writable, its fence proof is absent
or unbound, an open row lacks an explicit project or owner mapping, a required
priority review is absent, history is inconsistent, a prohibited class appears,
or the manifest is unsigned. Source text is represented only by digests in the
artifact. Private Ed25519 material is resolved only through the existing
protected key-reference map mechanism.

```text
python -m tools.migration.operator_requests.main \
  --ledger /srv/projects/mission-control/state/requests.jsonl \
  --shadow-openapi http://127.0.0.1:8091/openapi.json
```

An exit status of `3` is a successful dry-run analysis with one or more cutover
blockers. Status `0` means the frozen inputs are eligible; status `2` means the
source could not be analyzed safely.
