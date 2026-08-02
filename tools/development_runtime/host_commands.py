"""Resolved host command paths and unit activation state for the development verbs."""

from __future__ import annotations

import shutil
from pathlib import Path

import tools.process_execution as process_execution  # noqa: PLR0402

__all__ = ["docker_path", "gpg_path", "unit_state"]

_INSPECT_TIMEOUT_SECONDS = 10.0


def docker_path() -> str:
    """Return the resolved Docker binary every container operation must use."""

    return _resolved("docker", "docker is required for the persistent development database")


def gpg_path() -> str:
    """Return the resolved GnuPG binary every checkpoint artifact operation must use."""

    return _resolved("gpg", "gpg is required to encrypt and decrypt development checkpoints")


def _resolved(name: str, refusal: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(refusal)
    return str(Path(executable).resolve(strict=True))


def unit_state(name: str) -> str:
    """Return one systemd user-unit activation state without raising on inactivity."""

    result = process_execution.run(
        ["/usr/bin/systemctl", "--user", "is-active", name],
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
        check=False,
        capture_output=True,
    )
    return result.stdout.strip()
