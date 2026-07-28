"""Terminal regressions for the generation-3 private-VPS repair lineages."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError

from tools.private_vps.cli import main
from tools.private_vps.compose_policy import verify_compose
from tools.private_vps.evidence import verify_evidence
from tools.private_vps.manifest import FileSnapshot, PacketError, load_model, load_snapshot
from tools.private_vps.models import DeploymentBindings, EvidenceManifest, SchedulerReceipt

__all__: list[str] = []

ROOT = Path(__file__).parents[3]
PACKET = ROOT / "deploy/private-vps/development"
DEPLOYMENT_SCHEMA = ROOT / "contracts/operations/private-vps-deployment.schema.json"
EVIDENCE_SCHEMA = ROOT / "contracts/operations/private-vps-evidence.schema.json"
TRACEABILITY = ROOT / "generated/traceability-index.json"
CHECK_KINDS = (
    "tls_access",
    "database_bootstrap",
    "health_telemetry",
    "upgrade_rollback",
    "worker_restart",
    "host_reboot",
    "restore_report",
    "clean_install",
    "legacy_baseline",
)
START_DAY = date(2026, 7, 20)
SOURCE_REVISION = "711152066a9f21c0ffa092b91515f3339d5751a3"
SOURCE_TREE = "7c8e53c7623935582e6c01b50c4e0cb66710e3c1"
SCHEDULE_REF = "schedule-ref://ctower/i1-daily-development-reference"
PROVENANCE = "self_declared_development_reference"
CLI_FAILURE = 2


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _descriptor(identifier: str, kind: str, path: Path, root: Path, schema: str) -> dict[str, str]:
    return {
        "artifact_id": identifier,
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "sha256": _digest(path),
        "media_type": "application/json",
        "content_schema": schema,
    }


def _check(identifier: str, kind: str, deployment: dict[str, Any]) -> dict[str, object]:
    return {
        "schema": "ctower.private-vps-check/v1",
        "artifact_id": identifier,
        "kind": kind,
        "outcome": "pass",
        "provenance": PROVENANCE,
        "observed_at": f"{START_DAY.isoformat()}T09:00:00Z",
        "source": deployment["source"],
        "control_image": deployment["images"]["control"],
    }


def _occurrence(
    working_day: date,
    index: int,
    deployment: dict[str, Any],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    occurrence_id = f"occurrence.{working_day.isoformat()}"
    scheduled_for = f"{working_day.isoformat()}T08:00:00Z"
    common = {
        "occurrence_id": occurrence_id,
        "schedule_ref": SCHEDULE_REF,
        "scheduled_for": scheduled_for,
        "working_day": working_day.isoformat(),
        "provenance": PROVENANCE,
        "source": deployment["source"],
        "control_image": deployment["images"]["control"],
    }
    result: dict[str, object] = {
        "schema": "ctower.private-vps-synthetic-result/v1",
        **common,
        "outcome": "pass",
    }
    receipt: dict[str, object] = {
        "schema": "ctower.private-vps-scheduler-receipt/v1",
        **common,
        "trigger": "scheduled",
        "origin": "routine_scheduler_reference",
        "manual_command_ref": None,
    }
    manifest_item: dict[str, object] = {
        "occurrence_id": occurrence_id,
        "schedule_ref": SCHEDULE_REF,
        "scheduled_for": scheduled_for,
        "working_day": working_day.isoformat(),
        "trigger": "scheduled",
        "origin": "routine_scheduler_reference",
        "result_artifact_id": f"result.{index}",
        "scheduler_receipt_artifact_id": f"receipt.{index}",
        "manual_command_ref": None,
    }
    return result, receipt, manifest_item


def _evidence_fixture(root: Path) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    deployment_dir = root / "deployment"
    deployment_dir.mkdir(parents=True)
    for name in ("compose.yaml", "Caddyfile", "otel-collector.yaml"):
        shutil.copyfile(PACKET / name, deployment_dir / name)
    deployment = json.loads((PACKET / "bindings.example.json").read_text())
    deployment_path = deployment_dir / "bindings.json"
    _write(deployment_path, deployment)
    artifacts = [
        _descriptor(
            "artifact.deployment-contract-validation",
            "deployment_contract_validation",
            deployment_path,
            root,
            "ctower.private-vps-deployment/v1",
        )
    ]
    artifact_dir = root / "artifacts"
    for kind in CHECK_KINDS:
        identifier = f"artifact.{kind}"
        path = artifact_dir / f"{kind}.json"
        _write(path, _check(identifier, kind, deployment))
        artifacts.append(_descriptor(identifier, kind, path, root, "ctower.private-vps-check/v1"))
    occurrences = _add_occurrences(root, artifacts, deployment)
    manifest = _manifest(deployment, artifacts, occurrences)
    manifest_path = root / "manifest.json"
    _write(manifest_path, manifest)
    return manifest_path, manifest, deployment_path, deployment


def _manifest(
    deployment: dict[str, Any],
    artifacts: list[dict[str, str]],
    occurrences: list[dict[str, object]],
) -> dict[str, Any]:
    return {
        "schema": "ctower.private-vps-evidence/v1",
        "evidence_id": "evidence.private-vps.development",
        "claim": "development_rehearsal",
        "assurance": "development",
        "durability_policy": "pending_only",
        "object_adapter": "local_encrypted_filesystem",
        "key_adapter": "local_file",
        "provenance": PROVENANCE,
        "schedule_ref": SCHEDULE_REF,
        "calendar": "weekday_mon_fri_utc",
        "window_start": START_DAY.isoformat(),
        "window_end": (START_DAY + timedelta(days=4)).isoformat(),
        "deployment_manifest_artifact_id": "artifact.deployment-contract-validation",
        "bound_inputs": {
            "source": deployment["source"],
            "control_image": deployment["images"]["control"],
            "configuration": deployment["configuration"],
        },
        "artifacts": artifacts,
        "occurrences": occurrences,
    }


def _add_occurrences(
    root: Path,
    artifacts: list[dict[str, str]],
    deployment: dict[str, Any],
) -> list[dict[str, object]]:
    occurrences: list[dict[str, object]] = []
    for index in range(5):
        result, receipt, manifest_item = _occurrence(
            START_DAY + timedelta(days=index),
            index,
            deployment,
        )
        result_path = root / "artifacts" / f"result-{index}.json"
        receipt_path = root / "artifacts" / f"receipt-{index}.json"
        _write(result_path, result)
        _write(receipt_path, receipt)
        artifacts.append(
            _descriptor(
                f"result.{index}",
                "synthetic_occurrence",
                result_path,
                root,
                "ctower.private-vps-synthetic-result/v1",
            )
        )
        artifacts.append(
            _descriptor(
                f"receipt.{index}",
                "scheduler_receipt",
                receipt_path,
                root,
                "ctower.private-vps-scheduler-receipt/v1",
            )
        )
        occurrences.append(manifest_item)
    return occurrences


def _refresh_deployment(
    manifest_path: Path,
    manifest: dict[str, Any],
    deployment_path: Path,
    deployment: dict[str, Any],
) -> None:
    configuration = deployment["configuration"]
    for key, name in (
        ("compose", "compose.yaml"),
        ("caddyfile", "Caddyfile"),
        ("otel_collector", "otel-collector.yaml"),
    ):
        configuration[key]["sha256"] = _digest(deployment_path.parent / name)
    _write(deployment_path, deployment)
    manifest["bound_inputs"]["configuration"] = configuration
    manifest["artifacts"][0]["sha256"] = _digest(deployment_path)
    _write(manifest_path, manifest)


@pytest.mark.parametrize(
    ("counterexample", "expected_code"),
    [
        ("root_worker", "identity_changed"),
        ("role_admin_dsn", "reference_path_changed"),
    ],
)
def test_evidence_entry_invokes_shared_deployment_authority(
    tmp_path: Path,
    counterexample: str,
    expected_code: str,
) -> None:
    manifest_path, manifest, deployment_path, deployment = _evidence_fixture(tmp_path)
    compose_path = deployment_path.parent / "compose.yaml"
    compose = compose_path.read_text()
    if counterexample == "root_worker":
        deployment["workload_identities"]["worker"]["uid"] = 0
        compose = compose.replace('user: "10002:10001"', 'user: "0:10001"')
    else:
        deployment["database"]["worker_dsn"] = deployment["database"]["role_admin_dsn"]
        compose = compose.replace("worker-dsn", "role-admin-dsn")
    compose_path.write_text(compose)
    _refresh_deployment(manifest_path, manifest, deployment_path, deployment)

    with pytest.raises(PacketError, match=expected_code):
        verify_evidence(manifest_path, "development_rehearsal")


@pytest.mark.parametrize("name", ["Caddyfile", "otel-collector.yaml"])
def test_command_consumed_configuration_cannot_self_rebind(tmp_path: Path, name: str) -> None:
    manifest_path, manifest, deployment_path, deployment = _evidence_fixture(tmp_path)
    path = deployment_path.parent / name
    path.write_text(path.read_text() + "\n# caller rewrite\n")
    _refresh_deployment(manifest_path, manifest, deployment_path, deployment)

    with pytest.raises(PacketError, match="effective_configuration_changed"):
        verify_evidence(manifest_path, "development_rehearsal")


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("workload_identities", "api", "uid"), 10001.0, "accept"),
        (("workload_identities", "api", "uid"), True, "reject"),
        (("workload_identities", "api", "uid"), -1, "reject"),
        (("workload_identities", "api", "uid"), 65536, "reject"),
        (("failure_domain_count",), 1.0, "accept"),
        (("failure_domain_count",), True, "reject"),
        (("images", "postgres_major"), 17.0, "accept"),
        (("tls", "certificate", "group_id"), 10001.0, "accept"),
    ],
)
def test_schema_and_runtime_share_the_mathematical_integer_language(
    path: tuple[str, ...],
    value: object,
    expected: str,
) -> None:
    raw = json.loads((PACKET / "bindings.example.json").read_text())
    target = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    schema = json.loads(DEPLOYMENT_SCHEMA.read_text())
    schema_valid = Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(raw)
    runtime_valid = _model_valid(DeploymentBindings, raw)

    assert schema_valid == runtime_valid == (expected == "accept")


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-07-20T08:00:00Z", "accept"),
        ("2026-07-20T08:00:00.123456+14:00", "accept"),
        ("2000-02-29T08:00:00Z", "accept"),
        ("2024-02-29T08:00:00Z", "accept"),
        ("0001-01-01T00:00:00Z", "accept"),
        ("9999-12-31T23:59:59-23:59", "accept"),
        ("2026-07-20T08:00:60Z", "reject"),
        ("2026-07-20T08:00:00", "reject"),
        ("2026-07-20t08:00:00z", "reject"),
        ("2026-02-30T08:00:00Z", "reject"),
        ("1900-02-29T08:00:00Z", "reject"),
        ("2026-02-29T08:00:00Z", "reject"),
        ("2026-07-20T24:00:00Z", "reject"),
        ("2026-07-20T08:00:00.1234567Z", "reject"),
        ("2026-07-20T08:00:00+24:00", "reject"),
    ],
)
def test_schema_and_runtime_share_one_explicit_timestamp_language(
    timestamp: str,
    expected: str,
) -> None:
    raw = _receipt(timestamp)
    schema = json.loads(EVIDENCE_SCHEMA.read_text())
    receipt_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/schedulerReceipt",
    }
    schema_valid = Draft202012Validator(
        receipt_schema,
        format_checker=FormatChecker(),
    ).is_valid(raw)
    runtime_valid = _model_valid(SchedulerReceipt, raw)

    assert schema_valid == runtime_valid == (expected == "accept")


def test_check_window_uses_the_observation_instant_in_utc(tmp_path: Path) -> None:
    manifest_path, manifest, _, _ = _evidence_fixture(tmp_path)
    descriptor = manifest["artifacts"][1]
    check_path = tmp_path / descriptor["path"]
    check = json.loads(check_path.read_text())
    check["observed_at"] = "2026-07-20T00:30:00+14:00"
    _write(check_path, check)
    descriptor["sha256"] = _digest(check_path)
    _write(manifest_path, manifest)

    with pytest.raises(PacketError, match="check_outside_window"):
        verify_evidence(manifest_path, "development_rehearsal")


def test_deep_small_json_and_yaml_return_typed_limits() -> None:
    deep_json = b'{"nested":' + b"[" * 70 + b"0" + b"]" * 70 + b"}"
    with pytest.raises(PacketError, match="structure_limit_exceeded"):
        load_snapshot(_snapshot(deep_json), EvidenceManifest, field="evidence")

    bindings = load_model(
        PACKET / "bindings.example.json",
        DeploymentBindings,
        field="bindings",
    )
    deep_yaml = b"[" * 70 + b"]" * 70
    with pytest.raises(PacketError, match="structure_limit_exceeded"):
        verify_compose(_snapshot(deep_yaml), bindings)


def test_invalid_cli_arguments_are_typed_and_redacted(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    marker = "CALLER_VALUE_MUST_NOT_APPEAR"
    result = main(
        [
            "evidence-verify",
            "--manifest",
            str(tmp_path / marker),
            "--claim",
            marker,
        ]
    )
    captured = capsys.readouterr()
    decoded = json.loads(captured.out)

    assert result == CLI_FAILURE
    assert decoded["operation"] == "arguments"
    assert decoded["code"] == "invalid_arguments"
    assert marker not in captured.out
    assert marker not in captured.err
    assert "traceback" not in captured.out.lower()


def test_rendered_traceability_is_honestly_nonqualifying() -> None:
    rendered = json.loads(TRACEABILITY.read_text())["references"]
    deployment = "contracts/operations/private-vps-deployment.schema.json"
    evidence = "contracts/operations/private-vps-evidence.schema.json"

    for key in ("AC-ADM-03", "AC-EVD-01", "AC-EVD-04", "INV-18", "INV-19"):
        assert deployment not in rendered.get(key, [])
        assert evidence not in rendered.get(key, [])
    assert deployment in rendered["INV-32"]
    assert evidence in rendered["INV-32"]


def test_packet_docs_distinguish_the_running_shadow_instance() -> None:
    text = (ROOT / "deploy/private-vps/README.md").read_text()
    assert "PostgreSQL 17.10" in text
    assert "development_offhost_ack" in text
    assert "ordinary finalizer" in text
    assert "CP3_D_NOT_PROVEN" in text
    assert "deployment preflight" not in text.lower()


def _receipt(timestamp: str) -> dict[str, object]:
    return {
        "schema": "ctower.private-vps-scheduler-receipt/v1",
        "occurrence_id": "occurrence.2026-07-20",
        "schedule_ref": SCHEDULE_REF,
        "scheduled_for": timestamp,
        "working_day": "2026-07-20",
        "trigger": "scheduled",
        "origin": "routine_scheduler_reference",
        "provenance": PROVENANCE,
        "source": {"sha": SOURCE_REVISION, "tree": SOURCE_TREE},
        "control_image": (
            "example.invalid/ctower/control@sha256:"
            "1111111111111111111111111111111111111111111111111111111111111111"
        ),
        "manual_command_ref": None,
    }


def _model_valid(model: type[BaseModel], raw: dict[str, Any]) -> bool:
    try:
        model.model_validate_json(json.dumps(raw))
    except ValidationError:
        return False
    return True


def _snapshot(data: bytes) -> FileSnapshot:
    return FileSnapshot(
        data=data,
        sha256=f"sha256:{hashlib.sha256(data).hexdigest()}",
        size=len(data),
        owner_uid=0,
        owner_gid=0,
        mode="0400",
    )
