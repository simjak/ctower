"""Explicit generated-client routing for restricted online migration commands."""

from __future__ import annotations

import argparse
import inspect
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self, cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectCutoverHealth,
    CtowerProjectEpochRefusalRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    MigrationCorrectionRevision,
    MigrationHealthDigests,
    MigrationRelationCorrection,
    ProjectDeliveryCriteria,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)
from ctowerctl import _migration_commands, _parser, interface
from ctowerctl._output import ExitCode
from ctowerctl._parser import parse_arguments
from ctowerctl.spool import Spool
from modules.migration._import_vectors import (
    ZERO_DIGEST,
    fence_request,
    run_request,
    seed_batch,
)

__all__: tuple[str, ...] = ()

_NOW = datetime(2026, 7, 25, 12, tzinfo=UTC)


def _correction(run_id: UUID, cutover_id: UUID) -> CtowerProjectImportCorrectionRequest:
    return CtowerProjectImportCorrectionRequest(
        schema_id="ctower.ctower-project-import-correction/v1",
        correction_id=uuid4(),
        run_id=run_id,
        cutover_id=cutover_id,
        tenant_key="ctower",
        project_key="ctower",
        correction_kind="relation",
        superseded_revision=MigrationCorrectionRevision(object_id=uuid4(), revision=1),
        expected_current_digest=ZERO_DIGEST,
        replacement=MigrationRelationCorrection(
            kind="relation",
            superseded_relation_active=False,
            replacement_relation_id=None,
        ),
        reason="Reviewed synthetic correction",
        reviewer_id=uuid4(),
    )


def _epoch(run_id: UUID, cutover_id: UUID) -> CtowerProjectEpochRefusalRequest:
    return CtowerProjectEpochRefusalRequest(
        run_id=run_id,
        cutover_id=cutover_id,
        reconciliation_digest=ZERO_DIGEST,
        fence_registry_digest=ZERO_DIGEST,
    )


def _requests() -> tuple[tuple[str, str, BaseModel], ...]:
    run_id, cutover_id = uuid4(), uuid4()
    return (
        ("inventory", "create", run_request("ephemeral", _NOW)),
        (
            "export",
            "export",
            CtowerProjectExportEqualityBindRequest(
                run_id=run_id,
                cutover_id=cutover_id,
                selection_digest=ZERO_DIGEST,
                inventory_a_digest=ZERO_DIGEST,
                inventory_b_digest=ZERO_DIGEST,
                export_digest=ZERO_DIGEST,
                equality_report_digest=ZERO_DIGEST,
                reviewer_key_ref="signing-key-ref:test/reviewer",
                reviewer_key_version=1,
                reviewer_public_key_digest=ZERO_DIGEST,
                result="equal",
                export_a_artifact="{}",
                export_b_artifact="{}",
                export_equality_artifact="{}",
            ),
        ),
        (
            "plan",
            "plan",
            CtowerProjectAliasPlanBindRequest(
                run_id=run_id,
                cutover_id=cutover_id,
                export_equality_digest=ZERO_DIGEST,
                alias_map_digest=ZERO_DIGEST,
                reviewer_key_ref="signing-key-ref:test/reviewer",
                reviewer_key_version=1,
                reviewer_public_key_digest=ZERO_DIGEST,
                attention_required=0,
                alias_map_artifact="{}",
                import_plan_artifact="{}",
                fence_registry_artifact="{}",
                fence_observer_credential_digest=ZERO_DIGEST,
                fence_observer_expires_at=_NOW + timedelta(hours=1),
            ),
        ),
        ("import", "import", seed_batch(run_id, cutover_id, uuid4(), batch_index=0)),
        (
            "reconcile",
            "reconcile",
            CtowerProjectImportFinalizeRequest(
                run_id=run_id,
                cutover_id=cutover_id,
                expected_run_semantic_digest=ZERO_DIGEST,
                reconciliation_artifact="{}",
            ),
        ),
        ("correction append", "correction", _correction(run_id, cutover_id)),
        ("fence observe", "fence", fence_request(sequence=1, previous=None)),
        ("prepare", "prepare", _epoch(run_id, cutover_id)),
        ("commit-development-epoch", "commit", _epoch(run_id, cutover_id)),
    )


@pytest.mark.parametrize(("command", "method", "payload"), _requests())
def test_each_migration_mutation_validates_one_frozen_dto_and_routes_online(
    tmp_path: Path,
    command: str,
    method: str,
    payload: BaseModel,
) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(payload.model_dump_json(by_alias=True), encoding="utf-8")
    command_id = uuid4()
    client = _MigrationClient()

    result = _migration_commands.execute_online(
        argparse.Namespace(
            cli_name=f"migration ctower-project {command}",
            command_id=command_id,
            request_file=request_file,
        ),
        cast(CtowerClient, client),
    )

    assert result == payload
    assert client.calls == [(method, payload, command_id)]


