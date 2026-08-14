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

`PRESENT` means every selector named in the cell existed, collected, ran, passed, was not skipped, and is
inside a required suite in `tools/checks/expected-suites.toml`. `GAP` means no test met that layer's bar;
each missing cell has one issue.

## Matrix

| Shipped feature | Unit | Integration | E2E driving the real tower |
|---|---|---|---|
| Chat send-box | **PRESENT** (`repository-policy`): `tests/repository/test_inbox_send_ui.py::InboxSendTransportTests::test_the_command_carries_only_text_thread_and_a_server_read_recipient`; `tests/repository/test_inbox_send_ui.py::InboxSendDurabilityTests::test_a_non_accepted_answer_is_not_read_as_a_sent_message` | **PRESENT** (`dogfood-inbox-controls`): `tests/dogfood/test_inbox_controls_render.py::InboxSurfaceRenderTests::test_a_typed_message_appears_in_the_thread_without_a_reload`; `tests/dogfood/test_inbox_controls_render.py::InboxSurfaceRenderTests::test_a_non_accepted_answer_is_never_rendered_as_a_sent_message` | **GAP [#440](https://github.com/simjak/ctower/issues/440).** The browser tests use a stub Record source and explicitly never address a running ctower instance. |
| Chat compose (new thread) | **PRESENT** (`repository-policy`): `tests/repository/test_inbox_compose_ui.py::InboxComposeTransportTests::test_the_command_carries_only_the_message_and_a_server_listed_seat`; `tests/repository/test_inbox_compose_ui.py::InboxComposeTransportTests::test_a_seat_the_record_does_not_list_reaches_no_boundary_at_all`; `tests/repository/test_inbox_compose_ui.py::InboxComposeDurabilityTests::test_a_non_accepted_answer_is_not_read_as_a_started_thread` | **PRESENT** (`dogfood-inbox-controls`): `tests/dogfood/test_inbox_controls_render.py::InboxComposeRenderTests::test_composing_starts_the_thread_in_the_same_document`; `tests/dogfood/test_inbox_controls_render.py::InboxComposeRenderTests::test_composing_twice_never_opens_a_second_thread`; and (`native-inbox-acceptance`, real PostgreSQL) `tests/acceptance/increment-1/test_inbox_compose.py::test_the_addressable_seats_are_the_ones_a_new_thread_can_be_opened_to`; `tests/acceptance/increment-1/test_inbox_compose.py::test_the_offered_addresses_are_exactly_the_ones_the_command_accepts`; `tests/acceptance/increment-1/test_inbox_compose.py::test_composing_twice_to_one_seat_stays_one_pair_grouped_thread` | **GAP [#458](https://github.com/simjak/ctower/issues/458).** The browser tests use a stub Record source and the real-PostgreSQL tests use an in-process API; neither addresses a running ctower instance. The operator round trip #458 defines — compose to `director`, the message reaches that session, the reply mirrors back — is the E2E, and its delivery half is not built yet. |
| Terminal read | **PRESENT** (`repository-policy`): `tests/repository/test_inspection_grammar.py::InspectionGrammarCoverageTests::test_tmux_capture_is_bounded_and_never_writes_to_a_pane`; `tests/repository/test_surface_semantics.py::ChatStreamTests::test_status_lines_do_not_become_turns` | **GAP [#441](https://github.com/simjak/ctower/issues/441).** No test joins the production adapter and render path to a real tmux pane. | **GAP [#442](https://github.com/simjak/ctower/issues/442).** No running-instance flow opens a live crew pane and observes its output. |
| Routines | **PRESENT** (`runtime-routine-module`): `tests/modules/runtime/test_schedule.py::test_catch_up_is_bounded_and_keeps_the_latest_due_fire` | **PRESENT** (`operations-acceptance`): `tests/acceptance/increment-1/test_operations.py::test_routine_due_transaction_has_canonical_lineage_and_acceptance_gated_job` | **PRESENT** (`routine-occurrence-e2e`): `tests/acceptance/increment-1/test_routine_occurrence_e2e.py::test_running_worker_records_one_due_routine_across_duplicate_scan_and_restart` drives the installed worker's production tick boundary and API over disposable real PostgreSQL, then binds the canonical occurrence/effect and restart proof to the exercised `ctower.beat.health@1` revision without constraining the authored Routine inventory size. Closes [#443](https://github.com/simjak/ctower/issues/443). |
| Dream pipeline | **PRESENT** (`dream-dispatch-contracts`): `tests/contracts/runtime/test_dream_dispatch_contract.py::test_four_nightly_dream_packs_carry_the_exact_effect_facts` | **PRESENT** (`dream-dispatch-acceptance`): `tests/acceptance/increment-1/test_dream_dispatch_effect.py::test_nightly_dream_dispatch_stage_walk` | **GAP [#444](https://github.com/simjak/ctower/issues/444).** No installed worker emits, binds, consumes, and records custody for a real due dream effect. |
| Request capture | **PRESENT** (`request-contracts`): `tests/contracts/requests/test_request_contract.py::test_request_http_surface_is_strict_generated_and_phase_one_only` | **PRESENT** (`request-acceptance`): `tests/acceptance/increment-1/test_requests.py::test_request_capture_ack_replay_and_authoritative_list` | **GAP [#445](https://github.com/simjak/ctower/issues/445).** No Request is captured and read back through a supported running instance. |
| Agreements/Rulings ledger | **PRESENT** (`ruling-contracts`): `tests/contracts/rulings/test_ruling_contract.py::test_ruling_http_surface_is_strict_generated_and_has_no_claimed_identity` | **PRESENT** (`ruling-acceptance`): `tests/acceptance/increment-1/test_rulings.py::test_ruling_is_byte_exact_immutable_citable_and_superseded_by_a_new_fact` | **GAP [#446](https://github.com/simjak/ctower/issues/446).** No Ruling is appended and read byte-exact through a supported running instance. |
| Request digest | **PRESENT** (`morning-digest-contracts`): `tests/contracts/digest/test_morning_digest_contract.py::test_morning_digest_is_one_strict_read_only_generated_surface` | **PRESENT** (`morning-digest-acceptance`): `tests/acceptance/increment-1/test_morning_digest.py::test_real_morning_digest_composes_record_derived_briefs_and_links` | **GAP [#447](https://github.com/simjak/ctower/issues/447).** No installed instance renders and delivers the real operator digest. |
| Request decision briefs | **PRESENT** (`decision-brief-contracts`): `tests/contracts/decision_briefs/test_decision_brief_contract.py::test_decision_brief_is_a_strict_read_shape_with_no_caller_fact_input` | **PRESENT** (`decision-brief-acceptance`): `tests/acceptance/increment-1/test_decision_briefs.py::test_decision_request_renders_complete_record_derived_brief_and_ignores_extras` | **GAP [#448](https://github.com/simjak/ctower/issues/448).** No supported running-instance flow renders, answers, and closes a decision brief. |
| Request-maintenance proposals | **PRESENT** (`request-proposal-contracts`, `request-proposal-projections`): strict append/decision/list/review/digest schemas and deterministic 0/1/20/21/many ranking tests | **PRESENT** (`request-proposal-acceptance`, real PostgreSQL): `tests/acceptance/increment-1/test_request_maintenance_proposals.py` proves separation, evidence/quote checks, operator authority, immutable rejection, all ambiguity kinds, similarity preservation, and confirm-time refusal | **GAP.** The approved I1 surface is generated API/protected CLI; no supported installed-instance transcript drives the complete proposal-to-command flow. |
| GitLab standing integration | **PRESENT** (`gitlab-integration-contracts`): `tests/contracts/integrations/test_gitlab_issue_sync_contract.py::test_gitlab_issue_sync_payloads_are_strict_and_typed` | **PRESENT** (`connector-framework-acceptance`): `tests/acceptance/increment-1/test_connector_gitlab_integration.py::test_gitlab_issue_roundtrip_preserves_one_custody_chain_and_proof_gated_close` | **GAP [#449](https://github.com/simjak/ctower/issues/449).** Provider fixtures do not prove the installed registration, secret reference, egress, polling, or real provider outcome. |
| Notification mirror | **PRESENT** (`native-inbox-modules`): `tests/modules/inbox/test_ambiguous_commit_recovery.py::test_notification_replays_through_recover_ambiguous_commit` | **PRESENT** (`notification-transport-acceptance`): `tests/acceptance/increment-1/test_notify_bridge.py::test_notification_ingest_is_idempotent_and_groups_an_unordered_seat_pair` | **GAP [#450](https://github.com/simjak/ctower/issues/450).** No configured Mission Control rail drives a notification into the installed instance and reads back the pair-grouped outcome. |
| Promotion control | **PRESENT** (`repository-policy`): `tests/repository/test_inbox_promotion_ui.py::InboxPromotionTransportTests::test_promotion_posts_only_the_optional_target_and_surfaces_the_problem_detail` | **GAP [#451](https://github.com/simjak/ctower/issues/451).** Backend promotion acceptance is not joined to the UI server action; the browser suite explicitly never submits this form. | **GAP [#452](https://github.com/simjak/ctower/issues/452).** No running-instance browser flow submits the control and reads the linked Ticket outcome. |
| Portfolio | **PRESENT** (`repository-policy`): `tests/repository/test_portfolio_projection.py::RenderedCountEqualityTests::test_the_portfolio_ticket_total_equals_every_card`; `tests/repository/test_portfolio_projection.py::ScreenWiringTests::test_the_route_reads_through_the_adapter_seam` | **GAP [#453](https://github.com/simjak/ctower/issues/453).** Fixture projection tests are not joined to real Board and Inbox APIs; the separate PostgreSQL board test is not a portfolio-surface test or an activated suite. | **GAP [#454](https://github.com/simjak/ctower/issues/454).** No running-instance navigation proves real project rows, totals, escalations, comms attribution, or unavailable-source truth. |
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
