# Console Q3 typed-input CSO verdict

| Field | Value |
|---|---|
| State | **DISPUTED** — MAX confirmation reopens CT-C01, CT-C02–CT-C05, CT-C07, and CT-C08 |
| MAX confirmation date | 2026-08-11 |
| MAX confirmation model | `gpt-5.6-sol` at maximum reasoning effort |
| MAX current-main base | `f542b872c7a7c9216ac67fdb41425d7ca4b014a9` |
| Original ruling | **CLEARED-WITH-CONTROLS**, 2026-08-10; superseded by this addendum |
| Original current-main base | `7d6827ff9887cee4ae8a917b53aabfefe677804a` |
| Candidate specification | `docs/specs/crew-console.md` at `ddb760e2751b84b2824eb620c5bdd0356c79b291` |
| Candidate SHA-256 | `dc1dee344c608f4235d7fc4454eed6f11b60cd03b535ddbcd03f510755ef117c` |
| Approved ceremony design | `bc822f5f62eedbce6e20304b863a63ae6f120082` |
| Scope | `ConsoleTypeGrant`, `paste_text`, `submit`, and the last trusted boundary before `bin/mux` |

## MAX confirmation addendum — DISPUTED

### Director ruling

**DISPUTED.** The 2026-08-10 clearance is withdrawn. Phase 2 typing must not activate from this verdict,
from issue #437, or from a server-only Phase 1 proof. The exact #373 candidate and this control list require
repair, followed by a fresh exact-candidate CSO verdict.

This confirmation re-read the #373 Q3 contract and all three preceding CSO rounds against current main
`f542b872c7a7c9216ac67fdb41425d7ca4b014a9`. The original verdict file at
`1dd68fcfaf6e55ae9e2af9c79a614eb9c09cd91c` is byte-identical to the file merged by PR #432. Since the
original base, current main adds only that verdict, release metadata, and the testing coverage matrix; it
does not add a canonical console contract or deployed proof and does not cure the gaps below.

### Re-derived abuse classes

| Abuse class | MAX finding | Required correction |
|---|---|---|
| Grant theft, replay, and cross-grant composition | Per-grant replay and rebinding controls remain sound, but separately valid `paste_text` and `submit` grants can compose one unconfirmed shell line. Actor A may paste `printf safe`, Actor B may paste `; printf unexpected`, and Actor A may then submit. Every grant, digest, rate check, and per-grant CAS can pass while no confirmation covers the effective line. | Authorize an atomic full-line-plus-Enter action whose admission proves a clean input generation, or bind every action and final admission to one exclusive session-input generation/writer lease and the exact expected pending-line state. A different Actor or tab, a grant outside that lease and generation, a stale pending buffer, or intervening input must invalidate the sequence before mux. |
| Digest confusion | Requested, planned, and adapter-dispatch digests cover one physical action, not the effective pending line that `submit` executes. Separately, ordinary-surface raw SHA-256 content digests permit offline recovery of low-entropy commands. | Bind authorization to the complete effective input state. Keep raw content digests behind the audited reader; ordinary surfaces use opaque IDs or a keyed, non-enumerable commitment. Public domain separation alone is insufficient. |
| Fence bypass | Project, assignment, incarnation, target, and runner-epoch fencing are adequate for one action. There is no fence over the mutable session input generation shared by distinct valid grants. | Compare-and-set the session input generation at the last trusted boundary, or remove the split action whose safety depends on that mutable state. |
| Injection past the allowlist | NFC plus exclusion of CR/LF and C0/C1 still admits bidi controls, default-ignorable/invisible characters, and Unicode line/paragraph separators, including U+202E, U+2066, U+200B, U+2028, and U+2029. The approved ceremony renders text in a normal wrapping `<pre>`, so confirmed appearance can differ from dispatched bytes. | Publish an explicit Unicode security policy. Reject dangerous code points or render an escaped code-point/octet preview inside a bidi-isolated ceremony so the operator can verify every dispatched byte. |
| Stream tampering and hostile output | The one-way SSE/input separation remains sound. The original CT-C01 predecessor list omitted the safe terminal renderer and deployed product-viewer proof, so a server-only foundation can be mistaken for sufficient Phase 1 proof. | Require the complete Phase 1 product viewer, hostile-output safe-render corpus, and deployed UI QA as typing predecessors. |
| Revocation after partial input | A successful paste has already placed bytes in the terminal's pending line. Revoking or expiring that paste authority does not remove those bytes, and CT-C08 only refuses a new dispatch. A later valid submit can therefore execute input whose originating authority is no longer live. | Preserve the originating authorization through final line admission, or atomically invalidate the pending input generation on any contributing grant/session/global revocation or expiry and refuse submit until a separately specified secure reset establishes a clean generation. |

### Reopened controls and mandatory repair evidence

#### CT-C01 — complete Phase 1 product proof, not server foundation alone

