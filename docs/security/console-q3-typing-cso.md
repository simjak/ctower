# Console Q3 typed-input CSO verdict

| Field | Value |
|---|---|
| State | **CLEARED-WITH-CONTROLS** — security shape only |
| Review date | 2026-08-10 |
| Model | `gpt-5.6-sol` at maximum reasoning effort |
| Current-main base | `7d6827ff9887cee4ae8a917b53aabfefe677804a` |
| Candidate specification | `docs/specs/crew-console.md` at `ddb760e2751b84b2824eb620c5bdd0356c79b291` |
| Candidate SHA-256 | `dc1dee344c608f4235d7fc4454eed6f11b60cd03b535ddbcd03f510755ef117c` |
| Approved ceremony design | `bc822f5f62eedbce6e20304b863a63ae6f120082` |
| Scope | `ConsoleTypeGrant`, `paste_text`, `submit`, and the last trusted boundary before `bin/mux` |

## Verdict at one glance

The proposed typed-command boundary is **CLEARED-WITH-CONTROLS**. It has the right security shape: the
browser submits one strict durable command; only the control plane can mint a short-lived grant; the grant
binds one canonical action; and a final authenticated, linearizable admission immediately before the mux
call permits at most one injection.

This verdict is not product activation, deployment approval, or evidence that Phase 1 is implemented on
current main. The candidate console specification remains subordinate to `SPEC.md`; its canonical
incorporation, stable-ticket activation, prerequisite ordering, implementation, and deployed proofs remain
separate gates. In particular, typing MUST NOT attach to the current `apps/ctower-ui` terminal reader. That
reader directly captures tmux through a server-side dogfood source and does not implement the candidate's
OIDC session, `ConsoleViewGrant`, session allowlist, restricted output custody, or SSE boundary.

The build may proceed only by satisfying every mandatory control below. Missing or unknown evidence is a
refusal, not a partial pass.

## Exact boundary and consequence

The only cleared mutation path is:

```text
authenticated same-origin browser
  -> strict generated HTTPS command (`paste_text` or `submit`)
  -> trusted Access/control-plane authorization and durable transaction
  -> outbox consumer with current workload identity and runner epoch
  -> authenticated final adapter admission and linearizable CAS
  -> registered adapter -> Mission Control `bin/mux` -> exact tmux pane
```

The browser, output stream, runner, adapter, tmux, Mission Control, and terminal contents cannot mint,
extend, transfer, or reinterpret a grant. The browser has no direct route to tmux, `bin/mux`, a generic
process endpoint, or a writable terminal bridge. The adapter has no Record-tier client and can only ask the
narrow final-admission operation whether this exact stored plan was newly admitted.

This is a high-consequence boundary. Injected bytes execute in a live crew terminal under the authority and
ambient access of that crew process. A single confused, replayed, cross-project, or altered command can
produce effects beyond the console itself. The control objective is therefore stronger than ordinary UI
authorization: an unproved fact, changed binding, duplicate delivery, stale epoch, revocation race, or
custody failure must inject zero bytes.

The initial vocabulary is closed:

- `paste_text` is one NFC-normalized UTF-8 value of at most 4,096 bytes. It contains no CR or LF, C0 or C1
  control, terminal escape/ANSI/OSC sequence, NUL, file payload, secret value, or secret-reference expansion.
- `submit` has no text payload and represents exactly one Enter action.
- Multiline paste, arbitrary key events, interrupt, resize, file transfer, shell/session lifecycle, and every
  other terminal control are absent. A later action requires a new canonical contract and a new exact CSO
  verdict.

The input-policy detector runs before accepted command, event, outbox, exact-byte object, or dispatch
mutation. Refusal therefore injects zero bytes and creates no accepted command state. It may append only the
policy-mandated denial, security, suspension, notification, and containment facts.

## Abuse classes and required disposition

