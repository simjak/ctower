"""Acceptance 3 and 6 checks for recurring private-VPS evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from tools.private_vps.cli import main
from tools.private_vps.evidence import verify_evidence
from tools.private_vps.manifest import PacketError

__all__: list[str] = []

ROOT = Path(__file__).parents[3]
PACKET = ROOT / "deploy/private-vps/development"
SINGLETON_KINDS = (
    "deployment_preflight",
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
SCHEDULE_REF = "schedule-ref://ctower/i1-daily"
START_DAY = date(2026, 7, 20)
EXPECTED_ARTIFACT_COUNT = 20
EXPECTED_WORKING_DAYS = 5


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _artifact(artifact_id: str, kind: str, path: Path, base: Path) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "path": path.relative_to(base).as_posix(),
        "sha256": _digest(path),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _deployment(root: Path) -> tuple[Path, dict[str, Any]]:
    directory = root / "deployment"
    directory.mkdir(parents=True)
    for name in ("compose.yaml", "Caddyfile", "otel-collector.yaml"):
        shutil.copyfile(PACKET / name, directory / name)
    raw = json.loads((PACKET / "bindings.example.json").read_text(encoding="utf-8"))
    path = directory / "bindings.json"
    _write_json(path, raw)
    return path, raw


def _evidence(root: Path) -> tuple[Path, dict[str, Any]]:
    deployment_path, deployment = _deployment(root)
    artifacts, occurrences = _artifacts_and_occurrences(root)
    raw = {
        "schema": "ctower.private-vps-evidence/v1",
        "evidence_id": "evidence.private-vps.development",
        "claim": "development_rehearsal",
        "assurance": "development",
        "durability_policy": "pending_only",
        "object_adapter": "local_encrypted_filesystem",
        "key_adapter": "local_file",
        "producer_ref": "identity-ref://evidence/producer",
        "verifier_ref": "identity-ref://evidence/verifier",
        "deployment_manifest": _artifact(
            "deployment.manifest",
            "deployment_preflight",
            deployment_path,
            root,
        ),
        "cp3d_manifest": None,
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


def _artifacts_and_occurrences(
    root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    artifacts: list[dict[str, str]] = []
    artifact_dir = root / "artifacts"
    for kind in SINGLETON_KINDS:
        path = artifact_dir / f"{kind}.json"
        _write_json(path, {"kind": kind, "outcome": "development_nonqualifying"})
        artifacts.append(_artifact(f"artifact.{kind}", kind, path, root))

    occurrences: list[dict[str, object]] = []
    for index in range(5):
        working_day = START_DAY + timedelta(days=index)
        scheduled_for = f"{working_day.isoformat()}T08:00:00Z"
        occurrence_id = f"occurrence.{working_day.isoformat()}"
        result_path = artifact_dir / f"synthetic-{index}.json"
        receipt_path = artifact_dir / f"receipt-{index}.json"
        _write_json(result_path, {"occurrence_id": occurrence_id, "outcome": "pass"})
        _write_json(
            receipt_path,
            {
                "schema": "ctower.scheduler-receipt/v1",
                "occurrence_id": occurrence_id,
                "schedule_ref": SCHEDULE_REF,
                "scheduled_for": scheduled_for,
                "source": "routine_scheduler",
                "manual_command_ref": None,
            },
        )
        result_id = f"synthetic.{index}"
        receipt_id = f"receipt.{index}"
        artifacts.append(_artifact(result_id, "synthetic_occurrence", result_path, root))
        artifacts.append(_artifact(receipt_id, "scheduler_receipt", receipt_path, root))
        occurrences.append(
            {
                "occurrence_id": occurrence_id,
                "schedule_ref": SCHEDULE_REF,
                "scheduled_for": scheduled_for,
                "working_day": working_day.isoformat(),
                "trigger": "scheduled",
                "origin": "routine_scheduler",
                "result_artifact_id": result_id,
                "scheduler_receipt_artifact_id": receipt_id,
                "manual_command_ref": None,
            }
        )
    return artifacts, occurrences


def _rewrite(path: Path, raw: dict[str, Any]) -> None:
    _write_json(path, raw)


def test_acceptance_3_five_distinct_scheduled_working_days_verify(tmp_path: Path) -> None:
    path, _ = _evidence(tmp_path)

    summary = verify_evidence(path, "development_rehearsal")

    assert summary.artifact_count == EXPECTED_ARTIFACT_COUNT
    assert summary.qualifying_working_days == EXPECTED_WORKING_DAYS


def test_acceptance_3_manual_run_cannot_masquerade_as_scheduled(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    raw["occurrences"][0]["trigger"] = "manual"
    raw["occurrences"][0]["origin"] = "manual_cli"
    raw["occurrences"][0]["manual_command_ref"] = "identity-ref://manual/command"
    _rewrite(path, raw)

    with pytest.raises(PacketError, match="manual_occurrence"):
        verify_evidence(path, "development_rehearsal")


def test_acceptance_3_scheduler_receipt_provenance_is_verified(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    receipt = next(item for item in raw["artifacts"] if item["artifact_id"] == "receipt.0")
    receipt_path = tmp_path / receipt["path"]
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["source"] = "manual_cli"
    _write_json(receipt_path, payload)
    receipt["sha256"] = _digest(receipt_path)
    _rewrite(path, raw)

    with pytest.raises(PacketError, match="invalid_document"):
        verify_evidence(path, "development_rehearsal")


def test_acceptance_3_fewer_than_five_distinct_working_days_is_rejected(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    raw["occurrences"] = raw["occurrences"][:4]
    _rewrite(path, raw)

    with pytest.raises(PacketError, match=r"invalid_document|insufficient_working_days"):
        verify_evidence(path, "development_rehearsal")


def test_acceptance_3_changed_bound_inputs_or_artifact_bytes_are_rejected(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    raw["bound_inputs"]["source"]["tree"] = "f" * 40
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="source_changed"):
        verify_evidence(path, "development_rehearsal")

    path, raw = _evidence(tmp_path / "second")
    artifact_path = tmp_path / "second" / raw["artifacts"][0]["path"]
    artifact_path.write_text("changed", encoding="utf-8")
    with pytest.raises(PacketError, match="artifact_changed"):
        verify_evidence(path, "development_rehearsal")


def test_acceptance_3_missing_and_duplicate_artifacts_are_rejected(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    missing = copy.deepcopy(raw)
    missing["artifacts"][0]["kind"] = "synthetic_occurrence"
    _rewrite(path, missing)
    with pytest.raises(PacketError, match="missing_artifact"):
        verify_evidence(path, "development_rehearsal")

    duplicate = copy.deepcopy(raw)
    duplicate["artifacts"][1]["artifact_id"] = duplicate["artifacts"][0]["artifact_id"]
    _rewrite(path, duplicate)
    with pytest.raises(PacketError, match="duplicate_artifact"):
        verify_evidence(path, "development_rehearsal")


def test_acceptance_3_self_verification_is_rejected(tmp_path: Path) -> None:
    path, raw = _evidence(tmp_path)
    raw["verifier_ref"] = raw["producer_ref"]
    _rewrite(path, raw)

    with pytest.raises(PacketError, match="invalid_document"):
        verify_evidence(path, "development_rehearsal")


def test_acceptance_3_i1_exit_rejects_local_adapters_and_missing_cp3d(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    raw.update(
        {
            "claim": "i1_exit",
            "assurance": "cp3d",
            "durability_policy": "cutover_rpo0",
        }
    )
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="local_adapter_forbidden"):
        verify_evidence(path, "i1_exit")

    raw["object_adapter"] = "external_s3"
    raw["key_adapter"] = "external_kms"
    _rewrite(path, raw)
    with pytest.raises(PacketError, match="cp3d_manifest_missing"):
        verify_evidence(path, "i1_exit")


def test_acceptance_3_i1_exit_requires_separately_verified_cp3d_manifest(
    tmp_path: Path,
) -> None:
    path, raw = _evidence(tmp_path)
    verification_path = tmp_path / "cp3d/verification.json"
    _write_json(verification_path, {"verdict": "pass", "independent": True})
    cp3d_path = tmp_path / "cp3d/manifest.json"
    deployment_digest = raw["deployment_manifest"]["sha256"]
    cp3d = {
        "schema": "ctower.cp3d-activation/v1",
        "activation_id": "cp3d.activation.verified",
        "source": raw["bound_inputs"]["source"],
        "deployment_manifest_sha256": deployment_digest,
        "control_image": raw["bound_inputs"]["control_image"],
        "configuration": raw["bound_inputs"]["configuration"],
        "assurance": "cp3d",
        "durability_policy": "cutover_rpo0",
        "failure_domain_count": 2,
        "cp3d_qualified": True,
        "accepted_record_rpo_seconds": 0,
        "object_adapter": "external_s3",
        "key_adapter": "external_kms",
        "producer_ref": "identity-ref://cp3d/producer",
        "verifier_ref": "identity-ref://cp3d/verifier",
        "verification_artifact": _artifact(
            "cp3d.verification",
            "deployment_preflight",
            verification_path,
            cp3d_path.parent,
        ),
    }
    _write_json(cp3d_path, cp3d)
    raw.update(
        {
            "claim": "i1_exit",
            "assurance": "cp3d",
            "durability_policy": "cutover_rpo0",
            "object_adapter": "external_s3",
            "key_adapter": "external_kms",
            "cp3d_manifest": _artifact(
                "cp3d.manifest",
                "deployment_preflight",
                cp3d_path,
                tmp_path,
            ),
        }
    )
    _rewrite(path, raw)

    summary = verify_evidence(path, "i1_exit")

    assert summary.qualifying_working_days == EXPECTED_WORKING_DAYS


def test_acceptance_6_evidence_cli_emits_typed_machine_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, _ = _evidence(tmp_path)

    result = main(
        [
            "evidence-verify",
            "--manifest",
            str(path),
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
