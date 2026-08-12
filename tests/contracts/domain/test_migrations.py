"""Ordered migration, privilege, and development-Postgres contracts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "packages/ctower-kernel/migrations"
LIVE_EVIDENCE_FUNCTIONS = 2
_EXPECTED_MIGRATION_PATHS = [
    "0001_roles.sql",
    "0002_ticket_slice.sql",
    "0003_privileges.sql",
    "0004_proof_workflow.sql",
    "0005_proof_verdict_sequence.sql",
    "0006_narrow_head_update_privileges.sql",
    "0007_task_management_facts.sql",
    "0008_board_projection.sql",
    "0009_transactional_record_positions.sql",
    "0010_custody_episode_intervals.sql",
    "0011_persisted_command_refusals.sql",
    "0012_projection_runtime_role.sql",
    "0013_durability_authority.sql",
    "0014_durability_acceptance_finalization.sql",
    "0015_durability_probe_role.sql",
    "0016_durability_finalization_confirmation.sql",
    "0017_durability_probe_schema_boundary.sql",
    "0018_durability_probe_search_path.sql",
    "0019_outbox_routine_health.sql",
    "0020_recovery_roles.sql",
    "0021_object_backup_anchor.sql",
    "0022_restore_inventory.sql",
    "0023_cp3c_privileges.sql",
    "0024_catalog_authority.sql",
    "0025_ticket_comment_event.sql",
    "0026_fixed_operation_attempt_receipts.sql",
    "0027_i17a_cutover_delivery.sql",
    "0028_i17b_importer_isolation.sql",
    "0029_i17b_checkpoint_catalog_kind.sql",
    "0030_i17b_migration_truth_spine.sql",
    "0031_i17b_bounded_truth_spine.sql",
    "0032_thread_first_intake.sql",
    "0033_development_offhost_ack.sql",
    "0034_durability_finalizer_quarantine.sql",
    "0035_board_source_lookup.sql",
    "0036_migration_ledger_role.sql",
    "0037_relax_checkpoint_key_domain.sql",
    "0038_project_delivery_seat_carriage.sql",
    "0039_project_seat_credentials.sql",
    "0040_project_scoped_reads.sql",
    "0041_recorded_work_sessions.sql",
    "0042_checkpoint_delivery_surface.sql",
    "0043_context_set_catalogs.sql",
    "0044_ticket_change_and_label_facts.sql",
    "0045_attention_findings.sql",
    "0046_human_oidc_identity.sql",
    "0047_board_source_index.sql",
    "0048_native_inbox.sql",
    "0049_review_dispatch_effect.sql",
    "0050_knowledge_documents.sql",
    "0051_inbox_delivery_read_facts.sql",
    "0052_knowledge_inbox_event_kinds.sql",
    "0053_dream_dispatch_effect.sql",
    "0054_gitlab_issue_integration.sql",
    "0055_connector_framework.sql",
    "0056_gitlab_trace_views.sql",
    "0057_dream_lane_binding_surface.sql",
    "0058_recoverable_dream_lane_binding.sql",
    "0059_request_authority.sql",
    "0060_rulings_ledger.sql",
    "0061_request_decision_briefs.sql",
    "0062_beat_dispatch_effect.sql",
    "0063_routine_revision_activation.sql",
    "0064_console_output_reader_role.sql",
    "0065_console_view_grants.sql",
    "0066_beat_routine_retirement.sql",
]
_EXPECTED_ADOPTION_BASELINE = {
    "through": "0066_beat_routine_retirement.sql",
    "schema_sha256": ("sha256:da7b6db4d7eb3f0acafe9395d8b76c90886dfcbb5bd4455f07f19c2a7278ee45"),
    "semantic_checks": "ctower.pre-ledger/v1",
    "schema_object_sum256": (
        "sum256:486b5ca6a4abcae26d71b54d91ab18da4ec7bbe2a1e03799bd132d4424477104"
    ),
}
_EXPECTED_LEDGER_ADVANCE_TRANSITIONS = [
    {
        "recorded_through": "0063_routine_revision_activation.sql",
        "recorded_schema_sha256": (
            "sha256:cc7fffb7ce2f4fd55d3f5ed8746e42e8b6679847fc47de40d51262a9dad5423c"
        ),
        "cluster_through": "0064_console_output_reader_role.sql",
        "cluster_sha256": (
            "sha256:2475da971e7d4771ad7763970faa6a4fa318eee93a12461df94b7eaca296d93f"
        ),
        "postgres_major": 17,
        "result_schema_sha256": (
            "sha256:a0aad539aed6b65580daf16ac047856ef48fcbd72b82c396220e44ebe1a85d03"
        ),
        "schema_object_sum256": (
            "sum256:9496a4684ee94bb236c93cbab81d8a6e6cedf10555048665a594d717402e2644"
        ),
        "pending_database_from": "0065_console_view_grants.sql",
        "pending_database_through": "0066_beat_routine_retirement.sql",
    }
]
_DURABILITY_RECOVERY_CONTRACT = {
    "pre_migration_backup": {
        "isolated_recovery": True,
        "live_restore_before_later_acceptance_or_reactivation": True,
    },
    "after_cutover_or_later_acceptance": {
        "requires_durability_aware_build_or_forward_compensation": True,
        "preserve_immutable_facts": [
            "commands",
            "events",
            "acknowledgements",
            "finalizations",
        ],
    },
}


def test_migration_manifest_is_ordered_and_checksum_exact() -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    entries = cast(list[dict[str, str]], manifest["migrations"])
    names = [entry["path"] for entry in entries]

    assert set(manifest) == {
        "adoption_baseline",
        "ledger_advance_transitions",
        "migrations",
        "schema",
    }
    assert manifest["schema"] == "ctower.migrations/v4"
    assert manifest["adoption_baseline"] == _EXPECTED_ADOPTION_BASELINE
    assert manifest["ledger_advance_transitions"] == _EXPECTED_LEDGER_ADVANCE_TRANSITIONS
    assert names == sorted(names)
    assert names == _EXPECTED_MIGRATION_PATHS
    for entry in entries:
        digest = hashlib.sha256((MIGRATIONS / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == f"sha256:{digest}"


def test_every_post_ledger_cluster_migration_has_one_exact_advance_transition() -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    entries = cast(list[dict[str, object]], manifest["migrations"])
    transitions = cast(list[dict[str, object]], manifest["ledger_advance_transitions"])

    post_ledger_cluster_paths = {
        entry["path"]
        for entry in entries
        if entry.get("scope", "database") == "cluster"
        and cast(str, entry["path"]) > "0036_migration_ledger_role.sql"
    }
    transitioned_cluster_paths = [transition["cluster_through"] for transition in transitions]

    assert len(transitioned_cluster_paths) == len(set(transitioned_cluster_paths))
    assert set(transitioned_cluster_paths) == post_ledger_cluster_paths


def test_project_key_migration_backfills_then_removes_its_default() -> None:
    migration = (MIGRATIONS / "0039_project_seat_credentials.sql").read_text(encoding="utf-8")
    add_with_backfill_default = "ADD COLUMN project_key text NOT NULL DEFAULT 'ctower'"
    remove_default = "ALTER COLUMN project_key DROP DEFAULT"

    assert migration.index(add_with_backfill_default) < migration.index(remove_default)


def test_beat_routine_retirement_migration_guards_history_and_old_binary_inserts() -> None:
    migration = (MIGRATIONS / "0066_beat_routine_retirement.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE routine_retirements" in migration
    assert "routine_ref ~ '^ctower\\.beat\\." in migration
    assert "CREATE TRIGGER routine_retirements_immutable" in migration
    assert "BEFORE UPDATE OR DELETE ON routine_retirements" in migration
    assert "CREATE FUNCTION prevent_retired_routine_trigger()" in migration
    assert "BEFORE INSERT OR UPDATE ON routine_triggers" in migration
    assert "RETURN NULL" in migration
    assert "GRANT INSERT, SELECT ON routine_retirements TO ctower_svc" in migration
    assert "GRANT UPDATE" not in "\n".join(
        line for line in migration.splitlines() if "routine_retirements" in line
    )
    assert "GRANT DELETE" not in "\n".join(
        line for line in migration.splitlines() if "routine_retirements" in line
    )


def test_every_migration_declares_compatibility_forward_compensation_and_backup() -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    entries = cast(list[dict[str, object]], manifest["migrations"])

    for entry in entries:
        assert set(entry) in (
            {
                "backup_checkpoint",
                "forward_test",
                "maximum_service_version",
                "minimum_service_version",
                "path",
                "rollback_or_forward_compensation",
                "sha256",
            },
            {
                "backup_checkpoint",
                "forward_test",
                "maximum_service_version",
                "minimum_service_version",
                "path",
                "recovery_contract",
                "rollback_or_forward_compensation",
                "sha256",
            },
            {
                "backup_checkpoint",
                "forward_test",
                "maximum_service_version",
                "minimum_service_version",
                "path",
                "rollback_or_forward_compensation",
                "scope",
                "sha256",
            },
        )
        minimum = cast(str, entry["minimum_service_version"])
        maximum = cast(str, entry["maximum_service_version"])
        version = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
        assert re.fullmatch(version, minimum)
        assert re.fullmatch(version, maximum)
        assert tuple(map(int, minimum.split("."))) <= tuple(map(int, maximum.split(".")))
        forward = cast(str, entry["forward_test"])
        assert forward.startswith("pytest:")
        test_path, node = forward.removeprefix("pytest:").split("::")
        test_file = ROOT / test_path
        assert test_file.is_file()
        assert re.search(rf"^def {re.escape(node)}\(", test_file.read_text(), re.MULTILINE)
        assert cast(str, entry["rollback_or_forward_compensation"]).strip()
        assert cast(str, entry["backup_checkpoint"]).strip()


def test_durability_migration_recovery_separates_backup_restore_from_live_rollback() -> None:
    manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["migrations"]}
    declaration = cast(dict[str, object], entries["0013_durability_authority.sql"])

    assert declaration["recovery_contract"] == _DURABILITY_RECOVERY_CONTRACT


def test_service_and_projection_roles_are_least_privilege() -> None:
    roles = (MIGRATIONS / "0001_roles.sql").read_text(encoding="utf-8")
    grants = (MIGRATIONS / "0003_privileges.sql").read_text(encoding="utf-8")

    assert "ctower_admin" in roles
    assert "ctower_svc" in roles
    assert "ctower_projection" in roles
    assert "GRANT INSERT, SELECT ON events, command_results, outbox TO ctower_svc" in grants
    assert "GRANT UPDATE" not in grants
    assert "GRANT DELETE" not in grants
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO ctower_projection" in grants


def test_verdict_sequence_migration_backfills_from_authoritative_events() -> None:
    migration = (MIGRATIONS / "0005_proof_verdict_sequence.sql").read_text(encoding="utf-8")

    assert "SET proof_sequence = event.sequence" in migration
    assert "event.actor_principal_id = verdict.reviewer_id" in migration
    assert "event.client_command_id = verdict.client_command_id" in migration
    assert "proof_verdicts_sequence_unique" in migration
    assert "ALTER COLUMN proof_sequence SET NOT NULL" in migration


def test_cp2_migrations_separate_authority_from_disposable_projection() -> None:
    facts = (MIGRATIONS / "0007_task_management_facts.sql").read_text(encoding="utf-8")
    projection = (MIGRATIONS / "0008_board_projection.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE admission_facts" in facts
    assert "CREATE TABLE blocker_facts" in facts
    assert "CREATE TABLE ticket_relations" in facts
    assert "workflow_digest" in facts
    assert "CREATE TABLE event_links" in projection
    assert "record_position" in projection
    assert "CREATE TABLE board_projection_rows" in projection
    assert "GRANT INSERT, UPDATE, DELETE ON board_projection_rows" in projection
    assert "TO ctower_projection" in projection
    assert "GRANT INSERT, UPDATE, DELETE ON board_projection_rows TO ctower_svc" not in projection


def test_runtime_and_migrator_use_distinct_one_way_login_roles() -> None:
    roles = (MIGRATIONS / "0001_roles.sql").read_text(encoding="utf-8")

    assert "CREATE ROLE ctower_runtime LOGIN" in roles
    assert "CREATE ROLE ctower_migrator LOGIN" in roles
    assert "GRANT ctower_svc TO ctower_runtime" in roles
    assert "GRANT ctower_admin TO ctower_migrator" in roles
    assert "REVOKE ctower_admin FROM ctower_runtime" in roles
    assert "GRANT ctower_admin TO ctower_runtime" not in roles


def test_projection_runtime_login_can_assume_only_projection_role() -> None:
    role = (MIGRATIONS / "0012_projection_runtime_role.sql").read_text(encoding="utf-8")

    assert "CREATE ROLE ctower_projection_runtime" in role
    assert "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in role
    assert "GRANT ctower_projection TO ctower_projection_runtime" in role
    assert "REVOKE ctower_svc, ctower_admin FROM ctower_projection_runtime" in role


def test_durability_authority_is_additive_immutable_and_least_privilege() -> None:
    migration = (MIGRATIONS / "0013_durability_authority.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE durability_subject_heads" in migration
    assert "CREATE TABLE durability_acknowledgements" in migration
    assert "acceptance_position bigint GENERATED ALWAYS AS IDENTITY" in migration
    assert "CREATE TABLE durability_target_observations" in migration
    assert "GRANT INSERT, SELECT ON durability_acknowledgements TO ctower_svc" in migration
    assert "GRANT UPDATE" not in "\n".join(
        line for line in migration.splitlines() if "durability_acknowledgements" in line
    )
    assert "GRANT DELETE" not in migration


def test_durability_finalization_is_immutable_and_bound_to_one_acknowledgement() -> None:
    migration = (MIGRATIONS / "0014_durability_acceptance_finalization.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE durability_acceptance_finalizations" in migration
    assert "PRIMARY KEY (tenant_id, principal_id, client_command_id)" in migration
    assert "tenant_id, principal_id, client_command_id, acceptance_position" in migration
    assert "durability_acceptance_finalizations_immutable" in migration
    assert "GRANT INSERT, SELECT ON durability_acceptance_finalizations TO ctower_svc" in migration
    assert "GRANT UPDATE" not in migration
    assert "GRANT DELETE" not in migration
    assert migration.count("SECURITY DEFINER") == LIVE_EVIDENCE_FUNCTIONS
    assert migration.count("SET search_path = pg_catalog") == LIVE_EVIDENCE_FUNCTIONS
    assert "WHERE sender.application_name = 'ctower_i1_ack'" in migration
    assert "REVOKE ALL ON FUNCTION durability_primary_live_evidence() FROM PUBLIC" in migration
    assert "REVOKE ALL ON FUNCTION durability_standby_live_evidence() FROM PUBLIC" in migration
    assert "GRANT EXECUTE ON FUNCTION durability_primary_live_evidence() TO ctower_svc" in migration
    assert "GRANT EXECUTE ON FUNCTION durability_standby_live_evidence() TO ctower_svc" in migration
    assert "pg_read_all_stats" not in migration
    assert "pg_monitor" not in migration


def test_durability_probe_role_is_no_login_and_never_granted_to_runtime() -> None:
    migration = (MIGRATIONS / "0015_durability_probe_role.sql").read_text(encoding="utf-8")

    assert "CREATE ROLE ctower_durability_probe" in migration
    assert "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT" in migration
    assert "GRANT pg_read_all_stats TO ctower_durability_probe" in migration
    assert "GRANT ctower_durability_probe TO ctower_admin" in migration
    assert "REVOKE ctower_durability_probe FROM ctower_svc, ctower_runtime" in migration
    assert "GRANT pg_read_all_stats TO ctower_svc" not in migration


def test_finalization_confirmation_is_immutable_and_complete_receipt_bound() -> None:
    migration = (MIGRATIONS / "0016_durability_finalization_confirmation.sql").read_text(
        encoding="utf-8"
    )

    assert "durability_acknowledgements_complete_receipt_unique" in migration
    assert "durability_finalizations_complete_receipt_unique" in migration
    assert "durability_finalizations_complete_acknowledgement" in migration
    assert "CREATE TABLE durability_acceptance_confirmations" in migration
    assert "REFERENCES durability_acceptance_finalizations" in migration
    assert "durability_acceptance_confirmations_immutable" in migration
    assert "GRANT INSERT, SELECT ON durability_acceptance_confirmations TO ctower_svc" in migration
    assert "GRANT UPDATE" not in migration
    assert "GRANT DELETE" not in migration


def test_probe_schema_boundary_keeps_only_narrow_function_execution() -> None:
    migration = (MIGRATIONS / "0017_durability_probe_schema_boundary.sql").read_text(
        encoding="utf-8"
    )

    assert migration.count("REVOKE ALL ON FUNCTION") == LIVE_EVIDENCE_FUNCTIONS
    assert migration.count("GRANT EXECUTE ON FUNCTION") == LIVE_EVIDENCE_FUNCTIONS
    assert "FROM PUBLIC" in migration
    assert "TO ctower_svc" in migration
    assert "GRANT CREATE" not in migration


def test_durability_probe_search_path_puts_temporary_schema_last() -> None:
    migration = (MIGRATIONS / "0018_durability_probe_search_path.sql").read_text(encoding="utf-8")

    assert migration.count("ALTER FUNCTION public.durability_") == LIVE_EVIDENCE_FUNCTIONS
    assert migration.count("SET search_path = pg_catalog, pg_temp") == LIVE_EVIDENCE_FUNCTIONS
    assert "pg_temp, pg_catalog" not in migration


def test_development_composition_uses_postgres_17_without_a_password_value() -> None:
    compose = (ROOT / "deploy/development/compose.yaml").read_text(encoding="utf-8")

    assert "postgres:17" in compose
    assert "POSTGRES_HOST_AUTH_METHOD: trust" in compose
    assert "POSTGRES_PASSWORD" not in compose
