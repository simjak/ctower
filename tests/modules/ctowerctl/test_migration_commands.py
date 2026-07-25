"""Explicit generated-client routing for I1.7A reads and refusing stubs."""

from __future__ import annotations

import argparse
import io
from typing import Literal, Self, cast
from uuid import UUID, uuid4

import pytest

from ctower_client import CtowerClient
from ctower_client.models import (
    CtowerProjectCutoverHealth,
    CtowerProjectMigrationStubRequest,
    CtowerProjectMigrationStubResult,
    ProjectDeliveryCriteria,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)
from ctowerctl import _migration_commands, interface
from ctowerctl._output import ExitCode
from ctowerctl._parser import parse_arguments
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + ("a" * 64)
type _Phase = Literal[
    "inventory",
    "export",
    "plan",
    "import",
    "reconcile",
    "prepare",
    "commit_development_epoch",
]
_PHASES: tuple[tuple[str, _Phase], ...] = (
    ("inventory", "inventory"),
    ("export", "export"),
    ("plan", "plan"),
    ("import", "import"),
    ("reconcile", "reconcile"),
    ("prepare", "prepare"),
    ("commit-development-epoch", "commit_development_epoch"),
)


@pytest.mark.parametrize(("command", "phase"), _PHASES)
def test_each_migration_stub_calls_one_explicit_generated_method(
    command: str,
    phase: str,
) -> None:
    client = _MigrationClient()
    command_id = uuid4()
    cutover_id = uuid4()
    arguments = argparse.Namespace(
        cli_name=f"migration ctower-project {command}",
        command_id=command_id,
        cutover_id=cutover_id,
        input_digest=_DIGEST,
    )

    result = _migration_commands.execute_online_stub(arguments, cast(CtowerClient, client))

    assert isinstance(result, CtowerProjectMigrationStubResult)
    assert result.phase == phase
    assert client.calls == [(phase, cutover_id, command_id)]


def test_cli_routes_stub_online_without_creating_a_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _MigrationClient()
    command_id = uuid4()
    cutover_id = uuid4()
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "migration",
            "ctower-project",
            "inventory",
            "--command-id",
            str(command_id),
            "--cutover-id",
            str(cutover_id),
            "--input-digest",
            _DIGEST,
        ]
    )
    monkeypatch.setattr(interface, "CtowerClient", lambda *_args, **_kwargs: client)

    def spool_refused(*_args: object, **_kwargs: object) -> Spool:
        raise AssertionError("online-only migration command touched the replay spool")

    monkeypatch.setattr(Spool, "for_origin", spool_refused)
    result, code = interface._execute(arguments, io.StringIO("ephemeral-authority\n"))

    assert code is ExitCode.SUCCESS
    assert cast(CtowerProjectMigrationStubResult, result).phase == "inventory"
    assert client.calls == [("inventory", cutover_id, command_id)]


def test_parser_and_query_dispatch_are_closed_and_digest_strict() -> None:
    verify = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "migration",
            "ctower-project",
            "verify",
        ]
    )
    delivery = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "project",
            "delivery",
            "query",
            "ctower",
            "--output",
            "json",
        ]
    )
    client = _MigrationClient()

    assert isinstance(
        _migration_commands.execute_query(verify, cast(CtowerClient, client)),
        CtowerProjectCutoverHealth,
    )
    assert (
        _migration_commands.execute_query(delivery, cast(CtowerClient, client)).model_dump()[
            "project_key"
        ]
        == "ctower"
    )
    with pytest.raises(ValueError, match="digest"):
        parse_arguments(
            [
                "--base-url",
                "https://ctower.example",
                "migration",
                "ctower-project",
                "plan",
                "--command-id",
                str(uuid4()),
                "--cutover-id",
                str(uuid4()),
                "--input-digest",
                "unbound",
            ]
        )


