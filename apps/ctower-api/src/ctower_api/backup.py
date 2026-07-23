"""Public local composition for the one fixed CP3-C backup Adapter."""

from __future__ import annotations

from uuid import UUID

from ctower_api._backup_adapter import (
    BackupAdapterConfig,
    BackupError,
    BackupManifest,
    FixedBackupAdapter,
)

__all__ = ["BackupAdapterConfig", "BackupError", "BackupManifest", "LocalBackup"]


class LocalBackup:
    """Expose the fixed daily operation without exposing command execution."""

    def __init__(self, config: BackupAdapterConfig) -> None:
        self._adapter = FixedBackupAdapter(config)

    def run_daily(
        self,
        tenant_id: UUID,
        backup_id: UUID,
        *,
        key_version: str,
    ) -> BackupManifest:
        """Require complete physical, WAL, logical, object, and key evidence."""

        return self._adapter.run_daily(
            tenant_id,
            backup_id,
            key_version=key_version,
        )
