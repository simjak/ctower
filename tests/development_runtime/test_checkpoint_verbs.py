"""Named refusals, append-only ledger, and protected wiring for the checkpoint verbs."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

import tools.development_runtime.checkpoint as checkpoint  # noqa: PLR0402
import tools.development_runtime.checkpoint_ledger as ledger
import tools.development_runtime.interface as runtime_interface
import tools.process_execution as process_execution  # noqa: PLR0402
from ctower_api.development_config import DevelopmentConfig

__all__: tuple[str, ...] = ()

_IMAGE = "postgres@sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
_ARTIFACT_KEY = "development-checkpoint-artifact-key"
_ADMIN_REF = "secret-service:ctower-development/postgres-admin"
_SERVING = ("sha256:" + "a" * 64, "0039_project_seat_credentials.sql")
_OTHER_GENERATION = "sha256:" + "b" * 64
_EMPTY_LEDGER = f"sha256:{hashlib.sha256(b'').hexdigest()}"


def test_restore_refuses_an_unknown_checkpoint_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    known = _capture(monkeypatch, b"first-artifact")

    with pytest.raises(checkpoint.CheckpointRefusedError, match="unknown development checkpoint"):
        checkpoint.restore_checkpoint(known.checkpoint_id.replace("2026", "2025"))

    assert checkpoint.list_checkpoints() == (known,)


def test_restore_refuses_while_the_instance_is_still_serving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    record = _capture(monkeypatch, b"first-artifact")
    applied = _observe_application(monkeypatch, refuse=True)
    monkeypatch.setattr(checkpoint, "unit_state", lambda _name: "active")

    with pytest.raises(
        checkpoint.CheckpointRefusedError, match="the development instance is not stopped"
    ) as refusal:
        checkpoint.restore_checkpoint(record.checkpoint_id)

    assert "ctower-development-api.service" in str(refusal.value)
    assert "ctower-development-worker.service" in str(refusal.value)
    assert applied == []


def test_restore_refuses_a_generation_change_without_the_explicit_allowance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    record = _capture(monkeypatch, b"first-artifact")
    applied = _observe_application(monkeypatch, refuse=True)
    monkeypatch.setattr(checkpoint, "_serving_generation", lambda _config: _moved_generation())

    with pytest.raises(
        checkpoint.CheckpointRefusedError, match="the serving generation does not match"
    ) as refusal:
        checkpoint.restore_checkpoint(record.checkpoint_id)

    assert _OTHER_GENERATION in str(refusal.value)
    assert record.generation in str(refusal.value)
    assert applied == []


def test_restore_applies_a_generation_change_only_when_explicitly_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    record = _capture(monkeypatch, b"first-artifact")
    applied = _observe_application(monkeypatch, refuse=False)
    monkeypatch.setattr(checkpoint, "_serving_generation", lambda _config: _moved_generation())

    restored = checkpoint.restore_checkpoint(record.checkpoint_id, allow_generation_change=True)

    assert restored == record
    assert applied == [ledger.artifact_path(record.checkpoint_id)]


def test_restore_refuses_an_artifact_that_no_longer_matches_the_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    record = _capture(monkeypatch, b"first-artifact")
    applied = _observe_application(monkeypatch, refuse=True)
    artifact = ledger.artifact_path(record.checkpoint_id)
    artifact.chmod(0o600)
    artifact.write_bytes(b"first-artifacX")

    with pytest.raises(checkpoint.CheckpointRefusedError, match="does not match its ledger digest"):
        checkpoint.restore_checkpoint(record.checkpoint_id)

    assert applied == []


def test_restore_refuses_a_checkpoint_whose_artifact_was_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    record = _capture(monkeypatch, b"first-artifact")
    applied = _observe_application(monkeypatch, refuse=True)
    ledger.artifact_path(record.checkpoint_id).unlink()

    with pytest.raises(checkpoint.CheckpointRefusedError, match="artifact is missing"):
        checkpoint.restore_checkpoint(record.checkpoint_id)

    assert applied == []


def test_the_ledger_only_grows_and_never_rewrites_an_earlier_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    first = _capture(monkeypatch, b"first-artifact")
    first_bytes = _ledger_path().read_bytes()

    second = _capture(monkeypatch, b"second-artifact")

    grown = _ledger_path().read_bytes()
    assert grown.startswith(first_bytes)
    assert first.previous_sha256 == _EMPTY_LEDGER
    assert second.previous_sha256 == f"sha256:{hashlib.sha256(first_bytes).hexdigest()}"
    assert checkpoint.list_checkpoints() == (first, second)


def test_listing_refuses_a_ledger_whose_earlier_entry_was_rewritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    first = _capture(monkeypatch, b"first-artifact")
    _capture(monkeypatch, b"second-artifact")
    lines = _ledger_path().read_bytes().splitlines(keepends=True)
    rewritten = first.model_copy(update={"database": "ctower_shadow"})
    _ledger_path().write_bytes(rewritten.model_dump_json(by_alias=True).encode() + b"\n" + lines[1])

    with pytest.raises(ledger.CheckpointLedgerError, match="is not append-only at line 2"):
        checkpoint.list_checkpoints()


def test_listing_refuses_a_ledger_line_that_is_not_one_whole_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    _capture(monkeypatch, b"first-artifact")
    _ledger_path().write_bytes(_ledger_path().read_bytes()[:-40])

    with pytest.raises(ledger.CheckpointLedgerError, match="is truncated at line 1"):
        checkpoint.list_checkpoints()


def test_appending_refuses_a_record_chained_to_a_superseded_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    first = _capture(monkeypatch, b"first-artifact")
    _capture(monkeypatch, b"second-artifact")

    with pytest.raises(ledger.CheckpointLedgerError, match="advanced while this checkpoint"):
        ledger.append_record(first)


def test_the_artifact_key_only_crosses_an_anonymous_descriptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    delivered: list[str] = []
    arguments: list[str] = []

    def _capture_invocation(
        producer: Sequence[str],
        consumer: Sequence[str],
        *,
        timeout_seconds: float,
        producer_descriptors: Sequence[int] = (),
        consumer_descriptors: Sequence[int] = (),
    ) -> None:
        del timeout_seconds, producer_descriptors
        (descriptor,) = consumer_descriptors
        delivered.append(os.read(descriptor, 4096).decode("utf-8"))
        arguments.extend((*producer, *consumer))
        Path(consumer[consumer.index("--output") + 1]).write_bytes(b"opaque-ciphertext")

    monkeypatch.setattr(process_execution, "pipeline", _capture_invocation)

    record = checkpoint.create_checkpoint()

    assert delivered == [_ARTIFACT_KEY]
    assert all(_ARTIFACT_KEY not in argument for argument in arguments)
    assert all(_ARTIFACT_KEY not in value for value in os.environ.values())
    assert record.passphrase_ref == _ADMIN_REF
    assert record.generation == _SERVING[0]
    assert record.generation_migration_id == _SERVING[1]
    assert ledger.artifact_path(record.checkpoint_id).read_bytes() == b"opaque-ciphertext"


def test_the_protected_cli_wires_every_checkpoint_verb(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _bind_without_database(monkeypatch, tmp_path)
    record = _capture(monkeypatch, b"first-artifact")
    created: list[str] = []
    restored: list[tuple[str, bool]] = []

    def _create() -> ledger.CheckpointRecord:
        created.append("create")
        return record

    def _restore(
        checkpoint_id: str,
        *,
        allow_generation_change: bool = False,
    ) -> ledger.CheckpointRecord:
        restored.append((checkpoint_id, allow_generation_change))
        return record

    monkeypatch.setattr(checkpoint, "create_checkpoint", _create)
    monkeypatch.setattr(checkpoint, "restore_checkpoint", _restore)

    created_report = _run_cli(monkeypatch, capsys, "checkpoint")
    listed = _run_cli(monkeypatch, capsys, "checkpoint", "list")
    restored_report = _run_cli(
        monkeypatch,
        capsys,
        "restore",
        "--checkpoint-id",
        record.checkpoint_id,
        "--allow-generation-change",
    )

    assert created == ["create"]
    assert restored == [(record.checkpoint_id, True)]
    assert created_report == listed == restored_report
    assert [item["checkpoint_id"] for item in listed["checkpoints"]] == [record.checkpoint_id]
    assert listed["checkpoints"][0]["passphrase_ref"] == _ADMIN_REF


def test_the_restore_verb_requires_an_explicit_checkpoint_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ctower-private-vps", "restore"])

    with pytest.raises(SystemExit):
        runtime_interface.main()


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> dict[str, list[dict[str, str]]]:
    monkeypatch.setattr(sys, "argv", ["ctower-private-vps", *arguments])
    runtime_interface.main()
    return cast(dict[str, list[dict[str, str]]], json.loads(capsys.readouterr().out))


def _bind_without_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(checkpoint, "load_config", _config)
    monkeypatch.setattr(checkpoint, "load_secret", lambda _reference: _ARTIFACT_KEY)
    monkeypatch.setattr(checkpoint, "unit_state", lambda _name: "inactive")
    monkeypatch.setattr(checkpoint, "_serving_generation", lambda _config: _SERVING)


def _capture(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> ledger.CheckpointRecord:
    """Capture one real checkpoint whose encrypted bytes the test chooses."""

    def _write_artifact(
        producer: Sequence[str],
        consumer: Sequence[str],
        *,
        timeout_seconds: float,
        producer_descriptors: Sequence[int] = (),
        consumer_descriptors: Sequence[int] = (),
    ) -> None:
        del producer, timeout_seconds, producer_descriptors, consumer_descriptors
        Path(consumer[consumer.index("--output") + 1]).write_bytes(payload)

    with monkeypatch.context() as capturing:
        capturing.setattr(process_execution, "pipeline", _write_artifact)
        return checkpoint.create_checkpoint()


def _moved_generation() -> tuple[str, str]:
    return _OTHER_GENERATION, "0040_after_the_checkpoint.sql"


def _observe_application(monkeypatch: pytest.MonkeyPatch, *, refuse: bool) -> list[Path]:
    applied: list[Path] = []

    def _apply(_config: DevelopmentConfig, artifact: Path) -> None:
        if refuse:
            raise AssertionError("a refused restore must never reach the database")
        applied.append(artifact)

    monkeypatch.setattr(checkpoint, "_verify_artifact_decrypts", lambda *_arguments: None)
    monkeypatch.setattr(checkpoint, "_apply_checkpoint", _apply)
    return applied


def _ledger_path() -> Path:
    return ledger.checkpoint_root() / "ledger.jsonl"


def _config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate(
        {
            "schema": "ctower.development-runtime/v1",
            "label": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
            "api_host": "127.0.0.1",
            "api_port": 8091,
            "database_host": "127.0.0.1",
            "database_name": "ctower",
            "primary_port": 55432,
            "standby_port": 55433,
            "postgres_image": _IMAGE,
            "postgres_admin_secret_ref": _ADMIN_REF,
            "migrator_secret_ref": "secret-service:ctower-development/migrator",
            "runtime_secret_ref": "secret-service:ctower-development/runtime",
            "projection_secret_ref": "secret-service:ctower-development/projection",
            "operator_secret_ref": "secret-service:ctower-development/operator",
            "commander_secret_ref": "secret-service:ctower-development/commander",
        }
    )
