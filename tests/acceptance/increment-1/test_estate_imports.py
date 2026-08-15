"""Acceptance boundary vectors for operator-only estate import commands."""

from __future__ import annotations

import pytest

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
