# Releases and versioning

ctower uses [Semantic Versioning](https://semver.org/) and Release Please. The repository currently records
version `0.21.0`. The authored HTTP contract still records `0.0.0` because it makes no compatibility
promise. Neither number means that a supported product release exists.
The private-VPS E2 shadow path builds and verifies a wheel plus runtime manifest from source, but neither is
published and the release workflow does not deploy them. A release contains the tagged source tree,
generated changelog, and GitHub release notes only.

## Public API

The public API is any documented surface that users or external integrations are expected
to depend on. It includes:

- published HTTP and event contracts;
- CLI commands, flags, output schemas, and exit behavior;
- versioned workflow, policy, extension, and adapter contracts;
- supported configuration keys and environment variables;
- persisted formats that promise import, export, backup, or restore compatibility.

Internal modules, database tables, generated implementation details, experimental surfaces
explicitly marked unstable, and unpublished design proposals are not public API. A surface
does not become public merely because it is visible in the source tree.

`VERSION` is the canonical repository release version. `.release-please-manifest.json` is
Release Please's tracking state; the root `package.json` and `pyproject.toml` versions mirror
`VERSION` for workspace tooling and do not imply npm or Python package publication. The release
pull request updates all four values atomically, and `just check` rejects version drift.

## SemVer policy

- `fix:` is a backward-compatible correction and proposes a patch release.
- `feat:` is backward-compatible functionality and proposes a minor release.
- `type!:` or a `BREAKING CHANGE:` footer proposes a major release.
- Other accepted Conventional Commit types may appear in release notes but do not
  necessarily cause a release on their own.

Versions before `1.0.0` describe an actively developing public API. Minor releases may make
breaking changes when they are clearly documented; patch releases remain backward compatible
within their minor line. `0.x.y` is pre-1.0 maturity, not a SemVer prerelease suffix. If the
project later publishes preview builds such as `1.0.0-rc.1`, Release Please prerelease mode
must first be enabled by a reviewed configuration change.

## Pull request and release flow

1. Give every pull request a Conventional Commit title, for example
   `feat(cli): add ticket assignment` or `fix(workflow): preserve retry lineage`.
2. Merge with **squash merge** so that the validated pull request title becomes the commit on
   `main`. The title check is therefore part of the release contract, not cosmetic lint.
3. Release Please reads releasable commits on `main` and creates or updates one release pull
   request. That pull request owns the proposed `VERSION` and `CHANGELOG.md` changes.
4. Review the generated version and notes. The release pull request must pass the same required
   verification, documentation build, and review checks as any other pull request.
5. Merge the release pull request. Release Please then creates the immutable `vX.Y.Z` tag and
   the matching GitHub Release. This pipeline does not publish packages or deploy ctower.
6. Verify that the tag targets the release pull request merge commit, the GitHub Release notes
   match `CHANGELOG.md`, and the public documentation build for that commit succeeds.

The write-capable Release Please job has no manual trigger. It runs only for an exact push to
`refs/heads/main` in `simjak/ctower`; its job-level guard must remain in place even if trigger syntax is
edited later.

Do not edit `VERSION` or create release tags manually during normal operation. An exceptional
operator-directed version uses Release Please's documented `Release-As: X.Y.Z` commit footer and
still flows through a reviewed release pull request.

## Documentation release gate

A stale or overclaiming document blocks release. Before merging a release pull request:

- build the site with `just docs-check` (`mkdocs build --strict` in an external temporary
  directory);
- update current-state guidance for every changed public surface;
- regenerate inventories and reference material from verified source truth where applicable;
- distinguish proven behavior from planned or residual work, live behavior from snapshots,
  and wired functionality from placeholders;
- include migration and rollback guidance for compatibility-affecting changes;
- use repository-relative links and include no secrets or personally identifiable information.

For authored contracts, the current deterministic code-truth path starts at
`contracts/traceability/sources.json`. Run `python3 -m tools.checks.traceability --root . --write` to update
`generated/traceability-index.json` and its manifest entry, then run the same command with `--check` as the
release gate. Narrative pages remain authored and must be reviewed against the changed code and contracts.

GitHub Pages is built on every pull request but deployed only from trusted `main`. A successful
page deployment proves publication, not runtime correctness.

## Verification provenance

The required `release gate` job is safe for public fork pull requests: it has read-only repository
permission, receives no repository secrets, checks out complete candidate history without persisted
credentials, and invokes the canonical `just check` and `just verify` recipes. Python dependencies are
installed from the hash-locked `requirements/verify.txt`; JavaScript uses the frozen `pnpm-lock.yaml` with
lifecycle scripts disabled. Node distributions and the pnpm, `just`, Actionlint, and Gitleaks release assets
are fetched with bounded HTTPS requests and checked against committed SHA-256 values before execution.

Those versions describe the verification host only. They do not select a supported ctower Python runtime or
create a product lock. Update a binary pin only from the producer's release checksum or
release-asset digest, update its version and digest together, and let the repository supply-chain tests prove
the linkage. Remote GitHub Actions and pre-commit hooks remain pinned to immutable 40-character commits.

## Corrections, rollback, and withdrawal

Published version numbers, tags, changelog entries, and release assets are immutable: never
move a tag, replace an asset under the same version, or reuse a version number.

- For a normal defect, revert the deployment if one exists, fix forward, and publish a new
  patch or otherwise SemVer-appropriate version.
- For incorrect release notes or documentation, correct them in source and publish the
  correction in a newer release. GitHub release prose may add a prominent pointer to the
  correction, but it must not erase the historical record.
- GitHub has no package yank in the current source-only release posture. If package publication
  is added later, each registry's deprecation or yank mechanism must be documented before use;
  a withdrawn version is never republished.
- If continued distribution would expose a secret, personal data, or an active vulnerability,
  invoke the security incident process and restrict access as necessary. Record the exception,
  rotate affected credentials, publish a replacement version, and never reuse the compromised
  version number.

Runtime deployment rollback is separate from source release history. Point the environment at a
previous verified immutable artifact; do not mutate the release that produced it.

## Required repository settings

After the workflows reach GitHub, a maintainer must:

- set Pages source to **GitHub Actions** and restrict the `github-pages` environment to `main`;
- add a fine-grained `RELEASE_PLEASE_TOKEN` Actions secret with repository Contents,
  Issues, and Pull requests read/write access. The workflow safely falls back to
  `GITHUB_TOKEN`, so an unset secret does not make every `main` build fail; however, pull
  requests created by that fallback token do not trigger their own required verification
  workflows. Without the secret, a maintainer must cause a fresh pull-request event (for
  example, close and reopen the release PR) before it can satisfy branch protection;
- require the stable `release gate`, `build documentation`, and `conventional title` checks on `main`;
- enable squash merge and use the pull request title as the default squash commit title;
- prevent force pushes and tag deletion for released versions.