def test_cli_executes_migration_online_without_touching_spool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _MigrationClient()
    command_id = uuid4()
    payload = run_request("ephemeral", _NOW)
    request_file = tmp_path / "run.json"
    request_file.write_text(payload.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(interface, "CtowerClient", lambda *_args, **_kwargs: client)

    def spool_refused(*_args: object, **_kwargs: object) -> Spool:
        raise AssertionError("online-only migration command touched the replay spool")

    monkeypatch.setattr(Spool, "for_origin", spool_refused)
    stdout, stderr = io.StringIO(), io.StringIO()
    code = interface.main(
        [
            "--base-url",
            "https://ctower.example",
            "migration",
            "ctower-project",
            "inventory",
            "--command-id",
            str(command_id),
            "--request-file",
            str(request_file),
        ],
        stdin=io.StringIO("ephemeral-authority\n"),
        stdout=stdout,
        stderr=stderr,
    )

    assert code == int(ExitCode.SUCCESS)
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["project_key"] == "ctower"
    assert client.calls == [("create", payload, command_id)]


def test_parser_exposes_run_correction_fence_and_rejects_untyped_payload(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    run = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "migration",
            "ctower-project",
            "run",
            "get",
            str(run_id),
        ]
    )
    assert run.cli_name == "migration ctower-project run get"
    assert run.run_id == run_id

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"cutover_id":"not-a-run"}', encoding="utf-8")
    with pytest.raises(ValueError):
        _migration_commands.execute_online(
            argparse.Namespace(
                cli_name="migration ctower-project inventory",
                command_id=uuid4(),
                request_file=invalid,
            ),
            cast(CtowerClient, _MigrationClient()),
        )


def test_query_dispatch_and_project_delivery_text_expose_frozen_metadata() -> None:
    client = _MigrationClient()
    verify = argparse.Namespace(cli_name="migration ctower-project verify")
    run = argparse.Namespace(cli_name="migration ctower-project run get", run_id=uuid4())
    delivery = argparse.Namespace(
        cli_name="project delivery query", project_key="ctower", output="text"
    )

    assert isinstance(
        _migration_commands.execute_query(verify, cast(CtowerClient, client)),
        CtowerProjectCutoverHealth,
    )
    assert _migration_commands.execute_query(run, cast(CtowerClient, client)) == client.run_result
    view = cast(
        ProjectDeliveryView,
        _migration_commands.execute_query(delivery, cast(CtowerClient, client)),
    )
    stream = io.StringIO()
    interface._write_result(delivery, view, stream)

    output = stream.getvalue()
    assert "I1.7" in output
    assert "blocked" in output
    assert "5/6" in output
    assert "sources=ctower:CT-I1-007,mission-control:i1.7" in output
    assert "watermark=27/27" in output


def test_project_delivery_parser_and_renderer_accept_a_second_project_fixture() -> None:
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "project",
            "delivery",
            "query",
            "quarterly-close",
        ]
    )
    ledger_view = _ledger_delivery_view()

    assert arguments.project_key == "quarterly-close"
    with pytest.raises(ValueError, match="project_key"):
        parse_arguments(
            [
                "--base-url",
                "https://ctower.example",
                "project",
                "delivery",
                "query",
                "Q3/close",
            ]
        )
    rendered = _migration_commands.delivery_text(ledger_view)
    assert "company=ledger-co project=quarterly-close" in rendered
    assert "CHECKPOINT" in rendered
    assert "CRITERIA" in rendered
    assert "SLOTS" in rendered
    assert "UNRESOLVED" in rendered
    assert "Q3-close.2" in rendered
    assert "2/3" in rendered
    assert "1/3" in rendered
    assert "approval-receipt,archive-proof" in rendered
    assert "ledger:close-run-27,archive:quarter-2026-q3" in rendered
    assert "slot_unfilled:approval-receipt" in rendered
    parser_source = inspect.getsource(_parser._project_parser)
    renderer_source = inspect.getsource(_migration_commands.delivery_text)
    assert 'choices=("ctower",)' not in parser_source
    assert "type=_project_key" in parser_source
    assert not {"ctower", "I1.7", "quarterly-close", "Q3-close.2"}.intersection(renderer_source)

    json_arguments = argparse.Namespace(
        cli_name="project delivery query",
        project_key="quarterly-close",
        output="json",
    )
    json_stream = io.StringIO()
    interface._write_result(json_arguments, ledger_view, json_stream)
    payload = json.loads(json_stream.getvalue())
    assert payload["company_key"] == "ledger-co"
    assert payload["project_key"] == "quarterly-close"
    assert payload["rows"][0]["checkpoint_key"] == "Q3-close.2"
    assert payload["rows"][0]["qualifying_stage_slots_filled"] == 1


