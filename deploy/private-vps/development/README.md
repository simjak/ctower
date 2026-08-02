# Persistent shadow-only development runtime

This is the supported E2 walking slice for local dogfood on one private VPS. It is always
`SHADOW_ONLY_CP3_D_NOT_PROVEN`: it is not a production deployment, does not authorize the
`development_single_writer` epoch, and must contain only low-value reconstructible work.

The fixed topology is a PostgreSQL 17 primary and named physical ACK standby in persistent Docker
volumes, a loopback-only API, and a same-wheel control worker. The worker includes the ordinary bounded
durability finalizer. Docker publishes PostgreSQL only on `127.0.0.1`; the API binds only to
`127.0.0.1:8091`. No firewall, DNS, TLS endpoint, or external listener is created.

Configuration under `~/.config/ctower/` contains labels, ports, image digests, and Secret Service
references only. PostgreSQL passwords and operator/commander bearer values live in the allowlisted OS
keyring. The systemd units contain no secret values. The verified runtime is installed once at
`~/.local/share/ctower-development/runtime/`; its virtual environment is created at that permanent path,
and installation executes an installed console entry point before succeeding.

This unattended linger host uses the passwordless GNOME login collection of a dedicated development
account, owner-only on disk, and an exact user unit that unlocks that login collection before ctower
starts. This is a development-keyring tradeoff for this shadow instance, not a production secret-at-rest
claim. Values never appear in ctower config, unit, environment, argument, or plaintext credential files.
PostgreSQL host authentication is SCRAM from initial publication. A network-isolated initializer reads the
referenced administrator secret through stdin, leaves only the initialized volume, and is replaced by the
steady-state published container with no password environment entry; standby cloning is likewise
stdin-only.

The old order below was not executable from a clean checkout: its unqualified
`ctower-runtime-manifest` and `ctower-private-vps` commands silently selected whichever environment happened
to be on `PATH`. On the development host that was `/srv/projects/ctower/.venv`, which can be older than the
checkout. Do not use that repository verification environment for an install.

Prepare a disposable bootstrap environment outside the checkout with the approved standard-GIL
interpreter. Replace `UNIQUE` with a new owner-only temporary directory for this attempt. Building this
environment does not alter or remove an installed runtime:

```text
uv build --wheel --python /path/to/python3.13 \
  --out-dir /tmp/ctower-bootstrap-UNIQUE/dist
/path/to/python3.13 -m venv /tmp/ctower-bootstrap-UNIQUE/venv
uv pip install --python /tmp/ctower-bootstrap-UNIQUE/venv/bin/python \
  /tmp/ctower-bootstrap-UNIQUE/dist/ctower_workspace-*.whl
```

Before any persistent-runtime command, run the read-only preflight from the checkout with the approved
interpreter. It reads every entry from this checkout's `[project.scripts]`, then asks the isolated
bootstrap-venv interpreter to load the matching installed entry point and inspect the exact script pathname
the commands below will use. A missing, mismatched, unimportable, or non-callable entry point refuses the
install. The installed script must also be a current-user-executable regular file with a nonempty,
syntactically valid Python shim whose shebang resolves to that bootstrap interpreter. The preflight does not
execute scripts because some entries start services or unlock the development keyring.

```text
/path/to/python3.13 -m tools.runtime_preflight --pyproject pyproject.toml \
  --python /tmp/ctower-bootstrap-UNIQUE/venv/bin/python
```

Only a passing preflight starts the persistent-runtime install sequence; it is the first command after
disposable preparation and precedes every mutation of installed runtime state. The first two commands below
use console scripts from `/tmp/ctower-bootstrap-UNIQUE/venv`, which was built from the wheel above.
`install-runtime` creates and verifies the separate permanent venv at
`~/.local/share/ctower-development/runtime/venv`; later systemd and public-CLI commands use only that
permanent venv.

```text
/tmp/ctower-bootstrap-UNIQUE/venv/bin/ctower-runtime-manifest build \
  --source-root . --wheel /tmp/ctower-bootstrap-UNIQUE/dist/ctower_workspace-*.whl \
  --output /tmp/ctower-bootstrap-UNIQUE/development-manifest.json \
  --python /path/to/python3.13
/tmp/ctower-bootstrap-UNIQUE/venv/bin/ctower-private-vps install-runtime \
  --wheel /tmp/ctower-bootstrap-UNIQUE/dist/ctower_workspace-*.whl \
  --manifest /tmp/ctower-bootstrap-UNIQUE/development-manifest.json \
  --packs packs --python /path/to/python3.13 --source-root .
```

`install-runtime` is deliberately first-install-only and refuses an existing runtime path. Automated
upgrade/replacement, staging, pointer exchange, release-triggered service restart, and rollback belong to
the separately reviewed release-lifecycle follow-up.

First install:

```text
~/.local/share/ctower-development/runtime/venv/bin/ctower-private-vps database-up
~/.local/share/ctower-development/runtime/venv/bin/ctower-private-vps install-units \
  --unit-root deploy/private-vps/development/systemd
~/.local/share/ctower-development/runtime/venv/bin/ctower-private-vps bootstrap
~/.local/share/ctower-development/runtime/venv/bin/ctower-private-vps observe
```

Bootstrap persists only a command ID and Secret Service reference until the first-tenant operation,
credential bindings, state write, and service activation finish. Re-running the same command resumes that
checkpoint; it never mints a replacement capability for a partial bootstrap.

`observe` reports `finalizer_health` separately from policy health. It is `HEALTHY` only while the worker
unit is active and a completed finalizer scan (including an empty scan) advanced within ten seconds.
Missing or malformed progress, an inactive/crash-looping worker, a failed scan, a refused command, future
clock data, or progress older than ten seconds is typed `DEGRADED`; unknown is never treated as healthy.

Drive the instance only through the protected public CLI wrapper:

```text
~/.local/share/ctower-development/runtime/venv/bin/ctower-shadow-ctl ticket create ...
~/.local/share/ctower-development/runtime/venv/bin/ctower-shadow-ctl ticket query TICKET_ID
~/.local/share/ctower-development/runtime/venv/bin/ctower-shadow-ctl synthetic run \
  --workflow ctower.trust-spine-four-stage@1 \
  --wait --assert resolved,closed
```

The Docker containers use `--restart unless-stopped`, the user units are enabled under
`default.target`, and user lingering is a host prerequisite. A service restart is proven in this slice;
an actual host reboot remains deferred operational evidence unless the operator schedules it.

Explicit debt: TLS and any external endpoint, complete telemetry/export, backup/key-recovery/restore
drills, independent failure-domain ACK, CP3-D, production claims, and authoritative-writer promotion.

## Upgrade an existing installation

This path upgrades an already complete fixed-path runtime. It composes the disposable bootstrap,
preflight, manifest-build, and protected-CLI steps documented above; do not rebuild those steps around the
repository verification environment or unqualified commands. The replacement verb changes runtime files
only. It does not apply database migrations, reinstall units, or restart already-running processes.

The procedure below therefore refuses a candidate with a migration or unit delta. Such a release needs a
separately reviewed lifecycle plan. It is not safe to hide that delta inside this filesystem-only upgrade.
Run the whole procedure from the clean candidate checkout as the dedicated development account, with no
secret values in the shell environment.

### Secure rollback material and pre-state

Create a new archive; never reuse, modify, or delete an existing entry under
`~/.local/state/ctower/development-archives/`. Copy the installed wheel, manifest, packs, and installed
distribution list before candidate preparation. Stream `pg_dumpall` through compression and encryption so
no plaintext dump is retained. The existing PostgreSQL administrator secret is read from Secret Service
through an anonymous file descriptor; it never appears in a file, argument, environment variable, or log.

Run this Bash block from the candidate checkout:

```bash
set -euo pipefail
umask 077

runtime_root="$HOME/.local/share/ctower-development/runtime"
archive_parent="$HOME/.local/state/ctower/development-archives"
archive_root="$archive_parent/$(date -u +%Y%m%dT%H%M%SZ)-runtime-upgrade"
database_backup="$archive_root/database/ctower-development-pg17-all.sql.gz.gpg"

test -d "$runtime_root"
test -f "$runtime_root/manifest.json"
test -x "$runtime_root/venv/bin/ctower-private-vps"
mkdir -m 0700 "$archive_root"
mkdir -m 0700 "$archive_root/runtime" "$archive_root/database"

wheel_name="$(
  "$runtime_root/venv/bin/python" - "$runtime_root/manifest.json" <<'PY'
import json
import pathlib
import sys

name = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["wheel"]["filename"]
if not isinstance(name, str) or not name or pathlib.PurePath(name).name != name:
    raise SystemExit("installed manifest has an unsafe wheel filename")
print(name)
PY
)"
test -f "$runtime_root/$wheel_name"
install -m 0600 "$runtime_root/$wheel_name" "$archive_root/runtime/$wheel_name"
install -m 0600 "$runtime_root/manifest.json" "$archive_root/runtime/manifest.json"
install -m 0600 \
  "$runtime_root/installed-distributions.txt" \
  "$archive_root/runtime/installed-distributions.txt"
cp --archive --no-target-directory "$runtime_root/packs" "$archive_root/runtime/packs"
find "$archive_root/runtime" -type f -print0 |
  sort -z |
  xargs -0 sha256sum > "$archive_root/runtime.sha256"

exec {archive_key_fd}< <(
  "$runtime_root/venv/bin/python" -c \
    'from ctower_api.development_secrets import load_secret; print(load_secret("secret-service:ctower-development/postgres-admin"), end="")'
)
docker exec --user postgres ctower-development-primary \
  pg_dumpall --clean --if-exists --quote-all-identifiers |
  gzip --stdout |
  gpg --batch --quiet --no-symkey-cache --symmetric --cipher-algo AES256 \
    --pinentry-mode loopback --passphrase-fd "$archive_key_fd" \
    --output "$database_backup"
exec {archive_key_fd}<&-

exec {archive_key_fd}< <(
  "$runtime_root/venv/bin/python" -c \
    'from ctower_api.development_secrets import load_secret; print(load_secret("secret-service:ctower-development/postgres-admin"), end="")'
)
gpg --batch --quiet --no-symkey-cache --decrypt \
  --pinentry-mode loopback --passphrase-fd "$archive_key_fd" \
  "$database_backup" |
  gzip --test
exec {archive_key_fd}<&-

sync -f "$database_backup"
sha256sum "$database_backup" > "$archive_root/database.sha256"
test ! -e "$archive_root/database/ctower-development-pg17-all.sql.gz"
printf 'archive_root=%s\n' "$archive_root"
```

