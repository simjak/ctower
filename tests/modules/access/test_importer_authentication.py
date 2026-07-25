"""Exact migration-importer authentication remains separate from general auth."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from ctower_kernel.access import Access
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem

__all__: tuple[str, ...] = ()


class _Record:
    def actor_for_credential(self, credential_digest: bytes) -> Actor | None:
        del credential_digest
        return None


def test_importer_authentication_hashes_bearer_and_binds_exact_scope() -> None:
    run_id, cutover_id, tenant_id = uuid4(), uuid4(), uuid4()
    importer = Actor(uuid4(), tenant_id, PrincipalKind.MIGRATION_IMPORTER)
    observed: list[tuple[bytes, UUID, UUID, str, datetime]] = []

    def resolve(
        digest: bytes, run: UUID, cutover: UUID, project: str, now: datetime
    ) -> Actor | None:
        observed.append((digest, run, cutover, project, now))
        return importer if (run, cutover, project) == (run_id, cutover_id, "ctower") else None

    access = Access(
        cast(Record, _Record()),
        importer_resolver=resolve,
        clock=lambda: datetime(2026, 7, 25, tzinfo=UTC),
    )
    accepted = access.authenticate_importer(
        "Bearer opaque-importer",
        run_id=run_id,
        cutover_id=cutover_id,
        project_key="ctower",
    )
    refused = access.authenticate_importer(
        "Bearer opaque-importer",
        run_id=uuid4(),
        cutover_id=cutover_id,
        project_key="ctower",
    )

    assert accepted == importer
    assert isinstance(refused, RecordProblem)
    general = access.authenticate("Bearer opaque-importer")
    assert isinstance(general, RecordProblem)
    assert general.code == "unauthorized"
    assert observed[0][0] == hashlib.sha256(b"opaque-importer").digest()
