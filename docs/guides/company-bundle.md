# Exercise CompanyBundle

CompanyBundle is the strict, portable desired-state envelope for the development Catalog checkpoint. It can
validate, plan, atomically apply, and deterministically export one tenant's future-only component pins. It
does not activate runners, effects, external targets, or production recovery.

The checked-in synthetic example is
[`company/company.bundle.yaml`](https://github.com/simjak/ctower/blob/main/company/company.bundle.yaml).
It contains complete versioned component envelopes and inline non-secret payloads. Secret bindings contain
names and reference classes only—never credentials or resolved values.

## Validate and plan without writes

Local YAML intake is limited to one 1 MiB UTF-8 regular file. YAML 1.2 duplicate keys, aliases, anchors,
merge keys, custom tags, non-JSON scalars, non-finite numbers, excessive nodes/depth, symlinks, and hidden
filesystem/network resolution are rejected before transport. The API independently validates the generated
JSON and Catalog semantics.

```bash
read -r -s -p "Synthetic authority: " authority
printf '\n'
printf '%s\n' "${authority}" |
  ctl --base-url https://ctower.example \
  company bundle validate company/company.bundle.yaml
printf '%s\n' "${authority}" |
  ctl --base-url https://ctower.example \
  company bundle plan company/company.bundle.yaml
```

Validate and plan are read-only. The plan binds the active base version/digest, proposed semantic digest,
ordered actions/checks, and exact `plan_digest`.

## Apply the exact plan

Apply requires the plan's exact digest/base plus a caller-stable command ID:

```bash
printf '%s\n' "${authority}" |
  ctl --base-url https://ctower.example \
  company bundle apply company/company.bundle.yaml \
  --command-id 018f5f67-89ab-7def-8123-456789abcdef \
  --expected-active-version 0 \
  --plan-digest sha256:0000000000000000000000000000000000000000000000000000000000000000
```

The values above are illustrative. Use the real plan result; a stale or mismatched base/digest is refused
without moving the active pointer. The CLI durably spools apply before sending it. Exit `75` means queued or
`durability_pending`, not accepted.

The server re-plans under the locked base, stages digest-verified payloads through the shared object port,
and atomically commits immutable component/bundle/event/outbox facts plus the one future-only pointer. Exact
replay returns the original result; same key with different semantics conflicts.

## Export and round-trip

```bash
printf '%s\n' "${authority}" |
  ctl --base-url https://ctower.example company bundle export > exported.bundle.yaml
unset authority
```

Export is read-only desired state with deterministic ordering, UTF-8 LF, and exactly one trailing newline.
Server-owned actor/time/revision/check facts are not injected. Validating and planning that export against
the same active pointer must produce zero actions.

This is a development configuration surface, not a Git watcher, reconciler, secret transporter, live-run
mutation, or supported production configuration rollout.
