"""Public recovery policy fault matrix without storage shortcuts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.recovery import (
    AcceptedRoot,
    ExpectedSource,
    InventoryRevision,
    RecoveryPolicy,
    RestoreCheck,
    RestoreStepKind,
)

TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
INSTALLATION_ID = UUID("20000000-0000-4000-8000-000000000001")
BACKUP_ID = UUID("30000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)


def test_anchor_is_digest_chained_contiguous_and_replay_stable() -> None:
    policy = RecoveryPolicy()
    roots = (
        AcceptedRoot(acceptance_position=1, command_root="sha256:" + "1" * 64),
        AcceptedRoot(acceptance_position=2, command_root="sha256:" + "2" * 64),
    )

    first = policy.build_anchor(roots, previous_anchor_sha256=None)
    replay = policy.build_anchor(roots, previous_anchor_sha256=None)

    assert first == replay
    with pytest.raises(ValueError, match="contiguous"):
        policy.build_anchor(
            (roots[0], AcceptedRoot(acceptance_position=3, command_root="sha256:" + "3" * 64)),
            previous_anchor_sha256=None,
        )


def test_restore_rejects_invalid_inventory_signature_and_missing_active_source() -> None:
    inventory = _inventory(active_provider=True)
    report = RecoveryPolicy().evaluate_restore(
        restore_run_id=uuid4(),
        tenant_id=TENANT_ID,
        installation_id=INSTALLATION_ID,
        backup_id=BACKUP_ID,
        inventory=inventory,
        inventory_signature_verified=False,
        reconciled_source_keys=frozenset(),
        accepted_source_position=8,
        restored_acceptance_position=8,
        artifact_rpo_seconds=60,
        started_at=NOW,
        completed_at=NOW + timedelta(minutes=3),
        checks=_checks(),
    )

    reasons = {finding.reason for finding in report.findings}
    assert "inventory-signature-invalid" in reasons
    assert "inventory-active-source-unreconciled:ctower.provider.default" in reasons
    assert report.enablement_eligible is False
    assert report.effects_enabled is False


def test_restore_requires_complete_order_and_all_recovered_bytes_checks() -> None:
    policy = RecoveryPolicy()
    with pytest.raises(ValueError, match="complete and strictly ordered"):
        policy.evaluate_restore(
            restore_run_id=uuid4(),
            tenant_id=TENANT_ID,
            installation_id=INSTALLATION_ID,
            backup_id=BACKUP_ID,
            inventory=_inventory(),
            inventory_signature_verified=True,
            reconciled_source_keys=frozenset(),
            accepted_source_position=4,
            restored_acceptance_position=4,
            artifact_rpo_seconds=0,
            started_at=NOW,
            completed_at=NOW + timedelta(minutes=1),
            checks=_checks()[:-1],
        )

    checks = list(_checks())
    checks[7] = checks[7].model_copy(update={"outcome": "fail", "detail": "missing object"})
    failed = policy.evaluate_restore(
        restore_run_id=uuid4(),
        tenant_id=TENANT_ID,
        installation_id=INSTALLATION_ID,
        backup_id=BACKUP_ID,
        inventory=_inventory(),
        inventory_signature_verified=True,
        reconciled_source_keys=frozenset(),
        accepted_source_position=4,
        restored_acceptance_position=3,
        artifact_rpo_seconds=301,
        started_at=NOW,
        completed_at=NOW + timedelta(hours=5),
        checks=tuple(checks),
    )

    reasons = {finding.reason for finding in failed.findings}
    assert reasons == {
        "accepted-record-rpo-nonzero",
        "artifact-rpo-exceeded",
        "restore-step-failed",
        "restore-rto-exceeded",
    }


def _checks() -> tuple[RestoreCheck, ...]:
    return tuple(
        RestoreCheck(
            kind=kind,
            outcome="pass",
            evidence_sha256="sha256:" + f"{index:x}" * 64,
            detail=f"{kind.value} verified",
        )
        for index, kind in enumerate(RestoreStepKind, 1)
    )


def _inventory(*, active_provider: bool = False) -> InventoryRevision:
    sources = (
        _source("ctower.root-supervisor.default", "root_supervisor_journal"),
        _source("ctower.effect.default", "effect_journal"),
        _source(
            "ctower.provider.default",
            "provider_journal",
            active=active_provider,
        ),
    )
    revision_id = UUID("40000000-0000-4000-8000-000000000001")
    payload: dict[str, object] = {
        "schema_id": "ctower.expected-source-inventory/v1",
        "inventory_revision_id": str(revision_id),
        "tenant_id": str(TENANT_ID),
        "revision_number": 1,
        "previous_revision_sha256": None,
        "signing_key_reference": "kms-ref:restore/inventory",
        "signing_key_version": "v1",
        "public_key_sha256": "sha256:" + "a" * 64,
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )
    return InventoryRevision(
        schema_id="ctower.expected-source-inventory/v1",
        inventory_revision_id=revision_id,
        tenant_id=TENANT_ID,
        revision_number=1,
        previous_revision_sha256=None,
        revision_sha256=digest,
        signature="signed-by-external-kms",
        signing_key_reference="kms-ref:restore/inventory",
        signing_key_version="v1",
        public_key_sha256="sha256:" + "a" * 64,
        object_key="operations/inventory/v1.json",
        object_version="version-1",
        created_at=NOW,
        sources=sources,
    )


def _source(
    key: str,
    kind: Literal["root_supervisor_journal", "effect_journal", "provider_journal"],
    *,
    active: bool = False,
) -> ExpectedSource:
    if active:
        return ExpectedSource(
            source_key=key,
            source_kind=kind,
            activation="active",
            cursor_declaration="trusted_cursor",
            source_count=1,
            trust_root_ref="journal-ref:provider/root",
            trusted_cursor="cursor-1",
            activation_event_ref="event-ref:provider/activation",
        )
    return ExpectedSource(
        source_key=key,
        source_kind=kind,
        activation="not_exercised",
        cursor_declaration="zero_source",
        source_count=0,
    )
