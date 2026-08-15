"""Acceptance boundary vectors for operator-only estate import commands."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from support.postgres import DatabaseFixture

from ctower_kernel.record.postgres import apply_migrations, provision_database_roles
from ctowerctl._parser import parse_arguments

__all__: tuple[str, ...] = ()


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("ctower-inbox", "migration ctower-inbox import"),
        ("ctower-ruling", "migration ctower-ruling import"),
        ("ctower-knowledge", "migration ctower-knowledge import"),
        ("ctower-company-record", "migration ctower-company-record import"),
    ],
)
def test_each_estate_import_is_an_explicit_online_operator_command(
    subject: str, expected: str
) -> None:
    parsed = parse_arguments(
        [
            "migration",
            subject,
            "import",
            "--request-file",
            "estate-batch.json",
            "--command-id",
            "018f0d5e-7b9a-7c01-8000-000000000100",
        ]
    )
    assert parsed.cli_name == expected
    assert parsed.command_id.int > 0


def test_product_migration_engine_applies_and_attests_final_estate_schema(
    database: DatabaseFixture,
) -> None:
    """Fresh product migration apply reaches the estate schema and attests it."""
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)

    manifest_path = Path(__file__).parents[3] / "packages/ctower-kernel/migrations/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT migration_id, result_schema_sha256
            FROM ctower_schema_migrations
            ORDER BY migration_id DESC
            LIMIT 1
            """
        ).fetchone()

    assert row == (
        manifest["adoption_baseline"]["through"],
        manifest["adoption_baseline"]["schema_sha256"],
    )
