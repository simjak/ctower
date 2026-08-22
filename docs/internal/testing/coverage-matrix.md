# Shipped feature coverage matrix

This page is the evidence-backed retroactive sweep required by
[issue #438](https://github.com/simjak/ctower/issues/438) and operator Decision 11 (2026-08-10): every
feature must name unit, integration, and end-to-end coverage. It reports the repository at commit
`ed257d6`, where every selector named below exists and was run; this page's own rebinding to that
commit was the original audit baseline. Later gap-closing rows name their required selectors directly.
This page does not expand product scope or override `SPEC.md`.

## What the three layers mean

- **Unit** executes one contract, pure module, component, or adapter boundary in isolation. Controlled
  values and mocks are allowed.
- **Integration** joins multiple production boundaries. A disposable real PostgreSQL database, an
  ephemeral real HTTP process, or a real browser against a stub downstream may be used.
- **E2E driving the real tower** uses a supported running ctower instance and asserts the real operator
  outcome. An in-process client or disposable database alone is **not** E2E. The supported disposable
  real-stack form composes TestClient, real PostgreSQL, and the installed worker and asserts the tower's
  own persisted API response. A stub/fixture echo, route-existence assertion, or page load is not E2E.

**REMOVED** means the browser surface and its selectors were intentionally deleted. **DEFERRED** means
product-browser work remains owned by CT-I2-005 / I2.4.

`PRESENT` means every selector named in the cell existed, collected, ran, passed, was not skipped, and is
inside a required suite in `tools/checks/expected-suites.toml`. `GAP` means no test met that layer's bar;
each missing cell has one issue.

## Matrix

| Shipped feature | Unit | Integration | E2E driving the real tower |
|---|---|---|---|
| Chat send-box (retired browser surface) | **REMOVED** — the former browser control and its selectors were deleted with the UI; backend/API coverage remains under Inbox send. | **REMOVED** | **DEFERRED** to CT-I2-005 / I2.4. |
| Chat compose (retired browser surface) | **REMOVED** — the former browser control and its selectors were deleted with the UI; backend/API coverage remains under Inbox send. | **REMOVED** | **DEFERRED** to CT-I2-005 / I2.4. |
| Terminal read (retired browser surface) | **REMOVED** — the former browser reader and its selectors were deleted with the UI; server-side Console proof is tracked separately. | **REMOVED** | **DEFERRED** to CT-I2-005 / I2.4. |
| Routines | **PRESENT** (`runtime-routine-module`): `tests/modules/runtime/test_schedule.py::test_catch_up_is_bounded_and_keeps_the_latest_due_fire` | **PRESENT** (`operations-acceptance`): `tests/acceptance/increment-1/test_operations.py::test_routine_due_transaction_has_canonical_lineage_and_acceptance_gated_job` | **PRESENT** (`routine-occurrence-e2e`): `tests/acceptance/increment-1/test_routine_occurrence_e2e.py::test_running_worker_records_one_due_routine_across_duplicate_scan_and_restart` drives the installed worker's production tick boundary over disposable real PostgreSQL, then binds the canonical occurrence and the one appended work item, plus the duplicate-scan and restart replay proof, to the exercised `ctower.beat.health@1` revision without constraining the authored Routine inventory size. The read half is the record tier, not an HTTP surface: the work-item path publishes no API read. Closes [#443](https://github.com/simjak/ctower/issues/443). |
| Dream pipeline | **PRESENT** (`dream-dispatch-contracts`): `tests/contracts/runtime/test_dream_dispatch_contract.py::test_four_nightly_dream_packs_carry_the_exact_effect_facts` | **PRESENT** (`dream-dispatch-acceptance`): `tests/acceptance/increment-1/test_dream_dispatch_effect.py::test_nightly_dream_dispatch_stage_walk` | **GAP [#444](https://github.com/simjak/ctower/issues/444).** No installed worker emits, binds, consumes, and records custody for a real due dream effect. |
| Request capture | **PRESENT** (`request-contracts`): `tests/contracts/requests/test_request_contract.py::test_request_http_surface_is_strict_generated_and_phase_one_only` | **PRESENT** (`request-acceptance`): `tests/acceptance/increment-1/test_requests.py::test_request_capture_ack_replay_and_authoritative_list` | **GAP [#445](https://github.com/simjak/ctower/issues/445).** No Request is captured and read back through a supported running instance. |
| Agreements/Rulings ledger | **PRESENT** (`ruling-contracts`): `tests/contracts/rulings/test_ruling_contract.py::test_ruling_http_surface_is_strict_generated_and_has_no_claimed_identity` | **PRESENT** (`ruling-acceptance`): `tests/acceptance/increment-1/test_rulings.py::test_ruling_is_byte_exact_immutable_citable_and_superseded_by_a_new_fact` | **GAP [#446](https://github.com/simjak/ctower/issues/446).** No Ruling is appended and read byte-exact through a supported running instance. |
| Request digest | **PRESENT** (`morning-digest-contracts`): `tests/contracts/digest/test_morning_digest_contract.py::test_morning_digest_is_one_strict_read_only_generated_surface` | **PRESENT** (`morning-digest-acceptance`): `tests/acceptance/increment-1/test_morning_digest.py::test_real_morning_digest_composes_record_derived_briefs_and_links` | **GAP [#447](https://github.com/simjak/ctower/issues/447).** No installed instance renders and delivers the real operator digest. |
| Request decision briefs | **PRESENT** (`decision-brief-contracts`): `tests/contracts/decision_briefs/test_decision_brief_contract.py::test_decision_brief_is_a_strict_read_shape_with_no_caller_fact_input` | **PRESENT** (`decision-brief-acceptance`): `tests/acceptance/increment-1/test_decision_briefs.py::test_decision_request_renders_complete_record_derived_brief_and_ignores_extras` | **GAP [#448](https://github.com/simjak/ctower/issues/448).** No supported running-instance flow renders, answers, and closes a decision brief. |
| Request-maintenance proposals | **PRESENT** (`request-proposal-contracts`, `request-proposal-projections`): strict append/decision/list/review/digest schemas and deterministic 0/1/20/21/many ranking tests | **PRESENT** (`request-proposal-acceptance`, real PostgreSQL): `tests/acceptance/increment-1/test_request_maintenance_proposals.py` proves separation, evidence/quote checks, operator authority, immutable rejection, all ambiguity kinds, similarity preservation, and confirm-time refusal | **GAP.** The approved I1 surface is generated API/protected CLI; no supported installed-instance transcript drives the complete proposal-to-command flow. |
| GitLab standing integration | **PRESENT** (`gitlab-integration-contracts`): `tests/contracts/integrations/test_gitlab_issue_sync_contract.py::test_gitlab_issue_sync_payloads_are_strict_and_typed` | **PRESENT** (`connector-framework-acceptance`): `tests/acceptance/increment-1/test_connector_gitlab_integration.py::test_gitlab_issue_roundtrip_preserves_one_custody_chain_and_proof_gated_close` | **GAP [#449](https://github.com/simjak/ctower/issues/449).** Provider fixtures do not prove the installed registration, secret reference, egress, polling, or real provider outcome. |
| Notification mirror | **PRESENT** (`native-inbox-modules`): `tests/modules/inbox/test_ambiguous_commit_recovery.py::test_notification_replays_through_recover_ambiguous_commit` | **PRESENT** (`notification-transport-acceptance`): `tests/acceptance/increment-1/test_notify_bridge.py::test_notification_ingest_is_idempotent_and_groups_an_unordered_seat_pair` | **GAP [#450](https://github.com/simjak/ctower/issues/450).** No configured Mission Control rail drives a notification into the installed instance and reads back the pair-grouped outcome. |
| Promotion control (retired browser surface) | **REMOVED** — the former browser control and its selectors were deleted with the UI; the underlying command remains covered by contract/API tests. | **REMOVED** | **DEFERRED** to CT-I2-005 / I2.4. |
| Portfolio browser surface (retired) | **REMOVED** — the former browser projection and its selectors were deleted with the UI; backend projection coverage remains outside this browser-surface row. | **REMOVED** | **DEFERRED** to CT-I2-005 / I2.4. |
| Inbox send | **PRESENT** (`native-inbox-modules`): `tests/modules/inbox/test_ambiguous_commit_recovery.py::test_send_replays_through_recover_ambiguous_commit` | **PRESENT** (`native-inbox-acceptance`): `tests/acceptance/increment-1/test_inbox.py::test_a_send_is_not_accepted_until_its_durable_receipt_commits` | **GAP [#455](https://github.com/simjak/ctower/issues/455).** No supported running instance sends, reads, acknowledges, and replies between provisioned seats. |
| Connector framework | **PRESENT** (`gitlab-integration-modules`): `tests/modules/integrations/test_connector_boundary_types.py::test_cursor_page_close_and_receipt_values_are_strict_and_serializable` | **PRESENT** (`connector-framework-acceptance`): `tests/acceptance/increment-1/test_connector_registration_isolation.py::test_phase1_two_active_registrations_are_isolated` | **GAP [#456](https://github.com/simjak/ctower/issues/456).** No installed worker proves two active registrations with isolated cursors, leases, retries, and custody. |

## Live audit evidence

The selectors above were run together on `ed257d6` with Python 3.14.3, Node 24.16.0, pnpm 10.20.0,
PostgreSQL test containers, and the frozen Node dependency graph. The clean run collected 37 tests and
reported `37 passed, 0 skipped` — 9 subtests included — in 56.67 seconds. The one warning was Starlette's
existing `httpx` deprecation warning and did not change a verdict.

The browser selectors fail closed unless the frozen Node dependencies are installed, so
`pnpm install --frozen-lockfile --ignore-scripts` is a precondition of the run rather than part of it. No
failed or skipped selector is recorded as `PRESENT`.

The expected-suite manifest independently reports `browser-e2e` as deferred to `CT-I2-005`. At the
original audit baseline the real test tree contained no feature E2E tests meeting the running-instance
bar. The later `routine-occurrence-e2e` suite closes the Routine cell without activating product browser
scope; every other E2E gap remains explicit.

## Gap priority

The remaining issues [#440](https://github.com/simjak/ctower/issues/440) through
[#442](https://github.com/simjak/ctower/issues/442) and [#444](https://github.com/simjak/ctower/issues/444)
through [#456](https://github.com/simjak/ctower/issues/456), plus
[#458](https://github.com/simjak/ctower/issues/458) for the compose round trip, are one-to-one with the 17
missing cells. Daily operator
surfaces and communication paths carry `priority-p1`: chat send, terminal read, dream output, Request
capture, Rulings, digest, briefs, notification mirror, promotion, portfolio, and Inbox send. #458 is the
compose gap and is labelled `enhancement` rather than `tech-debt`, because it is the operator's own
undelivered round trip rather than a retroactively found hole; it ranks with the p1 surfaces.
GitLab-provider and generic connector E2E remain explicit gaps but rank below the controls the operator
touches directly each day.

## Regenerating the audit

1. Read `tools/checks/expected-suites.toml` and enumerate the real test tree; do not infer coverage from
   filenames or prior PR prose.
2. Re-run every selector in each `PRESENT` cell with verbose outcomes. A missing, failed, skipped, or
   no-longer-required selector changes the cell to `GAP` until a qualifying replacement runs.
3. Re-evaluate each integration against the joined-boundary definition and each E2E against a supported
   running instance. Fixture echoes and page loads never move into the E2E column.
4. Add every newly shipped feature as one row with all three named cells and one issue per missing cell.
5. Run `just check` while editing and `just verify` before review.