def test_unknown_internal_migration_spelling_is_closed(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        _migration_commands.execute_online(
            argparse.Namespace(
                cli_name="migration ctower-project invented",
                command_id=uuid4(),
                request_file=request_file,
            ),
            cast(CtowerClient, _MigrationClient()),
        )


class _MigrationClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, BaseModel, UUID]] = []
        self.run_result = run_request("read", _NOW)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def _mutation(self, name: str, request: BaseModel, command_id: UUID) -> BaseModel:
        self.calls.append((name, request, command_id))
        return request

    def create_ctower_project_import_run(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("create", request, command_id)

    def bind_ctower_project_export_equality(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("export", request, command_id)

    def bind_ctower_project_alias_plan(self, request: BaseModel, *, command_id: UUID) -> BaseModel:
        return self._mutation("plan", request, command_id)

    def apply_ctower_project_import_batch(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("import", request, command_id)

    def finalize_ctower_project_import_run(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("reconcile", request, command_id)

    def append_ctower_project_import_correction(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("correction", request, command_id)

    def report_ctower_project_fence_observation(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("fence", request, command_id)

    def prepare_ctower_project_cutover(self, request: BaseModel, *, command_id: UUID) -> BaseModel:
        return self._mutation("prepare", request, command_id)

    def commit_ctower_project_development_epoch(
        self, request: BaseModel, *, command_id: UUID
    ) -> BaseModel:
        return self._mutation("commit", request, command_id)

    def get_ctower_project_import_run(self, run_id: UUID) -> BaseModel:
        del run_id
        return self.run_result

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
            import_run_id=None,
            migration_digests=MigrationHealthDigests(
                source_selection=None,
                export_equality=None,
                alias_map=None,
                reconciliation=None,
                fence_registry=None,
                fence_observation=None,
            ),
            banner="DEVELOPMENT DOGFOOD — not disaster-safe",
        )

    def get_project_delivery(self, project_key: str) -> ProjectDeliveryView:
        reconciled = _NOW
        return ProjectDeliveryView(
            schema_id="ctower.project-delivery/v1",
            company_key="ctower",
            project_key=project_key,
            source_record_position=27,
            projection_record_position=27,
            reconciled_at=reconciled,
            freshness_due_at=reconciled + timedelta(hours=1),
            projection_semantic_digest=ZERO_DIGEST,
            rebuild_generation=0,
            rows=(
                ProjectDeliveryRow(
                    checkpoint_key="I1.7",
                    checkpoint_label="Development dogfood cutover",
                    headline_state="blocked",
                    underlying_maturity="verified",
                    outcome="reviewed reconstructible engineering work",
                    accountable_owner="operator",
                    criteria=ProjectDeliveryCriteria(proven=5, declared=6),
                    qualifying_stage_slots_filled=1,
                    qualifying_stage_slots_required=2,
                    qualifying_stage_unfilled_or_unknown_slot_keys=("cp3-d-proof",),
                    source_watermark=27,
                    projection_watermark=27,
                    freshness="fresh",
                    confidence="development_degraded",
                    health="CP3_D_NOT_PROVEN",
                    durability="CP3_D_NOT_PROVEN",
                    recovery="EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
                    data_class="RECONSTRUCTIBLE_ONLY",
                    semantic_digest=ZERO_DIGEST,
                    reconciled_at=reconciled,
                    freshness_due_at=reconciled + timedelta(hours=1),
                    rebuild_generation=0,
                    source_ids=("ctower:CT-I1-007", "mission-control:i1.7"),
                    derivation_reasons=("cp3_d_unproven",),
                ),
            ),
        )


def _ledger_delivery_view() -> ProjectDeliveryView:
    return ProjectDeliveryView(
        schema_id="ctower.project-delivery/v1",
        company_key="ledger-co",
        project_key="quarterly-close",
        source_record_position=27,
        projection_record_position=27,
        reconciled_at=_NOW,
        freshness_due_at=_NOW + timedelta(hours=1),
        projection_semantic_digest=ZERO_DIGEST,
        rebuild_generation=1,
        rows=(
            ProjectDeliveryRow(
                checkpoint_key="Q3-close.2",
                checkpoint_label="Quarter close approval",
                headline_state="blocked",
                underlying_maturity="verified",
                outcome="The quarter close is approved and archived",
                accountable_owner="controller",
                criteria=ProjectDeliveryCriteria(proven=2, declared=3),
                qualifying_stage_slots_filled=1,
                qualifying_stage_slots_required=3,
                qualifying_stage_unfilled_or_unknown_slot_keys=(
                    "approval-receipt",
                    "archive-proof",
                ),
                source_watermark=27,
                projection_watermark=27,
                freshness="fresh",
                confidence="STATE_UNKNOWN",
                health="STATE_UNKNOWN",
                durability="STATE_UNKNOWN",
                recovery="STATE_UNKNOWN",
                data_class="STATE_UNKNOWN",
                semantic_digest=ZERO_DIGEST,
                reconciled_at=_NOW,
                freshness_due_at=_NOW + timedelta(hours=1),
                rebuild_generation=1,
                source_ids=("ledger:close-run-27", "archive:quarter-2026-q3"),
                derivation_reasons=(
                    "slot_unfilled:approval-receipt",
                    "slot_unknown:archive-proof",
                    "underlying_maturity:verified",
                ),
            ),
        ),
    )