Keep the printed `archive_root`. The `.gpg` file is the only retained database dump. Do not add a
decrypted dump to the archive later.

Capture the old source revision and read-only live baseline through installed, protected commands:

```bash
set -euo pipefail

runtime_root="$HOME/.local/share/ctower-development/runtime"
old_source_commit="$(
  "$runtime_root/venv/bin/python" - "$runtime_root/manifest.json" <<'PY'
import json
import pathlib
import sys

print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["source_commit"])
PY
)"
git cat-file -e "$old_source_commit^{commit}"
git diff --exit-code "$old_source_commit"..HEAD -- \
  packages/ctower-kernel/migrations \
  deploy/private-vps/development/systemd
```

A nonzero `git diff --exit-code` is a stop, not permission to run `database-up`, reinstall units, or
improvise a mixed lifecycle.

#### Capture the protected baseline

After the delta gate succeeds, replace `PRINTED_ARCHIVE_ROOT` with the path printed by the archive block
and capture the three protected product proofs in their own executable block:

```bash
set -euo pipefail

runtime_root="$HOME/.local/share/ctower-development/runtime"
archive_root=PRINTED_ARCHIVE_ROOT
test -d "$archive_root"

"$runtime_root/venv/bin/ctower-private-vps" observe |
  tee "$archive_root/pre-observe.json"
"$runtime_root/venv/bin/ctower-shadow-ctl" control health |
  tee "$archive_root/pre-health.json"
"$runtime_root/venv/bin/ctower-shadow-ctl" board query |
  tee "$archive_root/pre-board.json"
```

### Prepare and preflight the candidate

Use the exact approved standard-GIL interpreter and unique disposable bootstrap directory selected in the
shared preparation above. Retain those concrete paths in this shell:

```bash
approved_python=/path/to/python3.13
bootstrap_root=/tmp/ctower-bootstrap-UNIQUE
test -x "$approved_python"
test -x "$bootstrap_root/venv/bin/python"
```

Before manifest generation, `install-runtime`, or any installed-runtime mutation, run the shared preflight
against that candidate environment:

```bash
"$approved_python" -m tools.runtime_preflight \
  --pyproject pyproject.toml \
  --python "$bootstrap_root/venv/bin/python"
```

A usable candidate prints `runtime preflight: PASS`, the candidate environment, `project scripts: 9`, and
one named `PASS <script> -> <target>` line for each checkout script. A refusal exits 1 and names each
failed script and check, for example:

```text
runtime preflight: FAIL
environment: /tmp/ctower-bootstrap-UNIQUE/venv/bin/python
project scripts: 9
  FAIL ctower-runtime-manifest -> tools.runtime_manifest.__main__:main: script path check failed: installed script does not exist
```

Metadata identity, target loading and callability, script-file existence, current-user executable mode,
shim shebang/interpreter identity, nonempty body, and Python syntax are independently checked. Any `FAIL`
is the end of this attempt: retain its complete output, leave the old runtime serving, and do not repair the
candidate and continue.

Only after all nine scripts pass, build `development-manifest.json` with the shared manifest command above.
Do not substitute the checkout's `.venv` for either bootstrap path.

### Replace once

Record the candidate commit and invoke the bootstrap-installed verb exactly once:

```bash
set -euo pipefail

candidate_commit="$(git rev-parse HEAD)"
candidate_wheel=("$bootstrap_root"/dist/ctower_workspace-*.whl)
test "${#candidate_wheel[@]}" -eq 1
test -f "${candidate_wheel[0]}"
test -f "$bootstrap_root/development-manifest.json"

"$bootstrap_root/venv/bin/ctower-private-vps" install-runtime \
  --wheel "${candidate_wheel[0]}" \
  --manifest "$bootstrap_root/development-manifest.json" \
  --packs packs \
  --python "$approved_python" \
  --source-root . \
  --replace
```

The verb takes an exclusive `flock` on the runtime parent for its whole operation. While holding it, the
verb verifies the manifest, creates and verifies a complete
`runtime-replacement-<uuid>` sibling, runs the candidate's installed
`ctower-private-vps --help`, creates the exchange peer, and makes one Linux
`renameat2(RENAME_EXCHANGE)` call. There is no two-rename fallback and no missing-runtime pathname window.
On success, `runtime` selects the candidate and the displaced runtime is retained at `runtime-previous`.

