"""Construction contract for complete PostgreSQL adoption measurement."""

from __future__ import annotations

from pathlib import Path

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
LEDGER_SOURCE = ROOT / "packages/ctower-kernel/src/ctower_kernel/record/_migration_ledger_sql.py"


def test_catalog_denominator_and_property_records_cover_cso_classes() -> None:
    source = LEDGER_SOURCE.read_text(encoding="utf-8")
    for required_catalog in (
        "pg_depend",
        "pg_identify_object_as_address",
        "user_schemas",
        "pg_policy",
        "reloptions",
        "pg_am",
        "pg_tablespace",
        "pg_inherits",
        "pg_get_partkeydef",
        "pg_foreign_table",
        "pg_range",
        "pg_statistic_ext",
        "pg_description",
        "pg_seclabel",
        "pg_publication_rel",
        "pg_publication_namespace",
        "constraint-trigger",
        "trigger.tgisinternal",
        "trigger.tgconstraint",
        "trigger.tgfoid",
        "trigger.tgtype",
        "trigger.tgenabled",
    ):
        assert required_catalog in source
    assert "type.typtype IN ('c', 'd', 'e', 'm', 'r')" in source


def test_internal_constraint_trigger_state_uses_stable_descriptors() -> None:
    source = LEDGER_SOURCE.read_text(encoding="utf-8")
    query = source.split("SELECT 'constraint-trigger'", maxsplit=1)[1].split('"""', maxsplit=1)[0]

    assert "trigger.tgname" not in query
    assert "trigger.oid" not in query
    assert "pg_identify_object_as_address" in query
    assert "pg_get_function_identity_arguments" in query
    assert "'relation'" in query
    assert "'type', trigger.tgtype" in query
    assert "'enabled', trigger.tgenabled" in query


def test_persisted_configuration_is_measured_by_scope_not_setting_name() -> None:
    source = LEDGER_SOURCE.read_text(encoding="utf-8")

    assert "pg_db_role_setting" in source
    assert "current_database()" in source
    assert "role.rolname LIKE 'ctower" in source
    for setting_name in (
        "session_replication_role",
        "default_transaction_read_only",
        "default_transaction_isolation",
        "synchronous_commit",
    ):
        assert setting_name not in source