def test_project_delivery_text_exposes_proof_sources_and_watermarks() -> None:
    view = ProjectDeliveryView(
        schema_id="ctower.project-delivery/v1",
        company_key="ctower",
        project_key="ctower",
        rows=(
            ProjectDeliveryRow(
                checkpoint_key="I1.7",
                checkpoint_label="Development dogfood cutover",
                headline_state="blocked",
                underlying_maturity="verified",
                outcome="reviewed reconstructible engineering work",
                accountable_owner="operator",
                criteria=ProjectDeliveryCriteria(proven=5, declared=6),
                source_watermark=27,
                projection_watermark=27,
                freshness="fresh",
                confidence="development_degraded",
                health="CP3_D_NOT_PROVEN",
                source_ids=("ctower:CT-I1-007", "mission-control:i1.7"),
                derivation_reasons=("cp3_d",),
            ),
        ),
    )
    stream = io.StringIO()

    interface._write_result(
        argparse.Namespace(cli_name="project delivery query", output="text"),
        view,
        stream,
    )

    output = stream.getvalue()
    assert "I1.7" in output
    assert "blocked" in output
    assert "5/6" in output
    assert "reasons=cp3_d" in output
    assert "sources=ctower:CT-I1-007,mission-control:i1.7" in output
    assert "watermark=27/27" in output


def test_migration_dispatch_rejects_unknown_internal_spellings() -> None:
    client = cast(CtowerClient, _MigrationClient())
    request = CtowerProjectMigrationStubRequest(
        cutover_id=uuid4(),
        input_digest=_DIGEST,
    )
    command_id = uuid4()

    with pytest.raises(ValueError, match="source stub"):
        _migration_commands._execute_source_stub(
            "migration ctower-project invented",
            client,
            request,
            command_id,
        )
    with pytest.raises(ValueError, match="cutover stub"):
        _migration_commands._execute_cutover_stub(
            "migration ctower-project invented",
            client,
            request,
            command_id,
        )
    with pytest.raises(ValueError, match=r"I1\.7A query"):
        _migration_commands.execute_query(
            argparse.Namespace(cli_name="migration ctower-project invented"),
            client,
        )


class _MigrationClient:
    def __init__(self) -> None:
        self.calls: list[tuple[_Phase, UUID, UUID]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def inventory_ctower_project_migration(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("inventory", request, command_id)

    def export_ctower_project_migration(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("export", request, command_id)

    def plan_ctower_project_migration(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("plan", request, command_id)

    def import_ctower_project_migration(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("import", request, command_id)

    def reconcile_ctower_project_migration(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("reconcile", request, command_id)

    def prepare_ctower_project_cutover(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("prepare", request, command_id)

    def commit_ctower_project_development_epoch(
        self, request: CtowerProjectMigrationStubRequest, *, command_id: UUID
    ) -> CtowerProjectMigrationStubResult:
        return self._phase("commit_development_epoch", request, command_id)

    def get_ctower_project_cutover_health(self) -> CtowerProjectCutoverHealth:
        return CtowerProjectCutoverHealth(
            schema_id="ctower.ctower-project-cutover-health/v1",
            cutover_id=None,
            authority_mode="legacy_writable",
            phase="not_started",
            writes_enabled=False,
            durability_claim="CP3_D_NOT_PROVEN",
            recovery_claim="EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
            data_class="RECONSTRUCTIBLE_ONLY",
            legacy_writer_fence="not_armed",
            split_brain="clear",
            projection_completeness="current",
            source_watermark=0,
            projection_watermark=0,
            banner="DEVELOPMENT DOGFOOD — not disaster-safe",
        )

    def get_project_delivery(self, project_key: str) -> ProjectDeliveryView:
        return ProjectDeliveryView(
            schema_id="ctower.project-delivery/v1",
            company_key="ctower",
            project_key=project_key,
            rows=(),
        )

    def _phase(
        self,
        phase: _Phase,
        request: CtowerProjectMigrationStubRequest,
        command_id: UUID,
    ) -> CtowerProjectMigrationStubResult:
        self.calls.append((phase, request.cutover_id, command_id))
        return CtowerProjectMigrationStubResult(
            cutover_id=request.cutover_id,
            phase=phase,
            state="deferred_to_i1_7b_or_c",
            detail="Not implemented in I1.7A.",
        )