If the verb exits nonzero before the exchange, the old `runtime` remains selected and already-running
processes continue using their open old files. Stop after capturing the complete output; read the current
manifest and make a real protected API query to prove the old service still serves. Do not retry. A failed
or interrupted attempt can consume an earlier retained predecessor or leave an unreferenced sibling, so
neither a retry nor cleanup is authorized by this runbook.

Success changes the filesystem selection only. Existing API and worker processes still execute the old
generation until explicitly restarted.

### Restart and verify

First prove that the filesystem exchange selected the candidate and retained the archived manifest:

```bash
set -euo pipefail

runtime_root="$HOME/.local/share/ctower-development/runtime"
runtime_previous="$HOME/.local/share/ctower-development/runtime-previous"

"$bootstrap_root/venv/bin/python" - \
  "$runtime_root/manifest.json" \
  "$runtime_previous/manifest.json" \
  "$archive_root/runtime/manifest.json" \
  "$candidate_commit" <<'PY'
import json
import pathlib
import sys

current = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
previous = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
archived = json.loads(pathlib.Path(sys.argv[3]).read_text(encoding="utf-8"))
if current["source_commit"] != sys.argv[4]:
    raise SystemExit("current runtime does not select the candidate commit")
if previous != archived:
    raise SystemExit("runtime-previous does not match the archived predecessor manifest")
print(json.dumps({"current": current, "previous": previous}, sort_keys=True))
PY

systemctl --user restart \
  ctower-development-api.service \
  ctower-development-worker.service
systemctl --user is-active \
  ctower-development-keyring.service \
  ctower-development-db.service \
  ctower-development-api.service \
  ctower-development-worker.service

health_ready=false
for attempt in {1..30}; do
  if "$runtime_root/venv/bin/ctower-shadow-ctl" control health \
    > "$archive_root/post-health.json.tmp"; then
    mv "$archive_root/post-health.json.tmp" "$archive_root/post-health.json"
    health_ready=true
    break
  fi
  sleep 1
done
test "$health_ready" = true

observe_ready=false
for attempt in {1..30}; do
  if "$runtime_root/venv/bin/ctower-private-vps" observe \
      > "$archive_root/post-observe.json.tmp" &&
    "$bootstrap_root/venv/bin/python" - "$archive_root/post-observe.json.tmp" <<'PY'
import json
import pathlib
import sys

observation = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
ready = (
    observation["api"] == "active"
    and observation["worker"] == "active"
    and observation["primary_container"] == "running"
    and observation["standby_container"] == "running"
    and observation["replication"] == ["streaming", "sync"]
    and observation["finalizer_health"]["status"] == "HEALTHY"
)
raise SystemExit(0 if ready else 1)
PY
  then
    mv "$archive_root/post-observe.json.tmp" "$archive_root/post-observe.json"
    observe_ready=true
    break
  fi
  sleep 1
done
test "$observe_ready" = true

"$bootstrap_root/venv/bin/python" -m json.tool "$archive_root/post-health.json"
"$bootstrap_root/venv/bin/python" -m json.tool "$archive_root/post-observe.json"
"$runtime_root/venv/bin/ctower-shadow-ctl" board query |
  tee "$archive_root/post-board.json"
```

The two 30-second loops are bounded readiness polling, never replacement retries. The health query must
succeed through the loopback API. `observe` must name the selected installation, show API and worker
`active`, both containers `running`, replication `streaming/sync`, and `finalizer_health.status`
`HEALTHY`. The shadow-only durability status remains explicitly `DEGRADED` with reason
`development_offhost_ack_cp3_d_not_proven`; it is not the finalizer result.

Compare the pre/post ticket count and Board state, then make a record-specific protected read:

```bash
set -euo pipefail

"$runtime_root/venv/bin/python" - \
  "$archive_root/pre-observe.json" \
  "$archive_root/post-observe.json" \
  "$archive_root/pre-board.json" \
  "$archive_root/post-board.json" <<'PY'
import json
import pathlib
import sys

pre_observe, post_observe, pre_board, post_board = (
    json.loads(pathlib.Path(path).read_text(encoding="utf-8")) for path in sys.argv[1:]
)
if post_observe["counts"]["tickets"] != pre_observe["counts"]["tickets"]:
    raise SystemExit("ticket count changed across the runtime upgrade")
if post_board["health"] != "CURRENT":
    raise SystemExit("post-upgrade Board is not CURRENT")
if post_board["projection_watermark"] != post_board["source_watermark"]:
    raise SystemExit("post-upgrade Board projection is not caught up")
if post_board["source_watermark"] < pre_board["source_watermark"]:
    raise SystemExit("post-upgrade Board watermark moved backwards")
if not pre_board["cards"]:
    raise SystemExit("pre-upgrade Board has no ticket available for a read proof")
print(pre_board["cards"][0]["ticket_id"])
PY

read_ticket_id="$(
  "$runtime_root/venv/bin/python" - "$archive_root/pre-board.json" <<'PY'
import json
import pathlib
import sys

print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["cards"][0]["ticket_id"])
PY
)"
"$runtime_root/venv/bin/ctower-shadow-ctl" ticket query "$read_ticket_id"
```

