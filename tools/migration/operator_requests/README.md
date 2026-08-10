# Operator Request cutover helper

This one-time release helper reads the complete Mission Control Request JSONL,
validates append lineage before selecting latest rows, derives the exact frozen
open denominator, validates reviewed owner and priority mappings, and emits
serial batches of at most 25 with a deterministic three-row sample. The
preflight writes neither source nor target. A separate explicit executor uses
the hidden, human-operator-authenticated epoch transport to prepare the signed
manifest, import in strict order, wait for off-host acceptance, reconcile every
row and count, compare deterministic samples through the public Request read,
persist signed batch proofs, and complete only after the final removal fence.

The portfolio deployment order is fixed. Apply migration `0059` to the existing
database as the first deployment phase; that transaction inserts a native-capture
fence for every existing tenant. Only after it commits may the candidate binary
replace the old service. The binary checks that marker at both Request write seams,
so capture is already fenced when the new endpoint becomes reachable; there is no
deploy-to-prepare capture window. Fresh tenants have no legacy ledger and therefore
do not receive this migration-time cutover marker.

The dry run fails closed when the ledger is writable, its fence proof is absent
or unbound, an open row lacks an explicit project or owner mapping, a required
priority review is absent, history is inconsistent, a prohibited class appears,
or the manifest is unsigned. Source text is represented only by digests in the
artifact. Private Ed25519 material is resolved only through the existing
protected key-reference map mechanism.

```text
python -m tools.migration.operator_requests.main \
  --ledger /srv/projects/mission-control/state/requests.jsonl \
  --owner-map /operator-evidence/request-owner-map.json \
  --fence-proof /operator-evidence/request-freeze.json \
  --signing-key-map /operator-secrets/signing-map.json \
  --signing-key-ref signing-key-ref:request-cutover \
  --signing-key-version 1 \
  --manifest-output /operator-evidence/request-manifest.json \
  --shadow-openapi http://127.0.0.1:8091/openapi.json
```

An exit status of `3` is a successful dry-run analysis with one or more cutover
blockers. Status `0` means the frozen inputs are eligible; status `2` means the
source could not be analyzed safely.

The source fence is observed, not self-asserted. The fence command requires the
ledger to reside on a read-only filesystem mount. Before finalization every
named legacy caller must be a read-only regular file containing the exact
`REQUEST_WRITES_REFUSED` marker; at finalization every named caller must be
absent. It hashes the observed caller bytes and source identity into the signed
artifact.

```text
python -m tools.migration.operator_requests.fence_main \
  --ledger /srv/projects/mission-control/state/requests.jsonl \
  --caller-root /srv/projects/mission-control \
  --caller tools/req --phase freeze \
  --signing-key-map /operator-secrets/signing-map.json \
  --signing-key-ref signing-key-ref:request-cutover \
  --signing-key-version 1 \
  --output /operator-evidence/request-freeze.json
```

Execution is deliberately two-stage. `import` ends only after all batch proofs
are accepted. The operator then removes the already-refusing legacy callers,
observes a `final` fence, and invokes `complete`. The authorization reference is
a mode-0600 JSON file containing one `authorization` header; no credential is
placed in argv, an environment variable, a manifest, evidence, or output.

```text
python -m tools.migration.operator_requests.execute_main import \
  --base-url https://ctower.internal \
  --auth-reference /operator-secrets/request-cutover-auth.json \
  --ledger /srv/projects/mission-control/state/requests.jsonl \
  --manifest /operator-evidence/request-manifest.json \
  --fence /operator-evidence/request-freeze.json \
  --evidence-dir /operator-evidence/request-batches \
  --reviewer-public-key /operator-evidence/request-reviewer.pub \
  --signing-key-map /operator-secrets/signing-map.json \
  --signing-key-ref signing-key-ref:request-cutover \
  --signing-key-version 1

python -m tools.migration.operator_requests.execute_main complete \
  --base-url https://ctower.internal \
  --auth-reference /operator-secrets/request-cutover-auth.json \
  --manifest /operator-evidence/request-manifest.json \
  --final-fence /operator-evidence/request-final.json \
  --reviewer-public-key /operator-evidence/request-reviewer.pub \
  --signing-key-map /operator-secrets/signing-map.json \
  --signing-key-ref signing-key-ref:request-cutover \
  --signing-key-version 1
```
