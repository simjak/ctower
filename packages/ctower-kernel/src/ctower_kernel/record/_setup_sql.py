"""Checksum-locked migration and local bootstrap provisioning."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
from typing import TextIO, cast

import psycopg

__all__ = ["apply_migrations", "provision_bootstrap"]

MIGRATIONS = Path(__file__).parents[3] / "migrations"
MINIMUM_CAPABILITY_LENGTH = 32


def apply_migrations(dsn: str) -> None:
    """Verify and apply the authored checksum-ordered plain SQL migration set."""

    manifest = cast(
        dict[str, object], json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
    )
    entries = cast(list[dict[str, str]], manifest["migrations"])
    scripts: list[str] = []
    for entry in entries:
        content = (MIGRATIONS / entry["path"]).read_bytes()
        actual = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if not hmac.compare_digest(actual, entry["sha256"]):
            raise ValueError(f"migration checksum mismatch: {entry['path']}")
        scripts.append(content.decode())
    with psycopg.connect(dsn) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(712040119)")
        for script in scripts:
            connection.execute(script)


def provision_bootstrap(
    dsn: str,
    *,
    capability_input: TextIO,
    allowed_origin: str,
    expires_at: datetime,
) -> None:
    """Read one capability from a local stream and persist only its digest."""

    capability = capability_input.readline().rstrip("\r\n")
    if len(capability) < MINIMUM_CAPABILITY_LENGTH:
        raise ValueError("bootstrap capability must have at least 32 characters")
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            INSERT INTO bootstrap_capability (
                singleton, capability_digest, allowed_origin, expires_at
            ) VALUES (true, %s, %s, %s)
            """,
            (hashlib.sha256(capability.encode("utf-8")).digest(), allowed_origin, expires_at),
        )
