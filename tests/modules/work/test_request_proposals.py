"""RED-first real-PostgreSQL boundary for Request-maintenance proposals."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from uuid import UUID

import psycopg
import pytest

from ctower_kernel.record import RecordProblem
from ctower_kernel.work.request_proposals import (
    RequestMaintenanceProposalAppend,
    _relation_shape_refusal,
)
from modules.migration._postgres import Database, isolated_database

__all__: tuple[str, ...] = ()


@pytest.fixture
def proposal_database() -> Iterator[Database]:
    """Use the kernel's real fresh-apply PostgreSQL fixture without skips."""

    yield from isolated_database()


def test_fresh_apply_installs_separate_append_only_proposal_facts(
    proposal_database: Database,
) -> None:
    with psycopg.connect(proposal_database.admin_dsn) as connection:
        tables = connection.execute(
            """
            SELECT to_regclass('public.request_maintenance_proposals'),
                   to_regclass('public.request_maintenance_proposal_evidence'),
                   to_regclass('public.request_maintenance_proposal_decisions')
            """
        ).fetchone()

    assert tables == (
        "request_maintenance_proposals",
        "request_maintenance_proposal_evidence",
        "request_maintenance_proposal_decisions",
    )


def test_partial_and_self_relations_refuse_before_postgresql_constraints() -> None:
    target_id = UUID("00000000-0000-7000-8000-000000000101")
    command = RequestMaintenanceProposalAppend(
        client_command_id=UUID("00000000-0000-7000-8000-000000000102"),
        project_key="ctower",
        kind="keep",
        basis="recorded-evidence",
        target_request_id=target_id,
        target_expected_version=1,
        target_text="Exact Request text.",
        source_record_position=1,
        evidence=(),
    )
    partial = replace(command, related_request_id=target_id)
    self_relation = replace(
        command,
        kind="duplicate",
        related_request_id=target_id,
        related_expected_version=1,
        related_text=command.target_text,
    )
    valid_relation = replace(
        self_relation,
        related_request_id=UUID("00000000-0000-7000-8000-000000000103"),
    )

    assert isinstance(_relation_shape_refusal(partial), RecordProblem)
    assert isinstance(_relation_shape_refusal(self_relation), RecordProblem)
    assert _relation_shape_refusal(valid_relation) is None
