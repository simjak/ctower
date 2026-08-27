"""The real rollback target: the product's recorded development checkpoints."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ctower_api.development_config import load_config
from ctower_api.development_secrets import load_secret
from tools.development_runtime._rehearsal_cluster import Clone
from tools.development_runtime._rehearsal_vocabulary import (
    CHECKPOINT_ARTIFACT_NAME,
    CHECKPOINT_RESTORE_TIMEOUT_SECONDS,
    UpgradeRehearsalError,
)
from tools.development_runtime.checkpoint_ledger import artifact_path, read_records
from tools.development_runtime.host_commands import docker_path, gpg_path

__all__ = ["ProductCheckpoint", "resolve_replay_checkpoint", "restore_product_checkpoint"]

# ---------------------------------------------------------------------------
# real rollback target -- the product's recorded development checkpoints
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProductCheckpoint:
    """One recorded development-runtime checkpoint plus the note of how it was chosen."""

    checkpoint_id: str
    artifact: Path
    artifact_sha256: str
    generation: str = ""
    generation_migration_id: str = ""
    note: str = ""


def resolve_replay_checkpoint(spec: str | None) -> ProductCheckpoint | None:
    """Choose the checkpoint as-live-now must replay as the real rollback target.

    ``spec`` may be a recorded checkpoint id, a path to a decryptable artifact (file or the
    owning directory), or None (default: the product's LATEST recorded checkpoint). Returns
    None only when no spec was given and the product ledger holds no checkpoint.
    """

    if spec is None:
        records = read_records()
        if not records:
            return None
        latest = records[-1]
        _require_checkpoint_artifact(
            latest.checkpoint_id, artifact_path(latest.checkpoint_id), latest.artifact_sha256
        )
        return ProductCheckpoint(
            checkpoint_id=latest.checkpoint_id,
            artifact=artifact_path(latest.checkpoint_id),
            artifact_sha256=latest.artifact_sha256,
            generation=latest.generation,
            generation_migration_id=latest.generation_migration_id,
            note=(
                f"replayed the product's latest recorded checkpoint {latest.checkpoint_id} "
                f"({latest.generation_migration_id} @ {latest.generation[:16]}…) as the real "
                f"rollback target"
            ),
        )
    candidate = Path(spec).expanduser()
    if candidate.is_dir():
        candidate = candidate / CHECKPOINT_ARTIFACT_NAME
    if candidate.is_file():
        return ProductCheckpoint(
            checkpoint_id=f"artifact:{candidate}",
            artifact=candidate,
            artifact_sha256=f"sha256:{_file_sha256(candidate)}",
            note=f"replayed the checkpoint artifact at {candidate}",
        )
    for record in read_records():
        if record.checkpoint_id == spec:
            _require_checkpoint_artifact(
                record.checkpoint_id, artifact_path(record.checkpoint_id), record.artifact_sha256
            )
            return ProductCheckpoint(
                checkpoint_id=record.checkpoint_id,
                artifact=artifact_path(record.checkpoint_id),
                artifact_sha256=record.artifact_sha256,
                generation=record.generation,
                generation_migration_id=record.generation_migration_id,
                note=(
                    f"replayed the recorded checkpoint {record.checkpoint_id} "
                    f"({record.generation_migration_id} @ {record.generation[:16]}…)"
                ),
            )
    raise UpgradeRehearsalError(
        f"unknown development checkpoint id or missing artifact path: {spec}"
    )


def _require_checkpoint_artifact(checkpoint_id: str, artifact: Path, artifact_sha256: str) -> None:
    if not artifact.is_file():
        raise UpgradeRehearsalError(
            f"the development checkpoint artifact is missing for {checkpoint_id}"
        )
    digest = _file_sha256(artifact)
    if artifact_sha256 and f"sha256:{digest}" != artifact_sha256:
        raise UpgradeRehearsalError(
            f"the development checkpoint artifact does not match its ledger digest for "
            f"{checkpoint_id}"
        )


def restore_product_checkpoint(clone: Clone, checkpoint: ProductCheckpoint) -> None:
    """Replace the clone's ctower database with the recorded encrypted checkpoint."""

    _require_checkpoint_artifact(
        checkpoint.checkpoint_id, checkpoint.artifact, checkpoint.artifact_sha256
    )
    secret = _checkpoint_passphrase()
    docker = docker_path()
    gpg = gpg_path()
    decrypt = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            gpg,
            "--batch",
            "--quiet",
            "--yes",
            "--no-symkey-cache",
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--decrypt",
            str(checkpoint.artifact),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    decrypt_input = decrypt.stdin
    decrypt_output = decrypt.stdout
    if decrypt_input is None or decrypt_output is None:
        decrypt.kill()
        raise UpgradeRehearsalError("gpg did not expose the checkpoint decrypt pipeline")
    try:
        decrypt_input.write(secret.encode("utf-8"))
        decrypt_input.close()
    except BrokenPipeError:
        pass
    try:
        finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                docker,
                "exec",
                "--interactive",
                "--user",
                "postgres",
                clone.container,
                "psql",
                "--no-psqlrc",
                "--quiet",
                "--set",
                "ON_ERROR_STOP=1",
                "--username",
                "postgres",
                "--dbname",
                "postgres",
            ],
            stdin=decrypt_output,
            capture_output=True,
            timeout=CHECKPOINT_RESTORE_TIMEOUT_SECONDS,
            check=False,
        )
    finally:
        decrypt_output.close()
        try:
            decrypt.wait(timeout=120)
        except subprocess.TimeoutExpired:
            decrypt.kill()
    if finished.returncode != 0:
        raise UpgradeRehearsalError(
            "the development checkpoint restore into the clone failed: "
            f"{finished.stderr.decode(errors='replace')[-400:]}"
        )


def _checkpoint_passphrase() -> str:
    config = load_config()
    return load_secret(config.postgres_admin_secret_ref)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
