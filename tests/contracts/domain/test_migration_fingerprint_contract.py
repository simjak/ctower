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
    ):
        assert required_catalog in source
    assert "type.typtype IN ('c', 'd', 'e', 'm', 'r')" in source
