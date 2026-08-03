"""Encrypted database checkpoint, listing, and refusing restore for the E2 runtime.

A checkpoint here is an operations fact about the development database cluster. It is
unrelated to the product-domain delivery checkpoint the Catalog defines, and it proves
neither CP3-C backup evidence nor CP3-D independent durability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg

import tools.process_execution as process_execution  # noqa: PLR0402
from ctower_api.development_config import DevelopmentConfig, load_config
from ctower_api.development_secrets import development_dsn, load_secret
from tools.development_runtime.checkpoint_ledger import (
    CheckpointLedgerError,
    CheckpointRecord,
    append_record,
    artifact_path,
    checkpoint_root,
    ledger_digest,
    read_records,
    serialize_checkpoints,
)
from tools.development_runtime.host_commands import docker_path, gpg_path, unit_state

__all__ = [
    "CheckpointLedgerError",
    "CheckpointRecord",
    "CheckpointRefusedError",
    "add_checkpoint_commands",
    "create_checkpoint",
    "list_checkpoints",
    "restore_checkpoint",
    "run_checkpoint_command",
]

# Typeshed exposes no public alias for the object `add_subparsers()` returns.
type _Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]

_PRIMARY_CONTAINER = "ctower-development-primary"
_MAINTENANCE_DATABASE = "postgres"
_SERVING_UNITS = (
    "ctower-development-api.service",
    "ctower-development-worker.service",
)
_STAGING_NAME = "staging"
_ARTIFACT_NAME = "database.sql.gpg"
_DIGEST_CHUNK_BYTES = 1 << 20
_CAPTURE_TIMEOUT_SECONDS = 900.0
_VERIFY_TIMEOUT_SECONDS = 300.0
_RESTORE_TIMEOUT_SECONDS = 900.0


class CheckpointRefusedError(RuntimeError):
    """One named refusal that keeps the development database exactly as it is."""


def add_checkpoint_commands(commands: _Subcommands) -> None:
    """Register the checkpoint, checkpoint list, and restore verbs on one parser."""

    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_subparsers(dest="checkpoint_command").add_parser("list")
    restore = commands.add_parser("restore")
    restore.add_argument("--checkpoint-id", required=True)
    restore.add_argument("--allow-generation-change", action="store_true")


def run_checkpoint_command(arguments: argparse.Namespace) -> str:
    """Execute one selected checkpoint verb and render its secret-free report."""

    if arguments.command == "restore":
        restored = restore_checkpoint(
            arguments.checkpoint_id,
            allow_generation_change=arguments.allow_generation_change,
        )
        return _render((restored,))
    if arguments.checkpoint_command == "list":
        return _render(list_checkpoints())
    return _render((create_checkpoint(),))


def create_checkpoint() -> CheckpointRecord:
    """Capture one encrypted checkpoint of the development database and record it."""

    config = load_config()
    with serialize_checkpoints():
        generation, migration_id = _serving_generation(config)
        captured_at = datetime.now(UTC)
        staged = _staged_artifact()
        _capture_encrypted_dump(config, staged)
        digest, size = _digest_file(staged)
        checkpoint_id = f"{captured_at:%Y%m%dT%H%M%SZ}-{digest}"
        record = CheckpointRecord.model_validate(
            {
                "schema": "ctower.development-checkpoint/v1",
                "checkpoint_id": checkpoint_id,
                "captured_at": captured_at,
                "database": config.database_name,
                "generation": generation,
                "generation_migration_id": migration_id,
                "artifact_sha256": f"sha256:{digest}",
                "artifact_bytes": size,
                "passphrase_ref": config.postgres_admin_secret_ref,
                "previous_sha256": _ledger_head(),
            }
        )
        _retain(staged, artifact_path(checkpoint_id))
        append_record(record)
        return record


def list_checkpoints() -> tuple[CheckpointRecord, ...]:
    """Return every recorded checkpoint after proving the ledger only ever grew."""

    with serialize_checkpoints():
        return read_records()


def restore_checkpoint(
    checkpoint_id: str,
    *,
    allow_generation_change: bool = False,
) -> CheckpointRecord:
    """Replace the development database with one recorded checkpoint, or refuse by name."""

    config = load_config()
    with serialize_checkpoints():
        record = _selected_record(checkpoint_id)
        _require_stopped_instance()
        _require_recorded_generation(
            config,
            record,
            allow_generation_change=allow_generation_change,
        )
        artifact = artifact_path(record.checkpoint_id)
        _require_recorded_artifact(artifact, record)
        _verify_artifact_decrypts(config, artifact)
        _apply_checkpoint(config, artifact)
        return record


def _render(records: Sequence[CheckpointRecord]) -> str:
    """Render one stable secret-free document shared by all three checkpoint verbs."""

    return json.dumps(
        {
            "schema": "ctower.development-checkpoint-report/v1",
            "checkpoints": [record.model_dump(mode="json", by_alias=True) for record in records],
        },
        sort_keys=True,
    )


def _selected_record(checkpoint_id: str) -> CheckpointRecord:
    for record in read_records():
        if record.checkpoint_id == checkpoint_id:
            return record
    raise CheckpointRefusedError(f"unknown development checkpoint id {checkpoint_id}")


def _require_stopped_instance() -> None:
    running = tuple(name for name in _SERVING_UNITS if unit_state(name) == "active")
    if running:
        raise CheckpointRefusedError(
            "the development instance is not stopped: " + " ".join(running)
        )


def _require_recorded_generation(
    config: DevelopmentConfig,
    record: CheckpointRecord,
    *,
    allow_generation_change: bool,
) -> None:
    generation, migration_id = _serving_generation(config)
    if generation == record.generation or allow_generation_change:
        return
    raise CheckpointRefusedError(
        "the serving generation does not match the checkpoint generation: serving "
        f"{migration_id} {generation} against checkpoint "
        f"{record.generation_migration_id} {record.generation}"
    )


def _require_recorded_artifact(artifact: Path, record: CheckpointRecord) -> None:
    if not artifact.is_file():
        raise CheckpointRefusedError(
            f"the development checkpoint artifact is missing for {record.checkpoint_id}"
        )
    digest, size = _digest_file(artifact)
    if f"sha256:{digest}" != record.artifact_sha256 or size != record.artifact_bytes:
        raise CheckpointRefusedError(
            "the development checkpoint artifact does not match its ledger digest for "
            f"{record.checkpoint_id}"
        )


def _serving_generation(config: DevelopmentConfig) -> tuple[str, str]:
    with psycopg.connect(development_dsn(config, "postgres")) as connection:
        row = connection.execute(
            """
            SELECT migration_id, result_schema_sha256 FROM ctower_schema_migrations
            ORDER BY migration_id DESC LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise CheckpointRefusedError("the development database records no schema generation")
    return str(row[1]), str(row[0])