Any post-exchange restart or verification failure is not an `install-runtime` failure and does not
automatically restore the predecessor. Capture the current and previous manifests, service state, health,
observation, and protected-read output, then stop for a rollback decision.

### Rollback readiness and rollback

Do not exercise rollback merely to test it on the live instance. Readiness requires the predecessor
manifest to equal the secured pre-upgrade manifest and the two exact preconditions enforced by
`rollback-runtime`: both `runtime` and `runtime-previous` contain `manifest.json` and an executable
`venv/bin/ctower-private-vps`.

```bash
set -euo pipefail

test -f "$runtime_root/manifest.json"
test -x "$runtime_root/venv/bin/ctower-private-vps"
test -f "$runtime_previous/manifest.json"
test -x "$runtime_previous/venv/bin/ctower-private-vps"
"$bootstrap_root/venv/bin/python" - \
  "$archive_root/runtime/manifest.json" \
  "$runtime_previous/manifest.json" <<'PY'
import json
import pathlib
import sys

archived = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
previous = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
if previous != archived:
    raise SystemExit("runtime-previous is not the secured predecessor")
print(json.dumps(previous, sort_keys=True))
PY
```

The relocated predecessor venv has fixed-path shebangs, so executing its entry point while it is named
`runtime-previous` is not version evidence. The manifest and executable-file checks above are the actual
verb preconditions; execute the entry point only after an authorized exchange returns it to `runtime`.

If rollback is authorized, use the currently selected installed verb, restart the processes so they open
the restored files, and repeat every post-verification read:

```bash
set -euo pipefail

"$runtime_root/venv/bin/ctower-private-vps" rollback-runtime
systemctl --user restart \
  ctower-development-api.service \
  ctower-development-worker.service
systemctl --user is-active \
  ctower-development-keyring.service \
  ctower-development-db.service \
  ctower-development-api.service \
  ctower-development-worker.service
"$bootstrap_root/venv/bin/python" -m json.tool "$runtime_root/manifest.json"
"$runtime_root/venv/bin/ctower-shadow-ctl" control health
"$runtime_root/venv/bin/ctower-private-vps" observe
"$runtime_root/venv/bin/ctower-shadow-ctl" board query
"$runtime_root/venv/bin/ctower-shadow-ctl" ticket query "$read_ticket_id"
```

`rollback-runtime` holds the same whole-verb lock and performs one atomic exchange. It swaps the two slots;
it is not a multi-generation history, does not reverse database migrations or unit changes, and does not
restart services. If either slot is incomplete or the predecessor manifest is not the expected secured
generation, do not run it. Preserve the state and use a separately reviewed recovery decision; the archive
is rollback material, not authority to improvise an in-place restore.

## Upgrade with migration 0037