The exact #373 candidate reviewed here requires
[inert terminal rendering](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L291-L298),
a [dedicated contextual panel](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L391-L407),
[full Phase 1 production verification before Phase 2](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L409-L412),
a [hostile-output safe-render corpus](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L453),
[deployed UI QA](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L466-L477),
and an [explicit safe-render policy](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L487-L505).
The original CT-C01 at this file's historical lines 87-94 named grants, allowlisting, custody, SSE, network,
and direct-path proof, but not the renderer or its deployed browser proof.

Issue #437 is a necessary server predecessor, not the complete one. At the inspected in-flight head
`9d8e13463c50a7adccfda44fcfb06b07c275f34e`, its proposed viewer decision explicitly says CT-I1-019 does not
realize the contextual browser panel or safe terminal renderer. That excluded work is mandatory before #437
evidence may participate in a complete Phase 1 production-verification fact. #437 alone must never satisfy
CT-C01.

- `test_console_typing_requires_full_phase1_product_viewer_production_proof`
- `test_console_typing_rejects_server_foundation_without_safe_renderer`
- `test_console_phase1_hostile_output_renderer_and_deployed_ui_qa_precede_typing`

#### CT-C02, CT-C03, and CT-C04 — bind the effective submitted line

The candidate deliberately grants one exact
[`paste_text`](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L178-L183)
or one payload-free
[`submit`](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L194-L212).
Its transaction and final CAS bind only that
[individual action and plan](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L221-L248).
The original controls repeat that split at historical CT-C02 through CT-C04 and the ceremony explicitly
presents paste and submit as separate grants. Aggregate ordering does not cure the exploit: it merely orders
the three individually valid actions shown above.

The repair must choose one complete security semantic. The smallest is an atomic bounded line-plus-Enter
action whose fresh confirmation covers the entire effective line and whose final admission proves or
establishes a clean input generation rather than appending to stale pending text. If separate paste and
submit remain, each distinct grant must bind the same exclusive writer/input-generation lease together with
Actor, browser session, session incarnation, pending input predecessor, resulting pending input, and final
admission; any grant outside that lease and generation, stale state, or intervening input invalidates the
confirmation and injects zero additional bytes.

- `test_console_submit_binds_the_exact_pending_input_generation`
- `test_console_cross_actor_paste_submit_composition_refuses_before_mux`
- `test_console_distinct_grants_compare_and_set_one_session_input_fence`
- `test_console_confirmation_covers_the_complete_effective_submitted_line`

#### CT-C05 — Unicode-safe allowlist and confirmation

The original initial vocabulary and CT-C05 exclude C0/C1 controls but do not decide Unicode bidi,
default-ignorable, zero-width, line-separator, or paragraph-separator handling. NFC preserves the concrete
vectors above. The approved ceremony says it shows exact bytes but renders the value as ordinary preformatted
text (`docs/design/crew-console/compare-board.html:155-172`, `:2260`, `:2515-2523` at the approved design
commit), without a required escaped preview or bidi isolation.

- `test_console_confirmation_escapes_or_refuses_bidi_and_default_ignorables`
- `test_console_paste_refuses_or_visibly_escapes_unicode_line_and_paragraph_separators`
- `test_console_confirmation_codepoint_preview_matches_dispatched_bytes`

#### CT-C07 — raw content digests are restricted data