| Abuse class | Attack shape | Required disposition |
|---|---|---|
| Grant theft or rebinding | Present a grant from another Actor, browser session, role binding, project, session incarnation, assignment interval, policy revision, or runner epoch | Refuse server-side and inject zero bytes; do not refresh, transfer, or widen the grant |
| Grant replay and race | Reuse, concurrently present, redeliver, or reissue one grant/command around expiry, revocation, crash, or worker failover | One successful final admission at most; every loser injects zero bytes; admission without a provable receipt becomes `state_unknown` and is never reinjected |
| Digest confusion | Change normalization, action, body, byte count, submit policy, requested bytes, mux prefix, planned bytes, or adapter-dispatch bytes while reusing an identity or digest claim | Server-derived canonical digest/count must match every bound field; a pre-dispatch mismatch injects zero bytes; a post-invocation receipt mismatch refuses success and triggers containment because dispatch may already have occurred |
| Fence bypass | Target Commander, another project/engagement, a reused tmux name, stale assignment, changed `@project`, missing allowlist fact, or fenced runner epoch | Refuse direct and indirect requests; revoke the affected session as specified; inject zero bytes |
| Injection past the allowlist | Smuggle newline, control/escape data, an over-limit value, prohibited material, file content, secret expansion, or an unregistered action through encoding or an alternate route | Parse and enforce the closed vocabulary before accepted command/event/outbox, exact-byte object, or dispatch mutation; only policy-mandated refusal/security/containment facts may append; direct/generic routes remain absent |
| Stream tampering | Use SSE event data, cursor, reconnect, output content, or a transport substitution to dispatch input, swap authority, or conceal a gap | Output remains one-way and lease-bound; input exists only as the durable HTTPS command; tampered or unprovable stream state closes with a typed gap/refusal |
| Audit/custody leakage | Recover exact bytes or grant material through logs, URLs, errors, telemetry, screenshots, ordinary projections, exports, crash dumps, or shared keys | Exact bytes remain envelope-encrypted behind the dedicated audited reader; ordinary surfaces expose metadata/digests only; no grant material is observable |

## Mandatory controls and named tests

The names below are acceptance identities, not illustrative suggestions. The implementation candidate must
activate them in the owning manifest and preserve their exact security assertions through the final gate.

### CT-C01 — Proven foundation and no direct attachment

Typing consumes the proven `CT-I1-013` same-origin human session/CSRF boundary and the candidate Phase-1
view-grant, allowlist, restricted-output custody, bounded-SSE, private-network, and direct-path controls.
Production verification of that foundation is a predecessor, as the candidate specification already
requires. The current dogfood tmux capture is not that proof and cannot be adapted into a writable fallback.

- `test_console_typing_requires_proven_phase1_foundation`
- `test_console_type_enabled_composition_has_no_direct_tmux_or_generic_process_route`
- `test_console_browser_has_no_bearer_grant_minting_or_record_tier_authority`

### CT-C02 — Server-side grant theft, replay, use, and expiry enforcement

Only Access/control-plane policy mints a `ConsoleTypeGrant`. It lasts at most 60 seconds, permits one
presentation and one exact action, requires protected reauthentication no older than 10 minutes plus fresh
confirmation of the exact command, and is bound to the exact Actor, role-binding revision, project,
`ConsoleSessionRef`, assignment interval, runner epoch, policy revision, nonce, and revocation state. The
requesting human must hold the exact project's `operator` or `commander` role; `viewer` and every other role
refuse. Per exact Actor/session/incarnation, the controlled server clock also enforces at most four
`paste_text` and six `submit` actions in any minute. Client time and UI countdowns have no authority.

- `test_console_type_grant_is_single_use_and_expires_server_side`
- `test_console_type_grant_theft_rebinding_and_parallel_replay_inject_zero_bytes`
- `test_console_type_grant_requires_fresh_reauthentication_and_exact_confirmation`
- `test_console_type_grant_viewer_and_unauthorized_roles_refuse_with_zero_injection`
- `test_console_type_grant_enforces_four_pastes_and_six_submits_per_minute`

### CT-C03 — Canonical input and digest binding

The trusted server parses the closed action variant and derives the canonical input-object bytes, digest,
byte count, and submit policy. It never trusts client-supplied canonicalization or count. The accepted
command separately records canonical requested bytes and deterministic planned bytes under the pinned
adapter revision, including the mux plan's leading ASCII space. Adapter-dispatch and harness-acknowledged
bytes remain separate fields. The final admission binds the stored injection-plan digest; a changed body
under one command identity is a conflict. A post-invocation receipt mismatch cannot be accepted as success
and triggers runner quarantine, grant/session revocation, and an incident; it does not claim zero injection
because dispatch may already have occurred.

- `test_console_type_grant_binds_server_canonical_action_digest_count_and_submit_policy`
- `test_console_injection_plan_digest_covers_exact_requested_planned_and_mux_bytes`
- `test_console_pre_dispatch_digest_count_or_body_mismatch_injects_zero_bytes`
- `test_console_post_dispatch_receipt_mismatch_refuses_success_and_triggers_containment`

### CT-C04 — Linearizable final admission and crash truth

