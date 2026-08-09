# GitHub connector Phase 2 CSO boundary verdict

**STATE: CLEARED-WITH-CONTROLS — SECURITY SHAPE ONLY; OPERATOR ACKNOWLEDGMENT AND
PHASE-2 ACTIVATION ARE STILL REQUIRED.**

**MODEL: gpt-5.6-sol · reasoning effort: max**

Reviewed on 2026-08-09 for the exact GitHub connector candidate in
[`docs/specs/connectors.md`](../specs/connectors.md), blob
`c5e022cebe331c80984578f479e260236326173a`, at `origin/main`
`eac2a1d718451c5cd5f200f99e89cf2681bb8feb`. The proven Phase-1 base is merge
`dabbaa1857524d8d1b82dc9b785f8904f8415901` from PR
[#387](https://github.com/simjak/ctower/pull/387). This clearance is invalidated by any change to
the candidate's credential classes, custody, permissions, ingress, egress, token lifecycle, or frozen
Phase-1 seam.

This document is the CSO analysis for the operator's boundary decision. It is not a product-scope decision,
an accepted Decision, an active build ticket, or permission to make a GitHub network call.

## One-glance boundary decision

| Question | Answer |
| --- | --- |
| Does Phase 2 open a new security boundary? | **Yes.** It adds a non-expiring GitHub App private key, short-lived signing JWTs, one-hour installation access tokens, and outbound traffic to `api.github.com:443`. |
| Is there new ingress? | **No.** Webhooks, OAuth callbacks, and all other inbound GitHub paths remain prohibited. |
| Does kernel authority gain credential or HTTP knowledge? | **No.** The API-owned adapter and trusted composition/minting path own GitHub details; the kernel keeps the frozen provider-neutral seam. |
| May Phase 2 use a PAT, OAuth token, user token, or standing installation token? | **No.** Only a repository-selected GitHub App installation token minted server-side from a referenced private key is admitted. |
| CSO verdict | **CLEARED-WITH-CONTROLS**, subject to every control and named test below. |
| Who makes the boundary decision? | **The OPERATOR.** An explicit acknowledgment is still mandatory before canonical activation. |

## Boundary statement

### New surfaces opened by Phase 2

1. **Credential classes and custody.** Phase 2 introduces a GitHub App private key. The key does not expire
   automatically and therefore remains a long-lived root credential until it is manually rotated or revoked.
   Only its approved vault or operating-system-keyring reference may enter Catalog. The value may be resolved
   temporarily only inside the trusted API composition/minting path; it must never cross the
   `IssueConnector` seam.
2. **Minting lifecycle.** The trusted path uses the private key to sign a GitHub App JWT with a maximum
   ten-minute lifetime, then requests an installation access token. Neither the private key nor JWT is cached.
   The installation token expires after one hour, is treated as an opaque value, lives only in process memory,
   and is refreshed before expiry. Code must not depend on a token prefix, length, or internal format.
3. **Rotation and revocation lifecycle.** Rotation creates a replacement App key, changes the approved secret
   binding, invalidates all local mint/token cache state, proves minting with the replacement, and only then
   deletes the old App key. Revocation deletes or disables the compromised key or installation, immediately
   invalidates local cached tokens, and makes the connector fail closed until an operator-approved binding and
   installation succeed. There is no fallback to an old key or token.
4. **Authorization surface.** The App and every minted token are limited to the selected target repository,
   with exactly repository permissions `Issues: read and write` and `Metadata: read`. No organization or
   account permission, webhook subscription, user authorization, or access to every repository is admitted.
5. **Egress surface.** Phase 2 adds only direct HTTPS requests to `api.github.com:443`, for installation-token
   minting and the exact Issue operations. Redirects are disabled. A redirect, alternate origin, alternate
   port, or resolved destination outside the approved origin fails before credential forwarding.

The current GitHub contract was rechecked on 2026-08-09 against the vendor documentation for
[private-key custody and rotation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps),
[JWT minting](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app),
[installation-token minting and expiry](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app),
and [least-privilege App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).
Phase 2 must recheck those documents at build time and pin the observed API version in its evidence bundle.

### Reused unchanged from the proven GitLab path

- Catalog and authored configuration carry a strict secret-binding name, never credential bytes. Deployment
  resolves the reference at the trusted API composition boundary.
- Kernel Integrations retains the frozen two-method `IssueConnector` Interface. It imports no provider,
  credential, HTTP, app, runner, CLI, web, or persistence client.
- The strict result union, retry classification, four-attempt/ten-second budget, bounded backoff, deterministic
  marker reconciliation, and terminal `AmbiguousWrite` behavior remain core-owned and unchanged.
- Leases, fences, cursor and progress storage, observation/delivery receipts, external-untrusted intake, and
  proof-gated close remain core-owned. Credential material never enters any of them.
- The API keeps a closed static first-party registry. There is no dynamic plugin loading, public
  provider-general API, arbitrary base URL, or provider-owned record-tier persistence.
- GitHub must pass the unchanged shared connector conformance suite. The Phase-1 freeze set must have a zero
  diff; provider-specific parsing, HTTP, authentication, and cursor interpretation stay in the API adapter.

## Mandatory Phase-2 controls and build tests

The Phase-2 build ticket must carry these exact control IDs and test node names. A broader integration test
does not replace a named negative-path test.

| ID | Build requirement | Mandatory named test evidence |
| --- | --- | --- |
| GH-C01 | **Reference-only private-key storage.** Catalog, generated configuration, connector registration, kernel values, persistence, cursors, fixtures, status, and artifacts may contain only the binding name and non-secret App/installation/repository identifiers. Private-key, JWT, and installation-token fields are forbidden. | `test_github_private_key_and_tokens_are_reference_only` validates every serializable boundary and fails on any secret-bearing field. |
| GH-C02 | **Server-side, bounded minting.** Only trusted API composition resolves the private-key reference, signs a JWT of at most ten minutes, and calls the installation-token endpoint. The key and JWT are not cached or forwarded; the installation token remains process-memory-only and refreshes before its one-hour expiry. No token-format assumptions are allowed. | `test_github_installation_token_is_minted_server_side`; `test_github_installation_token_refreshes_before_expiry`; `test_github_token_format_is_opaque`. |
| GH-C03 | **Exact least privilege.** App installation and token mint request select only the configured repository and enumerate exactly `issues=write` and `metadata=read`. The response's repository selection and permissions are verified; broader, missing, or malformed grants fail closed. Webhooks, user tokens, OAuth, PATs, org permissions, and all-repository selection are rejected. | `test_github_token_mint_is_repository_selected_and_least_privilege`; `test_github_registration_refuses_unapproved_auth_and_ingress`. |
| GH-C04 | **Egress allowlist.** The adapter has no configurable origin and may connect only to `api.github.com:443`. Redirect following is off; alternate host/port, redirect, and destination-drift fixtures fail before an authorization header or key-derived JWT can be sent. Only non-secret operation, status-class, request-ID, timing, and retry metadata may be observed. | `test_github_egress_is_pinned_to_api_github_com_443`; `test_github_egress_rejects_redirects_and_destination_drift`. |
| GH-C05 | **Rotation and revocation.** A secret-binding revision change invalidates all mint/token cache state and cannot reuse the old key. The connected-provider revocation drill removes the App key or installation, invalidates cached tokens, observes terminal authentication failure without blind retry, and stays failed closed until an approved replacement binding succeeds. The drill records only identifiers, timestamps, and typed outcomes. | `test_github_key_rotation_rebinds_without_old_key_reuse`; `test_github_revocation_drill_invalidates_cached_tokens_and_fails_closed`. |
| GH-C06 | **No secret values in observable output.** Unique synthetic private-key, JWT, and installation-token taints are exercised through success, HTTP failure, malformed response, refresh, rotation, and revocation paths. None may appear in exceptions, structured failures, logs, telemetry, Record or Inbox messages, status, receipts, snapshots, fixtures, CLI output, URLs, headers captured by hooks, or gate artifacts. | `test_github_secret_taint_never_reaches_observable_outputs` scans every captured and serialized output for all injected taints. |
| GH-C07 | **Frozen authority seam.** GitHub uses the existing two-method Interface, closed registry, result union, core retry/reconciliation, leases/fences, cursor store, and proof-gated close with no Phase-1 freeze-set change or record-tier connection. | `test_github_connector_passes_shared_conformance`; `test_github_phase2_preserves_phase1_freeze_set`. |
| GH-C08 | **Exact GitHub Issue semantics.** The adapter imports only Issues, excludes pull requests returned by the shared Issues endpoint, uses immutable repository identity plus issue number, survives repository rename, orders equal timestamps with an immutable tie-breaker, and delivers the marker comment/close mutation exactly once under reconciliation. | `test_github_pull_requests_are_excluded`; `test_github_repository_rename_preserves_identity`; `test_github_equal_timestamp_cursor_uses_immutable_tie_breaker`; `test_github_comment_and_close_reconciles_exactly_once`. |

The build evidence bundle must include the exact candidate digest, App permission and selected-repository
evidence, test output for every named node, a redacted egress trace, the redacted rotation/revocation drill,
the Phase-1 freeze-set zero diff, `just check`, and `just verify`. Any missing, stale, or nonmatching evidence
means the boundary is not cleared for that build.

## Append-only Decision supersession shape

Do not edit D39 or D43. Append the next available Decision number with a shape equivalent to:

> **D[next] — Admit one narrow GitHub App Issue co-source through the frozen connector seam**
>
> Supersede D39 only where it defers GitHub, and D43 only where its closed registry admits GitLab alone.
> Admit one static first-party `github-issues` adapter for selected repositories, using a GitHub App private-key
> reference, server-minted short-lived installation tokens, exactly `Issues: read/write` plus `Metadata: read`,
> and only `api.github.com:443` egress. Bind activation to GH-C01 through GH-C08, their exact named tests, the
> matching CSO evidence digest, and explicit operator acknowledgment of the new credential/egress boundary.

That supersession must preserve all other D39 and D43 constraints: ordinary `external_untrusted` authority,
proof-gated close, bounded progress, reference-only credentials, the provider-neutral two-method seam, strict
failure union, core-owned retry and reconciliation, generic persistence, the closed static registry, and the
Phase-1 freeze set. It must not activate webhooks, OAuth or user tokens, dynamic plugins, arbitrary providers,
provider-owned persistence, a public provider-general API, or any other GitHub surface.

After operator acknowledgment, the accepted Decision must be reflected in canonical `SPEC.md`, with aligned
derived `ARCHITECTURE.md` and non-normative `IMPLEMENTATION-ROADMAP.md`, before a stable Phase-2 CT ticket and
its dependencies are activated. This verdict document does not perform that activation.

## Verdict and operator boundary

**VERDICT: CLEARED-WITH-CONTROLS (GH-C01 through GH-C08).**

The reviewed candidate has an adequate defensive shape and does not require a security-spec rewrite before
the operator decides. Clearance is conditional on the exact candidate and controls above. The first GitHub
credential resolution or network call remains prohibited until the OPERATOR explicitly acknowledges the new
boundary, the append-only Decision and canonical activation prerequisites land, and matching build evidence
passes CSO review. A change to credentials, permissions, ingress, egress, lifecycle, or the frozen core makes
this verdict stale and requires a new CSO round.

SIGNED-OFF

- seat: CSO
- crew: cso-r2886-phase2
- model: gpt-5.6-sol · reasoning effort: max
- claim: the exact reviewed GitHub connector security shape is cleared only with GH-C01 through GH-C08
- stood-under: App private-key custody, JWT and installation-token lifecycle, least privilege, egress, rotation,
  revocation, taint containment, and preservation of the Phase-1 authority seam
- if-this-breaks: stop the connector, revoke the installation and App key, invalidate cached tokens, preserve
  only redacted evidence, and return the boundary to the OPERATOR and CSO before reactivation

**Security-review disclaimer:** This AI-assisted CSO review is not a substitute for a professional security
audit. It is not comprehensive or guaranteed, and it may miss subtle vulnerabilities or misunderstand complex
authorization flows. Production systems handling sensitive data, payments, or PII should also receive review
from a qualified security professional.