The candidate promises that only `console_input_audit_reader` can recover exact bytes while
[ordinary surfaces expose digests](https://github.com/simjak/ctower/blob/ddb760e2751b84b2824eb620c5bdd0356c79b291/docs/specs/crew-console.md#L258-L271).
Canonical current rules use lowercase SHA-256 and content-addressed SHA-256 object keys (`SPEC.md:2915`,
`:3244-3252` at the candidate commit).
Anyone who can see an ordinary-surface digest can hash a dictionary of likely inputs such as `pwd` or
`git status` and recover the command without reader authorization or an access fact. Envelope encryption and
distinct data keys do not change that result.

- `test_console_raw_input_content_digests_require_the_audited_reader`
- `test_console_ordinary_surfaces_use_opaque_or_keyed_non_enumerable_references`
- `test_console_low_entropy_command_dictionary_recovery_fails`

#### CT-C08 — revocation invalidates contributed pending input

The original CT-C08 below refuses new dispatch at authorization and final admission, but it does not bind the
validity of an already dispatched paste to the later submit that executes it. Revocation or expiry
of any grant, session, or global authority that contributed to a pending input generation must invalidate
that generation before another submit may be admitted. Because securely clearing an arbitrary terminal
buffer is not specified, the fail-closed result is zero execution and refusal until a separately specified,
CSO-reviewed reset establishes a clean generation. An atomic line-plus-Enter action avoids this residual.

- `test_console_revocation_between_paste_and_submit_invalidates_pending_input_generation`
- `test_console_expired_paste_authority_cannot_be_executed_by_a_later_submit_grant`
- `test_console_revoked_pending_input_refuses_until_secure_clean_generation_reset`

CT-C06's exact target/epoch fence remains confirmed. CT-C08's five-second output-stream closure and
transport separation also remain necessary and sound; its pending-input revocation semantic is insufficient.
The per-action parts of CT-C02 through CT-C04 remain necessary as well. Reopening a control means it is
insufficient, not that replay, canonicalization, final CAS, or transport separation may be removed.

### Prior-round and phase-boundary recheck

All three earlier CSO records remain mandatory specification judgments on current main, but none is deployed
proof. The initial round's Condition 6 required a Unicode-boundary corpus and Condition 7 required safe
rendering. The five-condition fold correctly incorporated its assigned grant/CAS/audit/custody subset. The
Q4-Q8 round correctly made safe output rendering a Phase 1 requirement. Those records therefore support,
rather than waive, this dispute: the Q3 control list failed to carry two earlier requirements into its own
typing predecessor and allowlist evidence, and it did not analyze cross-grant terminal-state composition,
digest enumeration, or revocation and expiry after partial input.

No implementation or compatibility fallback is authorized by this addendum. Repair the subordinate #373
proposal and the CSO control list through the canonical process, preserve issue #437 as server-foundation
only, and request a fresh MAX exact-candidate verdict before any typed-input build or deployment proceeds.

## Original 2026-08-10 verdict at one glance (superseded)

The proposed typed-command boundary is **CLEARED-WITH-CONTROLS**. It has the right security shape: the
browser submits one strict durable command; only the control plane can mint a short-lived grant; the grant
binds one canonical action; and a final authenticated, linearizable admission immediately before the mux
call permits at most one injection.

This verdict is not product activation, deployment approval, or evidence that Phase 1 is implemented on
current main. The candidate console specification remains subordinate to `SPEC.md`; its canonical
incorporation, stable-ticket activation, prerequisite ordering, implementation, and deployed proofs remain
separate gates. In particular, typing MUST NOT attach to the retired terminal-reader path. That historical
reader directly captured tmux through a server-side dogfood source and did not implement the candidate's
OIDC session, `ConsoleViewGrant`, session allowlist, restricted output custody, or SSE boundary.

The build may proceed only by satisfying every mandatory control below. Missing or unknown evidence is a
refusal, not a partial pass.

## Phase-1 prerequisite update — 2026-08-11

D56 and CT-I1-021 now canonically activate and implement the complete Phase-1 **viewer server foundation**
on the Console candidate: exact current-session allowances, human-bound one-use view grants, bounded durable
SSE, RESTRICTED per-object output custody, dedicated reader access facts, typed expiry/revocation/fences,
global containment, and private literal-bind proof. The statements below that call Phase 1 unimplemented or
the proposal non-canonical record the state at this verdict's 2026-08-10 signing; D56 supersedes those two
prerequisite assumptions for the viewer server only.

That update does not activate typing. CT-I1-021 contains no `ConsoleTypeGrant`, input route, input custody,
final admission, mux write, or browser UI. Phase 2 must still satisfy CT-C01 through CT-C08 and every named
test in this verdict as one separately activated exact candidate. The retired terminal-reader path remains
outside both proof chains.

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
requires. The historical dogfood tmux capture is not that proof and cannot be adapted into a writable
fallback.

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

1. **“Phase 1 is live” is not a security-proof statement.** The historical terminal surface was introduced
   before the three rounds; its former terminal component, tmux bridge, and closed read-command grammar
   remain described here as provenance, not current implementation. It read tmux directly on the server,
   polled through page refresh, and was deliberately labelled read-only. It had no `ConsoleViewGrant`,
   `ConsoleTypeGrant`, `console_session_allowed`, console custody reader, or console input contract.
2. **The retired dogfood server was not the product auth boundary.** Its old browser received no product
   session or authority, and D75 retires that separate non-product boundary. `SPEC.md` and the roadmap
   reserve the product browser for I2.4 after full normative I1 exit and require it to consume `CT-I1-013`.
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

## Original 2026-08-10 disposition (superseded)

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

## MAX confirmation sign-off

SIGNED-OFF

- seat: `cso`
- crew: `cso-q3-confirm`
- model: `gpt-5.6-sol` at maximum reasoning effort
- claim: The Q3 typing clearance is disputed; CT-C01, CT-C02 through CT-C05, CT-C07, and CT-C08 are reopened on the exact evidence and repairs above.
- stood-under: Current main `f542b872c7a7c9216ac67fdb41425d7ca4b014a9`; original verdict head `1dd68fcfaf6e55ae9e2af9c79a614eb9c09cd91c`; #373 candidate `ddb760e2751b84b2824eb620c5bdd0356c79b291` / SHA-256 `dc1dee344c608f4235d7fc4454eed6f11b60cd03b535ddbcd03f510755ef117c`; approved ceremony `bc822f5f62eedbce6e20304b863a63ae6f120082`; three prior CSO records; issue #437 and its inspected in-flight head.
- if-this-breaks: Keep typing inactive, revoke any typing grants, preserve audit objects, and re-summon the CSO on the repaired exact candidate before re-enabling the boundary.

Security review reduces known risk; it is not a guarantee of security or a substitute for a professional
security assessment.