Immediately before any mux subprocess, the authenticated adapter admission performs one durable CAS keyed by
`(grant_id, client_command_id, runner_epoch)`. Only a newly admitted result may invoke the registered adapter.
Duplicate outbox delivery, competing workers, adapter restart, delayed revocation, and runner fencing permit
at most one mux invocation. Admission followed by a missing or unprovable receipt is `state_unknown`, never
success and never an automatic retry.

- `test_console_final_admission_cas_allows_at_most_one_mux_invocation_under_race`
- `test_console_admission_to_receipt_crash_is_state_unknown_without_reinjection`
- `test_console_stale_epoch_duplicate_delivery_and_revocation_race_inject_zero_bytes`

### CT-C05 — Closed allowlist before mutation

The input policy implements the exact initial vocabulary above with strict decoding, normalization,
post-normalization length measurement, and a versioned prohibited-data corpus. Ambiguous encoding or policy
state refuses. Policy checks finish before accepted command/event/outbox, exact-byte object, or dispatch
mutation. Policy-mandated denial, security, suspension, notification, and containment facts may append, but
no accepted command state may exist.

- `test_console_paste_text_accepts_only_nfc_utf8_within_4096_bytes_and_without_controls`
- `test_console_submit_is_one_empty_enter_action`
- `test_console_input_allowlist_and_prohibited_data_refuse_before_command_or_object_mutation`
- `test_console_prohibited_data_refusal_appends_only_policy_mandated_security_and_containment_facts`

### CT-C06 — Exact fence and Commander refusal

The target is an opaque backend derived from one exact allowed `ConsoleSessionRef`; browser-supplied tmux
names are never authority. Type issuance and final admission both require a non-Commander target, exact live
project match, current assignment interval, current runner epoch, and current append-only
`console_session_allowed` fact. Missing, stale, renamed, cross-project, Commander, or mismatched targets
refuse with zero injection.

- `test_console_commander_session_refuses_type_grant_and_injects_zero_bytes`
- `test_console_session_allowlist_project_assignment_and_epoch_fence_refuse_mismatch`
- `test_console_reused_tmux_name_cannot_rebind_an_allowed_console_session`

### CT-C07 — Exact-byte custody and no grant-material observability

Requested, planned, adapter-dispatch, and any harness-acknowledged exact-byte objects are append-only and
envelope-encrypted with distinct per-object data-encryption-key references. Only
`console_input_audit_reader` may recover them, and every attempted read appends an access fact. Retention,
jurisdiction/classification, legal hold, crypto-erasure, readers, and export approval are explicit versioned
policy values with no defaults. Ordinary logs, URLs, errors, telemetry, projections, screenshots,
notifications, exports, and crash reports contain neither exact bytes nor serialized grants, nonces,
session cookies, reauthentication proofs, capability material, or secret values.

- `test_console_exact_input_objects_use_distinct_envelope_keys_and_audited_reader_access`
- `test_console_exact_input_canary_never_reaches_any_ordinary_surface`
- `test_console_grant_material_never_reaches_logs_urls_errors_telemetry_or_exports`

### CT-C08 — Immediate dispatch revocation, five-second stream closure, and transport separation

Grant/session/global revocation refuses new dispatch immediately at both command authorization and final
admission. Every affected output stream closes within five seconds under a controlled clock. The global kill
switch survives restart, disables grant mint/renewal and adapter admission, and does not disable ordinary
Fleet, Ticket, or Inbox operation. SSE stays output-only; reconnect, cursor, terminal content, and any
WebSocket or writable bridge cannot dispatch input or replace the durable command path.

- `test_console_revocation_refuses_dispatch_immediately_and_closes_stream_within_five_seconds`
- `test_console_kill_switch_persists_restart_and_disables_console_admission_only`
- `test_console_sse_reconnect_cursor_and_output_content_cannot_dispatch_or_rebind_input`

## Prior CSO rounds against current main

The three earlier verdicts remain valid as specification judgments. No current-main change weakens their
accepted candidate language. Current main also does not implement those judgments, so none of the rounds can
be cited as deployed proof.