def _capture_encrypted_dump(config: DevelopmentConfig, artifact: Path) -> None:
    with _passphrase_descriptor(config) as descriptor:
        process_execution.pipeline(
            [
                docker_path(),
                "exec",
                "--user",
                "postgres",
                _PRIMARY_CONTAINER,
                "pg_dump",
                "--create",
                "--clean",
                "--if-exists",
                "--quote-all-identifiers",
                "--dbname",
                config.database_name,
            ],
            [
                *_gpg_invocation(descriptor),
                "--symmetric",
                "--cipher-algo",
                "AES256",
                "--output",
                str(artifact),
            ],
            timeout_seconds=_CAPTURE_TIMEOUT_SECONDS,
            consumer_descriptors=(descriptor,),
        )


def _verify_artifact_decrypts(config: DevelopmentConfig, artifact: Path) -> None:
    with _passphrase_descriptor(config) as descriptor:
        process_execution.run(
            [
                *_gpg_invocation(descriptor),
                "--decrypt",
                "--output",
                os.devnull,
                str(artifact),
            ],
            timeout_seconds=_VERIFY_TIMEOUT_SECONDS,
            check=True,
            discard_output=True,
            inherited_descriptors=(descriptor,),
        )


def _apply_checkpoint(config: DevelopmentConfig, artifact: Path) -> None:
    with _passphrase_descriptor(config) as descriptor:
        process_execution.pipeline(
            [*_gpg_invocation(descriptor), "--decrypt", str(artifact)],
            [
                docker_path(),
                "exec",
                "--interactive",
                "--user",
                "postgres",
                _PRIMARY_CONTAINER,
                "psql",
                "--no-psqlrc",
                "--quiet",
                "--set",
                "ON_ERROR_STOP=1",
                "--username",
                "postgres",
                "--dbname",
                _MAINTENANCE_DATABASE,
            ],
            timeout_seconds=_RESTORE_TIMEOUT_SECONDS,
            producer_descriptors=(descriptor,),
        )


def _gpg_invocation(descriptor: int) -> tuple[str, ...]:
    return (
        gpg_path(),
        "--batch",
        "--quiet",
        "--yes",
        "--no-symkey-cache",
        "--pinentry-mode",
        "loopback",
        "--passphrase-fd",
        str(descriptor),
    )


@contextmanager
def _passphrase_descriptor(config: DevelopmentConfig) -> Iterator[int]:
    """Hand the artifact passphrase to one child through an anonymous descriptor only."""

    secret = load_secret(config.postgres_admin_secret_ref).encode("utf-8")
    read_end, write_end = os.pipe()
    try:
        with os.fdopen(write_end, "wb") as stream:
            stream.write(secret)
        yield read_end
    finally:
        os.close(read_end)


def _staged_artifact() -> Path:
    staging = checkpoint_root() / _STAGING_NAME
    staging.mkdir(mode=0o700, parents=True, exist_ok=True)
    staged = staging / _ARTIFACT_NAME
    staged.unlink(missing_ok=True)
    return staged


def _retain(staged: Path, destination: Path) -> None:
    destination.parent.mkdir(mode=0o700, parents=True)
    staged.replace(destination)
    destination.chmod(0o400)


def _ledger_head() -> str:
    read_records()
    return ledger_digest()


def _digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_DIGEST_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
