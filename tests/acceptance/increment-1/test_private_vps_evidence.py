"""Adversarial acceptance tests for development-only recurrence evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError

from tools.private_vps.cli import main
from tools.private_vps.evidence import verify_evidence
from tools.private_vps.manifest import (
    MAX_ARTIFACT_BYTES,
    FileSnapshot,
    PacketError,
    load_snapshot,
)
from tools.private_vps.models import (
    EvidenceManifest,
    SchedulerReceipt,
    SyntheticResult,
)

__all__: list[str] = []

ROOT = Path(__file__).parents[3]
PACKET = ROOT / "deploy/private-vps/development"
EVIDENCE_SCHEMA = ROOT / "contracts/operations/private-vps-evidence.schema.json"
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
CONTENT_SCHEMAS = {
    "deployment_preflight": "ctower.private-vps-deployment/v1",
    **dict.fromkeys(CHECK_KINDS, "ctower.private-vps-check/v1"),
    "synthetic_occurrence": "ctower.private-vps-synthetic-result/v1",
    "scheduler_receipt": "ctower.private-vps-scheduler-receipt/v1",
}
SCHEDULE_REF = "schedule-ref://ctower/i1-daily-development-reference"
PROVENANCE = "self_declared_development_reference"
START_DAY = date(2026, 7, 20)
EXPECTED_ARTIFACT_COUNT = 20
EXPECTED_WORKING_DAYS = 5
CLI_FAILURE = 2
FORBIDDEN_MARKER = "FORBIDDEN_" + "INLINE_MATERIAL"


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _descriptor(artifact_id: str, kind: str, path: Path, base: Path) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "path": path.relative_to(base).as_posix(),
        "sha256": _digest(path),
        "media_type": "application/json",
        "content_schema": CONTENT_SCHEMAS[kind],
    }


def _deployment(root: Path) -> tuple[Path, dict[str, Any]]:
    directory = root / "deployment"
    directory.mkdir(parents=True)
    for name in ("compose.yaml", "Caddyfile", "otel-collector.yaml"):
        shutil.copyfile(PACKET / name, directory / name)
    raw = json.loads((PACKET / "bindings.example.json").read_text(encoding="utf-8"))
    path = directory / "bindings.json"
    _write_json(path, raw)
    return path, raw


def _check_payload(
    artifact_id: str,
    kind: str,
    deployment: dict[str, Any],
) -> dict[str, object]:
    return {
        "schema": "ctower.private-vps-check/v1",
        "artifact_id": artifact_id,
        "kind": kind,
        "outcome": "pass",
        "provenance": PROVENANCE,
        "observed_at": f"{START_DAY.isoformat()}T09:00:00Z",
        "source": deployment["source"],
        "control_image": deployment["images"]["control"],
    }


def _occurrence_payloads(
    working_day: date,
    occurrence_id: str,
    deployment: dict[str, Any],
) -> tuple[dict[str, object], dict[str, object]]:
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
    result = {
        "schema": "ctower.private-vps-synthetic-result/v1",
        **common,
        "outcome": "pass",
    }
    receipt = {
        "schema": "ctower.private-vps-scheduler-receipt/v1",
        **common,
        "trigger": "scheduled",
        "origin": "routine_scheduler_reference",
        "manual_command_ref": None,
    }
    return result, receipt


def _artifacts_and_occurrences(
    root: Path,
    deployment_path: Path,
    deployment: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    artifacts = [
        _descriptor(
            "artifact.deployment-preflight",
            "deployment_preflight",
            deployment_path,
            root,
        )
    ]
    artifact_dir = root / "artifacts"
    for kind in CHECK_KINDS:
        artifact_id = f"artifact.{kind}"
        path = artifact_dir / f"{kind}.json"
        _write_json(path, _check_payload(artifact_id, kind, deployment))
        artifacts.append(_descriptor(artifact_id, kind, path, root))
    occurrences: list[dict[str, object]] = []
    for index in range(EXPECTED_WORKING_DAYS):
        working_day = START_DAY + timedelta(days=index)
        occurrence_id = f"occurrence.{working_day.isoformat()}"
        result, receipt = _occurrence_payloads(working_day, occurrence_id, deployment)
        result_path = artifact_dir / f"synthetic-{index}.json"
        receipt_path = artifact_dir / f"receipt-{index}.json"
        _write_json(result_path, result)
        _write_json(receipt_path, receipt)
        result_id = f"synthetic.{index}"
        receipt_id = f"receipt.{index}"
        artifacts.append(_descriptor(result_id, "synthetic_occurrence", result_path, root))
        artifacts.append(_descriptor(receipt_id, "scheduler_receipt", receipt_path, root))
        occurrences.append(
            {
                "occurrence_id": occurrence_id,
                "schedule_ref": SCHEDULE_REF,
                "scheduled_for": f"{working_day.isoformat()}T08:00:00Z",
                "working_day": working_day.isoformat(),
                "trigger": "scheduled",
                "origin": "routine_scheduler_reference",
                "result_artifact_id": result_id,
                "scheduler_receipt_artifact_id": receipt_id,
                "manual_command_ref": None,
            }
        )
    return artifacts, occurrences


def _evidence(root: Path) -> tuple[Path, dict[str, Any]]:
    deployment_path, deployment = _deployment(root)
    artifacts, occurrences = _artifacts_and_occurrences(root, deployment_path, deployment)
    raw = {
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
        "deployment_manifest_artifact_id": "artifact.deployment-preflight",
        "bound_inputs": {
            "source": deployment["source"],
            "control_image": deployment["images"]["control"],
            "configuration": deployment["configuration"],
        },
        "artifacts": artifacts,
        "occurrences": occurrences,
    }
    path = root / "manifest.json"
    _write_json(path, raw)
    return path, raw


def _rewrite(path: Path, raw: dict[str, Any]) -> None:
    _write_json(path, raw)


def _artifact_path(root: Path, raw: dict[str, Any], artifact_id: str) -> Path:
    descriptor = next(item for item in raw["artifacts"] if item["artifact_id"] == artifact_id)
    relative = descriptor["path"]
    assert isinstance(relative, str)
    return root / relative


def _refresh_digest(root: Path, raw: dict[str, Any], artifact_id: str) -> None:
    descriptor = next(item for item in raw["artifacts"] if item["artifact_id"] == artifact_id)
    descriptor["sha256"] = _digest(root / descriptor["path"])


def test_complete_distinct_scheduled_working_days_verify(tmp_path: Path) -> None:
    path, _ = _evidence(tmp_path)

    summary = verify_evidence(path, "development_rehearsal")

    assert summary.artifact_count == EXPECTED_ARTIFACT_COUNT
    assert summary.qualifying_working_days == EXPECTED_WORKING_DAYS


def test_i1_exit_is_structurally_unrepresentable_and_always_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(PacketError, match="unsupported_claim"):
        verify_evidence(missing, "i1_exit")

    result = main(["evidence-verify", "--manifest", str(missing), "--claim", "i1_exit"])
    decoded = json.loads(capsys.readouterr().out)
    assert result == CLI_FAILURE
    assert decoded["code"] == "unsupported_claim"
    assert "cp3d" not in EVIDENCE_SCHEMA.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("claim",), "i1_exit"),
        (("assurance",), "cp3d"),
        (("provenance",), "independently_verified"),
        (("window_start",), "2026-02-30"),
        (("occurrences", 0, "origin"), "routine_scheduler"),
        (("artifacts", 0, "media_type"), "text/plain"),
    ],
)
def test_evidence_schema_and_model_have_the_same_language(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    _, raw = _evidence(tmp_path)
    target: Any = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    validator = Draft202012Validator(
        json.loads(EVIDENCE_SCHEMA.read_text()),
        format_checker=FormatChecker(),
    )

    assert not validator.is_valid(raw)
    with pytest.raises(ValidationError):
        EvidenceManifest.model_validate_json(json.dumps(raw))


def test_manual_or_misattributed_scheduler_provenance_fails_closed(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    raw["occurrences"][0]["trigger"] = "manual"
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="invalid_document"):
        verify_evidence(path, "development_rehearsal")

    path, raw = _evidence(tmp_path / "provenance")
    receipt_path = _artifact_path(tmp_path / "provenance", raw, "receipt.0")
    payload = json.loads(receipt_path.read_text())
    payload["provenance"] = "fake-independent-receipt"
    _write_json(receipt_path, payload)
    _refresh_digest(tmp_path / "provenance", raw, "receipt.0")
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="invalid_document"):
        verify_evidence(path, "development_rehearsal")


@pytest.mark.parametrize("counterexample", ["gap", "duplicate_day", "wrong_schedule"])
def test_recurrence_requires_complete_distinct_bound_outcomes(
    tmp_path: Path,
    counterexample: str,
) -> None:
    path, raw = _evidence(tmp_path)
    if counterexample == "gap":
        raw["occurrences"][2]["working_day"] = "2026-07-25"
    elif counterexample == "duplicate_day":
        raw["occurrences"][1]["working_day"] = raw["occurrences"][0]["working_day"]
    else:
        raw["occurrences"][0]["schedule_ref"] = "schedule-ref://other/reference"
    _rewrite(path, raw)

    with pytest.raises(PacketError, match=r"working_day|schedule_changed"):
        verify_evidence(path, "development_rehearsal")


def test_result_and_receipt_artifacts_are_distinct_and_semantically_parsed(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    raw["occurrences"][1]["result_artifact_id"] = raw["occurrences"][0]["result_artifact_id"]
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="duplicate_occurrence_artifact"):
        verify_evidence(path, "development_rehearsal")

    path, raw = _evidence(tmp_path / "outcome")
    result_path = _artifact_path(tmp_path / "outcome", raw, "synthetic.0")
    payload = json.loads(result_path.read_text())
    payload["outcome"] = "development_nonqualifying"
    _write_json(result_path, payload)
    _refresh_digest(tmp_path / "outcome", raw, "synthetic.0")
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="invalid_document"):
        verify_evidence(path, "development_rehearsal")


def test_artifact_inventory_is_complete_exact_and_secret_free(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    raw["artifacts"][1]["kind"] = "synthetic_occurrence"
    raw["artifacts"][1]["content_schema"] = CONTENT_SCHEMAS["synthetic_occurrence"]
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="missing_artifact"):
        verify_evidence(path, "development_rehearsal")

    path, raw = _evidence(tmp_path / "secret")
    result_path = _artifact_path(tmp_path / "secret", raw, "synthetic.0")
    payload = json.loads(result_path.read_text())
    payload["token"] = FORBIDDEN_MARKER
    _write_json(result_path, payload)
    _refresh_digest(tmp_path / "secret", raw, "synthetic.0")
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="inline_secret_material"):
        verify_evidence(path, "development_rehearsal")


def test_artifact_individual_and_aggregate_bytes_are_bounded(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    result_path = _artifact_path(tmp_path, raw, "synthetic.0")
    result_path.write_bytes(result_path.read_bytes() + b" " * MAX_ARTIFACT_BYTES)
    _refresh_digest(tmp_path, raw, "synthetic.0")
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="document_too_large"):
        verify_evidence(path, "development_rehearsal")

    aggregate_root = tmp_path / "aggregate"
    path, raw = _evidence(aggregate_root)
    for descriptor in raw["artifacts"]:
        artifact_path = aggregate_root / descriptor["path"]
        artifact_path.write_bytes(artifact_path.read_bytes() + b" " * (55 * 1024))
        descriptor["sha256"] = _digest(artifact_path)
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="artifact_aggregate_too_large"):
        verify_evidence(path, "development_rehearsal")


def test_symlinked_artifact_component_is_rejected(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    moved = tmp_path / "moved-artifacts"
    artifact_dir.rename(moved)
    artifact_dir.symlink_to(moved, target_is_directory=True)
    _rewrite(path, raw)

    with pytest.raises(PacketError, match="missing_or_unsafe_directory"):
        verify_evidence(path, "development_rehearsal")


def test_digest_and_semantic_parse_use_the_same_artifact_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, raw = _evidence(tmp_path)
    result_path = _artifact_path(tmp_path, raw, "synthetic.0")
    original = load_snapshot
    replaced = False

    def replace_after_read(
        snapshot: FileSnapshot,
        model: type[BaseModel],
        *,
        field: str,
    ) -> BaseModel:
        nonlocal replaced
        if model is SyntheticResult and not replaced:
            replaced = True
            result_path.write_text('{"changed":true}', encoding="utf-8")
        return original(snapshot, model, field=field)

    monkeypatch.setattr(
        "tools.private_vps.evidence.load_snapshot",
        replace_after_read,
    )
    summary = verify_evidence(path, "development_rehearsal")
    assert summary.qualifying_working_days == EXPECTED_WORKING_DAYS


def test_scheduler_receipt_schema_is_runtime_validated(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    receipt_path = _artifact_path(tmp_path, raw, "receipt.0")
    payload = json.loads(receipt_path.read_text())
    payload["manual_command_ref"] = "file-ref://fake/self-receipt"
    _write_json(receipt_path, payload)
    _refresh_digest(tmp_path, raw, "receipt.0")
    _rewrite(path, raw)

    with pytest.raises(PacketError, match="invalid_document"):
        verify_evidence(path, "development_rehearsal")
    with pytest.raises(ValidationError):
        SchedulerReceipt.model_validate_json(json.dumps(payload))


def test_deployment_configuration_cannot_escape_its_artifact_directory(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    deployment_dir = tmp_path / "deployment"
    moved = tmp_path / "moved-deployment"
    deployment_dir.rename(moved)
    deployment_dir.symlink_to(moved, target_is_directory=True)
    _rewrite(path, raw)

    with pytest.raises(PacketError, match="missing_or_unsafe_directory"):
        verify_evidence(path, "development_rehearsal")


def test_evidence_cli_emits_the_typed_development_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, _ = _evidence(tmp_path)
    result = main(
        [
            "evidence-verify",
            "--manifest",
            os.fspath(path),
            "--claim",
            "development_rehearsal",
        ]
    )
    decoded = json.loads(capsys.readouterr().out)

    assert result == 0
    assert decoded == {
        "artifact_count": EXPECTED_ARTIFACT_COUNT,
        "claim": "development_rehearsal",
        "code": "valid",
        "issues": [],
        "ok": True,
        "operation": "evidence-verify",
        "qualifying_working_days": EXPECTED_WORKING_DAYS,
        "schema": "ctower.private-vps-result/v1",
    }