| Round | Exact reviewed object | Current-main finding |
|---|---|---|
| Initial boundary adjudication | `61fd730fc220b2125007e46cd521cf4aa4bfc491`, SHA-256 `dab11acfd5b5ebf7618ed198fcf242ae25f0b03f34c462bea6bbbd8b85f0ce22` | Its twelve conditions remain mandatory. The final candidate retains the grant, CAS, audit, custody, closed-input, output, SSE, direct-path, containment, chat, and activation constraints. It was explicitly non-build-activating. |
| Five-condition fold | `e4c28ba67e578bf8241aad05f01fe8f781024b46`, SHA-256 `d58f4eeabb3914305ed41ea70a7a4d2b8fc4e21edd15009f7f49d957a8fbfbfc` | Sole issuer, type-grant bounds, final CAS, truthful byte-vector audit, and restricted input custody remain present in the final candidate. No implemented current-main contract or proof exercises them. |
| Phase-1 Q4–Q8 verdict | `ddb760e2751b84b2824eb620c5bdd0356c79b291`, SHA-256 `dc1dee344c608f4235d7fc4454eed6f11b60cd03b535ddbcd03f510755ef117c` | Restricted output custody, exact allowlist fence, private/direct-path proof, bounded SSE, and containment remain present. The verdict cleared only the CSO condition for the canonical process to activate viewer tickets; it did not approve shipping or deployment. |

Three assumptions must be stated more narrowly now:

1. **“Phase 1 is live” is not a security-proof statement.** Current main's terminal surface was introduced
   before the three rounds; its terminal component, tmux bridge, and closed read-command grammar remain
   unchanged since `abd2f935189de359d2b22d302377f3d12e9c10a3`. It reads tmux directly on the server,
   polls through page refresh, and is deliberately labelled read-only. It has no `ConsoleViewGrant`,
   `ConsoleTypeGrant`, `console_session_allowed`, console custody reader, or console input contract.
2. **The dogfood server is not the product auth boundary.** D41–D45 keep `apps/ctower-ui` separate and
   non-product; its browser receives no product session or authority. `SPEC.md` and the roadmap reserve the
   product browser for I2.4 after full normative I1 exit and require it to consume `CT-I1-013`.
3. **The console proposal is not canonical current-main scope.** The exact candidate is still on draft PR
   #373 and says it is subordinate to `SPEC.md`. This Q3 artifact resolves the input security question; it
   does not silently merge the candidate, activate a stable CT ticket, satisfy its Phase-1 production
   prerequisite, or convert the existing reader into evidence.

These are weakened operational assumptions, not reasons to weaken the controls. CT-C01 makes them explicit
predecessors and forbids a compatibility attachment to the existing direct reader.

## Ceremony design and operator boundary

The approved full-frame compare board at `bc822f5f62eedbce6e20304b863a63ae6f120082` shows the required
read-only, ceremony, granted, expired, and revoked states. The ceremony names the exact action and text,
requested/planned byte counts, digest, incarnation, runner epoch, assignment sequence, reauthentication age,
60-second grant, and separate paste/submit actions. Expiry locks injection without discarding the draft;
revocation records the fact and five-second closure state; adapter success is shown only as injected and
unacknowledged until the harness proves ACK.

The operator acknowledgement recorded on 2026-08-10 approves that terminal-console design and allows the
typing phase to enter its governed sequence. It does not waive the CSO controls, canonical source order,
stable-ticket/dependency gates, independent design review, verification, or deployment evidence.

## Final disposition

**CLEARED-WITH-CONTROLS.** No specification amendment is required to make the narrow `paste_text`/`submit`
boundary defensible: the exact candidate already contains the necessary grant, audit, custody, fencing,
transport, and containment architecture, and this Q3 verdict closes the initial input vocabulary. The build
must treat CT-C01 through CT-C08 and every named test as mandatory acceptance. A changed action vocabulary,
transport authority, direct terminal path, grant binding, byte-custody policy, final-admission rule, or
five-second revocation contract invalidates this verdict and requires a new exact-candidate CSO round.

SIGNED-OFF

- seat: `cso`
- crew: `cso-q3-typing`
- model: `gpt-5.6-sol` at maximum reasoning effort
- claim: The exact Q3 typed-input security shape is cleared only with CT-C01 through CT-C08 and their named tests.
- stood-under: Current main `7d6827ff9887cee4ae8a917b53aabfefe677804a`, candidate SHA-256 `dc1dee344c608f4235d7fc4454eed6f11b60cd03b535ddbcd03f510755ef117c`, approved design `bc822f5f62eedbce6e20304b863a63ae6f120082`, and the three prior CSO records.
- if-this-breaks: Activate the persistent console kill switch, revoke grants and sessions, quarantine the affected runner, preserve audit/custody objects, open an incident, and require a fresh exact-boundary CSO verdict before re-enabling typing.

Security review reduces known risk; it is not a guarantee of security. This verdict is valid only for the
exact reviewed boundary and only while all mandatory controls remain enforced and evidenced.
