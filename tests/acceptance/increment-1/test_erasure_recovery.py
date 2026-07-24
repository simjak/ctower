"""Restart-safe erasure acceptance tests across external effect boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from support.tenant_fixture import TenantFixture

from ctower_kernel.proof.objects import ObjectIntegrityError, StoredObject, digest_bytes
from ctower_kernel.proof.postgres import PostgresProof

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
_TOMBSTONE_CLOCK_CALL = 2
__all__: tuple[str, ...] = ()


class CrashableErasureStore:
    """Idempotent external effects with one deterministic crash point."""

    def __init__(self, content: bytes, *, crash_at: str) -> None:
        self.content = content
        self.crash_at = crash_at
        self.object_exists = True
        self.key_exists = True

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        del tenant_id, artifact_digest, content, key_reference
        raise AssertionError("the fixture is already externally stored")

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        del tenant_id, receipt
        if not self.object_exists or not self.key_exists:
            raise ObjectIntegrityError("external object or key is unavailable")
        return self.content

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        del tenant_id, receipt
        if self.crash_at == "before_object":
            self.crash_at = ""
            raise RuntimeError("crash before object deletion")
        self.object_exists = False
        if self.crash_at == "after_object":
            self.crash_at = ""
            raise RuntimeError("crash after object deletion")
        self.key_exists = False
        if self.crash_at == "after_key":
            self.crash_at = ""
            raise RuntimeError("crash after key erasure")


@pytest.mark.parametrize("crash_at", ["before_object", "after_object", "after_key"])
def test_erasure_intent_reconciles_each_external_restart_point(
    tenant: TenantFixture,
    crash_at: str,
) -> None:
    content, receipt = _seed_external_object(tenant)
    store = CrashableErasureStore(content, crash_at=crash_at)
    intent_id = uuid4()
    proof = _proof(tenant, store)

    with pytest.raises(RuntimeError, match="crash"):
        proof.erase_object(
            tenant.tenant_id,
            receipt.artifact_digest,
            tombstone_id=intent_id,
            authority_ref="erasure-ref:test/approved",
            reason="retention expired",
        )
    _assert_pending(tenant, receipt.artifact_digest, intent_id)
    with pytest.raises(ObjectIntegrityError, match="pending reconciliation"):
        proof.read_object(tenant.tenant_id, receipt.artifact_digest)

    restarted = _proof(tenant, store)
    restarted.erase_object(
        tenant.tenant_id,
        receipt.artifact_digest,
        tombstone_id=intent_id,
        authority_ref="erasure-ref:test/approved",
        reason="retention expired",
    )
    _assert_erased(tenant, receipt.artifact_digest, intent_id)
    restarted.erase_object(
        tenant.tenant_id,
        receipt.artifact_digest,
        tombstone_id=intent_id,
        authority_ref="erasure-ref:test/approved",
        reason="retention expired",
    )


def test_erasure_reconciles_external_success_before_tombstone_and_rejects_drift(
    tenant: TenantFixture,
) -> None:
    content, receipt = _seed_external_object(tenant)
    store = CrashableErasureStore(content, crash_at="")
    intent_id = uuid4()
    calls = 0

    def crash_before_tombstone() -> datetime:
        nonlocal calls
        calls += 1
        if calls == _TOMBSTONE_CLOCK_CALL:
            raise RuntimeError("crash before tombstone")
        return NOW

    proof = PostgresProof(
        tenant.database.runtime_dsn,
        object_store=store,
        object_key_reference="kms-ref:test/object",
        clock=crash_before_tombstone,
    )
    with pytest.raises(RuntimeError, match="tombstone"):
        proof.erase_object(
            tenant.tenant_id,
            receipt.artifact_digest,
            tombstone_id=intent_id,
            authority_ref="erasure-ref:test/approved",
            reason="retention expired",
        )
    _assert_pending(tenant, receipt.artifact_digest, intent_id)

    restarted = _proof(tenant, store)
    with pytest.raises(ObjectIntegrityError, match="immutable identity"):
        restarted.erase_object(
            tenant.tenant_id,
            receipt.artifact_digest,
            tombstone_id=uuid4(),
            authority_ref="erasure-ref:test/approved",
            reason="retention expired",
        )
    restarted.erase_object(
        tenant.tenant_id,
        receipt.artifact_digest,
        tombstone_id=intent_id,
        authority_ref="erasure-ref:test/approved",
        reason="retention expired",
    )
    _assert_erased(tenant, receipt.artifact_digest, intent_id)


def _seed_external_object(tenant: TenantFixture) -> tuple[bytes, StoredObject]:
    content = b"restart-safe erasure evidence"
    artifact_digest = digest_bytes(content)
    receipt = StoredObject(
        artifact_digest=artifact_digest,
        object_key=f"tenants/{tenant.tenant_id}/objects/{artifact_digest}",
        object_version="version-1",
        ciphertext_sha256="sha256:" + "a" * 64,
        key_reference="kms-ref:test/object",
        key_version="v1",
        wrapped_key_sha256="sha256:" + "b" * 64,
        uploaded_at=NOW,
        verified_at=NOW,
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO proof_objects (
                tenant_id, artifact_digest, content, producer_id, recorded_at,
                storage_state, object_key, object_version, ciphertext_sha256,
                key_reference, key_version, wrapped_key_sha256, external_verified_at
            ) VALUES (%s, %s, NULL, %s, %s, 'external_verified', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant.tenant_id,
                bytes.fromhex(artifact_digest.removeprefix("sha256:")),
                tenant.commander_id,
                NOW,
                receipt.object_key,
                receipt.object_version,
                bytes.fromhex(receipt.ciphertext_sha256.removeprefix("sha256:")),
                receipt.key_reference,
                receipt.key_version,
                bytes.fromhex(receipt.wrapped_key_sha256.removeprefix("sha256:")),
                NOW,
            ),
        )
    return content, receipt


def _proof(tenant: TenantFixture, store: CrashableErasureStore) -> PostgresProof:
    return PostgresProof(
        tenant.database.runtime_dsn,
        object_store=store,
        object_key_reference="kms-ref:test/object",
        clock=lambda: NOW,
    )


def _assert_pending(
    tenant: TenantFixture,
    artifact_digest: str,
    intent_id: UUID,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        state = connection.execute(
            """
            SELECT object.storage_state, intent.erasure_intent_id
            FROM proof_objects AS object
            JOIN object_erasure_intents AS intent
              USING (tenant_id, artifact_digest)
            WHERE object.tenant_id = %s AND object.artifact_digest = %s
            """,
            (tenant.tenant_id, bytes.fromhex(artifact_digest.removeprefix("sha256:"))),
        ).fetchone()
    assert state == ("erasure_pending", intent_id)


def _assert_erased(
    tenant: TenantFixture,
    artifact_digest: str,
    intent_id: UUID,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        state = connection.execute(
            """
            SELECT object.storage_state, tombstone.erasure_intent_id
            FROM proof_objects AS object
            JOIN object_erasure_tombstones AS tombstone
              USING (tenant_id, artifact_digest)
            WHERE object.tenant_id = %s AND object.artifact_digest = %s
            """,
            (tenant.tenant_id, bytes.fromhex(artifact_digest.removeprefix("sha256:"))),
        ).fetchone()
    assert state == ("erased", intent_id)