This path is the 0037-specific migration-inclusive counterpart to [Upgrade an existing
installation](#upgrade-an-existing-installation). It covers only
`0037_relax_checkpoint_key_domain.sql`: the migration broadens two existing `CHECK` constraints to the
already-authored contract domain, rewrites no rows, drops no data, and declares an exact forward test,
backup checkpoint, and forward-compensation rule in the checksum-locked migration manifest. A different
migration, destructive schema change, data migration, constraint narrowing, unit delta, or any migration
whose predecessor runtime cannot safely use the resulting schema is a stop for an operator-owned
expand/migrate/contract decision. This section does not authorize it or claim to be a generic migration
procedure.

The persistent mutation order is fixed: verified backup, migration apply, runtime replace, service restart,
live verification, then rollback-readiness proof. Candidate preparation and preflight are read-only with
respect to the installed runtime and happen before the migration apply. Run the complete procedure from the
clean candidate checkout as the dedicated development account, with no secret values in the shell
environment.

### Confirm the exact 0037 delta and capture its checkpoint

First complete [Secure rollback material and pre-state](#secure-rollback-material-and-pre-state) through the
encrypted backup integrity check and retain its printed `archive_root`. Do not run that section's
filesystem-only migration/unit delta gate: this path intentionally admits the one exact migration delta
below. It still refuses every systemd-unit delta and every unexpected migration file:

```bash
set -euo pipefail

runtime_root="$HOME/.local/share/ctower-development/runtime"
old_source_commit="$(
  "$runtime_root/venv/bin/python" - "$runtime_root/manifest.json" <<'PY'
import json
import pathlib
import sys

print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["source_commit"])
PY
)"
git cat-file -e "$old_source_commit^{commit}"
git diff --exit-code "$old_source_commit"..HEAD -- \
  deploy/private-vps/development/systemd

expected_migration_delta=$'A\tpackages/ctower-kernel/migrations/0037_relax_checkpoint_key_domain.sql\nM\tpackages/ctower-kernel/migrations/manifest.json'
actual_migration_delta="$(
  git diff --name-status "$old_source_commit"..HEAD -- \
    packages/ctower-kernel/migrations
)"
printf '%s\n' "$actual_migration_delta"
test "$actual_migration_delta" = "$expected_migration_delta"

git diff "$old_source_commit"..HEAD -- \
  packages/ctower-kernel/migrations/0037_relax_checkpoint_key_domain.sql \
  packages/ctower-kernel/migrations/manifest.json
```

Review the printed SQL and declaration before continuing. For 0037, both replaced constraints must move
from the narrower increment-only pattern to
`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`; the manifest must name the exact forward test, require a verified
database backup plus the existing constraint definitions and stored keys, and require reviewed forward
compensation before any later narrowing. A different diff or declaration stops here. The git-tree gate is
also backed by the kernel's `ledger-schema-mismatch` refusal: `database-up` will not advance a ledger whose
last recorded schema attestation differs from the live schema.

The encrypted cluster backup above satisfies the database-backup part of 0037's checkpoint. Capture the
other declared facts from the primary without putting the administrator secret in an argument or
environment variable. Replace `PRINTED_ARCHIVE_ROOT` with the path printed by the archive block:

```bash
set -euo pipefail
umask 077

archive_root=PRINTED_ARCHIVE_ROOT
migration_evidence="$archive_root/migration-0037"
test -d "$archive_root/runtime"
test -f "$archive_root/database/ctower-development-pg17-all.sql.gz.gpg"
mkdir -m 0700 "$migration_evidence"

docker exec --user postgres ctower-development-primary \
  psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 --csv --command "
    SELECT constraint_row.conrelid::regclass::text AS relation,
           constraint_row.conname AS constraint_name,
           pg_get_constraintdef(constraint_row.oid, true) AS definition
    FROM pg_constraint AS constraint_row
    WHERE constraint_row.conname IN (
      'project_delivery_checkpoint_definitions_checkpoint_key_check',
      'project_delivery_projection_rows_checkpoint_key_check'
    )
    ORDER BY relation, constraint_name
  " > "$migration_evidence/pre-constraints.csv"

docker exec --user postgres ctower-development-primary \
  psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 --csv --command "
    SELECT 'project_delivery_checkpoint_definitions' AS relation, checkpoint_key
    FROM project_delivery_checkpoint_definitions
    UNION ALL
    SELECT 'project_delivery_projection_rows' AS relation, checkpoint_key
    FROM project_delivery_projection_rows
    ORDER BY relation, checkpoint_key
  " > "$migration_evidence/pre-checkpoint-keys.csv"

sync -f "$migration_evidence/pre-constraints.csv"
sync -f "$migration_evidence/pre-checkpoint-keys.csv"
sha256sum \
  "$migration_evidence/pre-constraints.csv" \
  "$migration_evidence/pre-checkpoint-keys.csv" \
  > "$migration_evidence/pre-state.sha256"
sha256sum -c "$migration_evidence/pre-state.sha256"
sync -f "$migration_evidence/pre-state.sha256"
```

Retain `archive_root` and `migration_evidence` in this shell. Now run the separate [Capture the protected
baseline](#capture-the-protected-baseline) block, producing `pre-observe.json`, `pre-health.json`, and
`pre-board.json`. Do not substitute direct database reads for those product proofs.

### Prepare and preflight before applying

Complete [Prepare and preflight the candidate](#prepare-and-preflight-the-candidate), including the shared
wheel build and `development-manifest.json` build. A preflight refusal still ends the attempt before any
migration. The migration command below must come from that verified candidate bootstrap, because the
currently installed predecessor does not contain the candidate migration.

### Apply the migration once

Run the candidate's `database-up` exactly once and retain the complete output. The verb starts the existing
primary/standby pair if necessary, serializes role reconciliation and migration work with the migration
advisory lock, loads the strict manifest, verifies its ordered resource inventory and checksums, applies the
pending database SQL transactionally, closes role authority, records the attested migration ledger, restores
the development durability configuration, and waits for synchronous replication.

```bash
set -euo pipefail

archive_root=PRINTED_ARCHIVE_ROOT
bootstrap_root=/tmp/ctower-bootstrap-UNIQUE
migration_evidence="$archive_root/migration-0037"
test -d "$migration_evidence"
test -x "$bootstrap_root/venv/bin/ctower-private-vps"

migration_log="$migration_evidence/database-up.log"
set +e
"$bootstrap_root/venv/bin/ctower-private-vps" database-up 2>&1 |
  tee "$migration_log"
migration_status="${PIPESTATUS[0]}"
set -e
sync -f "$migration_log"
if [ "$migration_status" -ne 0 ]; then
  printf 'database-up failed with status %s; STOP without retry\n' "$migration_status" >&2
  exit "$migration_status"
fi
```

Each bounded coordination operation already performs its only retries: at most three attempts within twenty
seconds for migration-lock acquisition and for each role-reconciliation operation, and only for classified
connection, capacity, lock, cancellation, or shutdown failures. A nonzero exit means that one of those
policies has either been exhausted or the failure was not retryable.

If migration SQL itself fails, the candidate's database transaction rolls back its schema changes and writes
no migration-ledger row. That is not the only possible failed state. Role reconciliation occurs on separate
connections, and the schema transaction commits before the post-schema role closure and ledger attestation.
A later failure can therefore leave committed candidate schema or role changes with no new ledger row. The
database pair may also have been started while the predecessor runtime remains selected. Capture the log,
current installed manifest, unit/container state, current ledger/schema, and protected-read result, then
stop for an operator decision. Do not retry `database-up`, replace the runtime, restart services, clean up,
or restore the archive in the same attempt.

On success, capture and assert the ledger row, resulting constraints, and unchanged stored keys before
replacing the runtime. Replace both path placeholders with the same concrete values used above:

```bash
set -euo pipefail

archive_root=PRINTED_ARCHIVE_ROOT
bootstrap_root=/tmp/ctower-bootstrap-UNIQUE
migration_evidence="$archive_root/migration-0037"
test -d "$migration_evidence"
test -x "$bootstrap_root/venv/bin/python"

docker exec --user postgres ctower-development-primary \
  psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 --csv --command "
    SELECT migration_id, sha256, application_kind, result_schema_sha256, applied_at
    FROM ctower_schema_migrations
    WHERE migration_id = '0037_relax_checkpoint_key_domain.sql'
  " > "$migration_evidence/post-ledger.csv"

docker exec --user postgres ctower-development-primary \
  psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 --csv --command "
    SELECT constraint_row.conrelid::regclass::text AS relation,
           constraint_row.conname AS constraint_name,
           pg_get_constraintdef(constraint_row.oid, true) AS definition
    FROM pg_constraint AS constraint_row
    WHERE constraint_row.conname IN (
      'project_delivery_checkpoint_definitions_checkpoint_key_check',
      'project_delivery_projection_rows_checkpoint_key_check'
    )
    ORDER BY relation, constraint_name
  " > "$migration_evidence/post-constraints.csv"

docker exec --user postgres ctower-development-primary \
  psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 --csv --command "
    SELECT 'project_delivery_checkpoint_definitions' AS relation, checkpoint_key
    FROM project_delivery_checkpoint_definitions
    UNION ALL
    SELECT 'project_delivery_projection_rows' AS relation, checkpoint_key
    FROM project_delivery_projection_rows
    ORDER BY relation, checkpoint_key
  " > "$migration_evidence/post-checkpoint-keys.csv"

ledger_rows="$(
  docker exec --user postgres ctower-development-primary \
    psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 \
      --tuples-only --no-align --command "
        SELECT count(*) FROM ctower_schema_migrations
        WHERE migration_id = '0037_relax_checkpoint_key_domain.sql'
      "
)"
test "$ledger_rows" = 1

expected_schema_sha256="$(
  "$bootstrap_root/venv/bin/python" - \
    packages/ctower-kernel/migrations/manifest.json <<'PY'
import json
import pathlib
import sys

migration_id = "0037_relax_checkpoint_key_domain.sql"
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
matches = [item for item in manifest["migrations"] if item["path"] == migration_id]
if len(matches) != 1 or manifest["adoption_baseline"]["through"] != migration_id:
    raise SystemExit("manifest does not declare exactly one terminal migration 0037")
print(manifest["adoption_baseline"]["schema_sha256"])
PY
)"
actual_schema_sha256="$(
  docker exec --user postgres ctower-development-primary \
    psql --dbname=ctower --no-psqlrc --set=ON_ERROR_STOP=1 \
      --tuples-only --no-align --command "
        SELECT result_schema_sha256 FROM ctower_schema_migrations
        WHERE migration_id = '0037_relax_checkpoint_key_domain.sql'
      "
)"
if [ "$actual_schema_sha256" != "$expected_schema_sha256" ]; then
  printf 'post-0037 schema digest mismatch: expected %s, observed %s\n' \
    "$expected_schema_sha256" "$actual_schema_sha256" >&2
  exit 1
fi
printf 'post-0037 schema digest: PASS (%s)\n' "$actual_schema_sha256"

"$bootstrap_root/venv/bin/python" - \
  "$migration_evidence/post-constraints.csv" <<'PY'
import csv
import pathlib
import sys

definition = "CHECK (checkpoint_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'::text)"
expected = {
    (
        "project_delivery_checkpoint_definitions",
        "project_delivery_checkpoint_definitions_checkpoint_key_check",
        definition,
    ),
    (
        "project_delivery_projection_rows",
        "project_delivery_projection_rows_checkpoint_key_check",
        definition,
    ),
}
with pathlib.Path(sys.argv[1]).open(encoding="utf-8", newline="") as handle:
    observed = {
        (row["relation"], row["constraint_name"], row["definition"])
        for row in csv.DictReader(handle)
    }
if observed != expected:
    raise SystemExit(f"post-0037 constraints differ from the authored definitions: {observed!r}")
print("post-0037 constraint definitions: PASS")
PY

if ! cmp --silent \
    "$migration_evidence/pre-checkpoint-keys.csv" \
    "$migration_evidence/post-checkpoint-keys.csv"; then
  printf 'stored checkpoint_key values changed while applying migration 0037\n' >&2
  exit 1
fi
printf 'post-0037 stored checkpoint_key values: unchanged\n'

sync -f "$migration_evidence/post-ledger.csv"
sync -f "$migration_evidence/post-constraints.csv"
sync -f "$migration_evidence/post-checkpoint-keys.csv"
sha256sum \
  "$migration_evidence/post-ledger.csv" \
  "$migration_evidence/post-constraints.csv" \
  "$migration_evidence/post-checkpoint-keys.csv" \
  > "$migration_evidence/post-state.sha256"
sha256sum -c "$migration_evidence/post-state.sha256"
sync -f "$migration_evidence/post-state.sha256"
```

### Replace, restart, verify, and prove rollback readiness

After the successful ledger proof, run [Replace once](#replace-once) exactly once. The database is already at
0037 at this point. If replacement fails before exchange, preserve that compatible relaxed schema and follow
the existing old-runtime serving proof; do not treat the encrypted backup as permission to narrow the
constraint or discard later accepted facts.

On replacement success, complete [Restart and verify](#restart-and-verify), including manifest identity,
unit state, bounded readiness, replication, finalizer health, ticket-count/Board comparisons, and one
record-specific protected read.

After those live checks pass, run 0037's manifest-declared forward test from the clean candidate checkout.
The test owns a uniquely named disposable Compose project and database; it does not connect to the installed
development pair. Create a separate hash-locked verification environment rather than adding test packages
to the candidate bootstrap. Replace every placeholder below with the concrete path retained for this
attempt. The declared node ID is recorded in `forward-test-nodeid.txt`, environment installation output in
`forward-test-environment.log`, and pytest output in `forward-test.log`:

```bash
set -euo pipefail

approved_python=/path/to/python3.13
archive_root=PRINTED_ARCHIVE_ROOT
bootstrap_root=/tmp/ctower-bootstrap-UNIQUE
forward_test_root=/tmp/ctower-forward-test-UNIQUE
migration_evidence="$archive_root/migration-0037"
test -x "$approved_python"
test -x "$bootstrap_root/venv/bin/python"
test -d "$migration_evidence"
test ! -e "$forward_test_root"

"$approved_python" -m venv "$forward_test_root/venv"
"$forward_test_root/venv/bin/python" -m pip install \
  --disable-pip-version-check --require-hashes \
  -r requirements/verify.txt 2>&1 |
  tee "$migration_evidence/forward-test-environment.log"

forward_test="$(
  "$bootstrap_root/venv/bin/python" - \
    packages/ctower-kernel/migrations/manifest.json <<'PY'
import json
import pathlib
import sys

migration_id = "0037_relax_checkpoint_key_domain.sql"
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
matches = [item for item in manifest["migrations"] if item["path"] == migration_id]
if len(matches) != 1:
    raise SystemExit("manifest does not declare exactly one migration 0037")
declaration = matches[0]["forward_test"]
if not declaration.startswith("pytest:"):
    raise SystemExit("migration 0037 forward_test is not a pytest declaration")
print(declaration.removeprefix("pytest:"))
PY
)"
test "$forward_test" = \
  "tests/acceptance/increment-1/test_checkpoint_delivery.py::test_non_increment_checkpoint_key_materializes_and_projects_end_to_end"
printf '%s\n' "$forward_test" > "$migration_evidence/forward-test-nodeid.txt"

set +e
"$forward_test_root/venv/bin/python" -m pytest --quiet "$forward_test" 2>&1 |
  tee "$migration_evidence/forward-test.log"
forward_test_status="${PIPESTATUS[0]}"
set -e
sync -f "$migration_evidence/forward-test-environment.log"
sync -f "$migration_evidence/forward-test-nodeid.txt"
sync -f "$migration_evidence/forward-test.log"
test "$forward_test_status" -eq 0
```

Only after the declared forward test passes, complete the non-mutating readiness proof in [Rollback
readiness and rollback](#rollback-readiness-and-rollback).

`rollback-runtime` still swaps only runtime files. It never reverses migration 0037. That is safe for this
narrow class because the predecessor can continue using its former subset of a now-broader accepted key
domain. Exercise the runtime rollback only after a separate authorization, restart both processes, and
repeat every post-verification read as the existing section requires. Restoring the encrypted database or
adding a compensating migration is a separate operator decision, never automatic rollback or cleanup.
