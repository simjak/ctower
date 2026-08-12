"""Strict values and failures shared by the migration ledger modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "MigrationAdoptionError",
    "MigrationAdvanceTransition",
    "MigrationBaseline",
    "MigrationExecutionError",
    "MigrationPreconditionError",
    "MigrationScript",
    "MigrationStateError",
]


@dataclass(frozen=True, slots=True)
class MigrationScript:
    """One checksum-verified authored database migration."""

    migration_id: str
    sha256: str
    scope: Literal["cluster", "database"]
    content: str


@dataclass(frozen=True, slots=True)
class MigrationBaseline:
    """One exact supported pre-ledger schema state."""

    through: str
    schema_sha256: str
    semantic_checks: Literal["ctower.pre-ledger/v1"]
    # Diagnostic only: canonical schema_sha256 remains the acceptance authority.
    schema_object_sum256: str


@dataclass(frozen=True, slots=True)
class MigrationAdvanceTransition:
    """One exact cluster-created state between recorded database migrations."""

    recorded_through: str
    recorded_schema_sha256: str
    cluster_through: str
    cluster_sha256: str
    postgres_major: int
    result_schema_sha256: str
    schema_object_sum256: str
    pending_database_from: str
    pending_database_through: str


class MigrationStateError(ValueError):
    """The migration ledger is malformed or contradicts the authored history."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class MigrationAdoptionError(MigrationStateError):
    """A pre-ledger database cannot prove the exact supported baseline."""


class MigrationPreconditionError(MigrationStateError):
    """A ledgered database fails an invariant the pending set requires."""


class MigrationExecutionError(MigrationStateError):
    """Authored migration SQL failed behind a bounded data-safe error."""
